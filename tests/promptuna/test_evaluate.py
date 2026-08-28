"""Tests for promptuna.evaluate."""

from unittest.mock import patch

import pytest
from helpers import (
    echo_program,
    fake_complete,
    make_llm_judge_metric,
    make_run_results,
    make_trial,
    score_of,
)

from promptuna.evaluate import (
    Aggregate,
    FailedScoring,
    LLMJudgeMetric,
    Metric,
    Ordinal,
    ProgrammaticMetric,
    Range,
    RawScore,
    RunInfo,
    RunResults,
    SuccessfulScoring,
    _aggregate,
    content_divergence,
    default_llm_judge,
    evaluate,
    score_metric,
    stream_evaluate,
)
from promptuna.program import Example
from promptuna.run import FailedTrial, SuccessfulTrial, run_trial

# ---------------------------------------------------------------------------
# Scales
# ---------------------------------------------------------------------------


def test_range_normalizes_between_floor_and_ceiling():
    scale = Range(0.0, 10.0)
    scale.validate(5)
    assert scale.normalize(5) == 0.5


def test_range_rejects_inverted_bounds():
    with pytest.raises(ValueError, match="floor must be lower"):
        Range(10.0, 0.0)


def test_range_rejects_out_of_bounds_values():
    scale = Range(0.0, 1.0)
    with pytest.raises(ValueError):
        scale.validate(2.0)


def test_ordinal_normalizes_worst_to_best():
    scale = Ordinal(["bad", "ok", "great"])
    assert scale.normalize("bad") == 0.0
    assert scale.normalize("great") == 1.0


def test_ordinal_requires_unique_levels():
    with pytest.raises(ValueError, match="unique"):
        Ordinal(["a", "a", "b"])


def test_ordinal_requires_at_least_two_levels():
    with pytest.raises(ValueError, match="at least two"):
        Ordinal(["only"])


# ---------------------------------------------------------------------------
# Aggregation helpers
# ---------------------------------------------------------------------------


def test_aggregate_empty_input():
    assert _aggregate([]) == Aggregate(mean=0.0, sd=0.0, n=0)


def test_aggregate_single_value_has_zero_sd():
    agg = _aggregate([0.5])
    assert agg.mean == 0.5
    assert agg.sd == 0.0
    assert agg.n == 1


def test_aggregate_computes_sample_standard_deviation():
    agg = _aggregate([0.0, 1.0])
    assert agg.mean == 0.5
    assert agg.sd == pytest.approx(0.70710678, rel=1e-5)
    assert agg.n == 2


# ---------------------------------------------------------------------------
# score_metric
# ---------------------------------------------------------------------------


def test_score_metric_applies_programmatic_scorer(
    example, exact_match_metric, fake_complete_factory
):
    with fake_complete_factory("4"):
        trial = run_trial(
            echo_program,
            "Answer: {{ question }}",
            "test:model",
            example,
        )
    scoring = score_metric(trial, exact_match_metric)

    assert isinstance(scoring, SuccessfulScoring)
    assert scoring.score.normalized == 1.0


def test_score_metric_returns_zero_for_failed_trial(example, exact_match_metric):
    failed = FailedTrial(example=example, error=RuntimeError("program crashed"))
    scoring = score_metric(failed, exact_match_metric)

    assert isinstance(scoring, SuccessfulScoring)
    assert scoring.score.normalized == 0.0
    assert "trial failed" in scoring.score.reason


def test_score_metric_wraps_scorer_errors(example, exact_match_metric):
    def exploding_scorer(output, example):
        raise RuntimeError("scorer blew up")

    broken_metric = ProgrammaticMetric(
        name="broken",
        description="always crashes",
        scale=Range(0.0, 1.0),
        scorer=exploding_scorer,
    )
    trial = make_trial(example)
    scoring = score_metric(trial, broken_metric)

    assert isinstance(scoring, FailedScoring)
    assert str(scoring.error) == "scorer blew up"


def test_score_metric_rejects_out_of_scale_values(example):
    metric = ProgrammaticMetric(
        name="strict",
        description="must stay in range",
        scale=Range(0.0, 1.0),
        scorer=lambda output, example: RawScore(raw=5.0),
    )
    scoring = score_metric(make_trial(example), metric)

    assert isinstance(scoring, FailedScoring)


# ---------------------------------------------------------------------------
# RunResults accessors
# ---------------------------------------------------------------------------


def test_run_results_summarizes_quality_and_reliability(experiment, examples, exact_match_metric):
    results = make_run_results(experiment, examples, exact_match_metric, scores=[1.0, 0.5])

    assert results.overall.mean == 0.75
    assert results.failure_rate == 0.0
    assert results.scoring_failure_rate == 0.0
    assert results.latency == pytest.approx(0.4)
    assert results.output_tokens == 4
    assert results.speed == pytest.approx(10.0)
    assert len(results.per_example()) == 2
    assert "exact_match" in results.per_metric()


def test_run_results_telemetry_is_zero_without_successful_responses(
    experiment, example, exact_match_metric
):
    failed = FailedTrial(example=example, error=RuntimeError("nope"))
    results = RunResults(
        experiment=experiment,
        run=RunInfo(),
        trials=[failed],
        scorings=[],
    )

    assert results.latency == 0.0
    assert results.output_tokens == 0
    assert results.speed == 0.0
    assert results.failure_rate == 1.0


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"examples": [], "metrics": [object()]}, "examples is empty"),
        (
            {
                "examples": [Example(inputs={"q": "1"}), Example(inputs={"q": "2"}, reference="2")],
                "metrics": [object()],
            },
            "mix rows with and without `reference`",
        ),
        ({"examples": [Example(inputs={"q": "1"})], "metrics": []}, "no metrics provided"),
    ],
)
def test_evaluate_rejects_invalid_input(experiment, kwargs, match):
    metrics: list[Metric] = kwargs.pop("metrics")
    if metrics == [object()]:
        metrics = [
            ProgrammaticMetric(
                name="m",
                description="d",
                scale=Range(0.0, 1.0),
                scorer=lambda output, example: RawScore(raw=1.0),
            )
        ]
    with pytest.raises(ValueError, match=match):
        evaluate(experiment, kwargs["examples"], metrics)


def test_evaluate_rejects_duplicate_metric_names(experiment, examples):
    metric = ProgrammaticMetric(
        name="dup",
        description="d",
        scale=Range(0.0, 1.0),
        scorer=lambda output, example: RawScore(raw=1.0),
    )
    with pytest.raises(ValueError, match="unique"):
        evaluate(experiment, examples, [metric, metric])


def test_evaluate_rejects_empty_prompt_template(experiment, examples, exact_match_metric):
    experiment.prompt_template = ""
    with pytest.raises(ValueError, match="prompt_template is empty"):
        evaluate(experiment, examples, [exact_match_metric])


# ---------------------------------------------------------------------------
# Integration: evaluate / stream_evaluate
# ---------------------------------------------------------------------------


def test_evaluate_scores_program_output(
    experiment, examples, exact_match_metric, fake_complete_factory
):
    with fake_complete_factory("4"):
        results = evaluate(experiment, examples[:1], [exact_match_metric])

    assert len(results.trials) == 1
    assert isinstance(results.trials[0], SuccessfulTrial)
    assert len(results.scorings) == 1
    assert score_of(results.scorings[0]).normalized == 1.0


def test_stream_evaluate_yields_trials_before_scorings(
    experiment, examples, exact_match_metric, fake_complete
):
    items = list(stream_evaluate(experiment, examples[:1], [exact_match_metric]))

    assert len(items) == 2
    assert isinstance(items[0], SuccessfulTrial)
    assert isinstance(items[1], SuccessfulScoring)


def test_stream_evaluate_with_empty_examples_raises(experiment, exact_match_metric):
    with pytest.raises(ValueError, match="examples is empty"):
        list(stream_evaluate(experiment, [], [exact_match_metric]))


def test_evaluate_runs_llm_judge_metrics_in_thread_pool(experiment, examples, model, fake_complete):
    metric = make_llm_judge_metric(model)
    results = evaluate(experiment, examples[:1], [metric], workers=2)

    assert len(results.scorings) == 1
    assert score_of(results.scorings[0]).normalized == 1.0


def test_default_llm_judge_uses_structured_output(model, example):
    metric = LLMJudgeMetric(
        name="judge",
        description="quality",
        scale=Range(0.0, 1.0),
        scorer=default_llm_judge,
        model=model,
        prompt_template="Judge {{ OUTPUT }} for {{ METRIC }}",
    )
    trial = make_trial(example)

    with patch("promptuna.evaluate.complete", side_effect=fake_complete):
        raw = default_llm_judge(
            trial.output,
            example,
            metric,
            model,
            trial.rendered_prompt,
        )

    assert raw.raw == 1.0
    assert raw.reason == "looks good"


def test_content_divergence_scores_identical_and_differing_replicates():
    assert content_divergence(["same", "same", "same"]) == 0.0
    assert content_divergence(["one"]) is None  # undefined from a single sample
    assert content_divergence([]) is None
    assert content_divergence(["abcdef", "abcxyz"]) == pytest.approx(0.5)


def test_replicate_divergence_aggregates_across_examples(experiment, examples, exact_match_metric):
    stable, wobbly = examples
    results = RunResults(
        experiment=experiment,
        run=RunInfo(),
        trials=[
            make_trial(stable, output="4"),
            make_trial(stable, output="4", replicate=1),
            make_trial(wobbly, output="abcdef"),
            make_trial(wobbly, output="abcxyz", replicate=1),
        ],
        scorings=[],
    )

    divergence = results.replicate_divergence()

    assert divergence is not None
    assert divergence.n == 2  # one value per example, not per trial
    assert divergence.mean == pytest.approx(0.25)  # mean of 0.0 and 0.5


def test_replicate_divergence_is_none_without_replicates(experiment, examples, exact_match_metric):
    results = make_run_results(experiment, examples, exact_match_metric, scores=[1.0, 1.0])
    assert results.replicate_divergence() is None
