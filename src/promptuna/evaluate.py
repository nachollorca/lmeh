"""Score trials and run full experiments.

Two entry points:

- :func:`evaluate` blocks and returns a fully-populated :class:`RunResults`.
- :func:`stream_evaluate` yields :class:`Trial` and :class:`Scoring` items
  as soon as they are ready, so callers can render progress or persist
  partial results and survive mid-run crashes.

Both share the same threaded engine. :func:`~promptuna.run.run_trial` and
:func:`score_metric` are total functions: they never raise, instead wrapping
failures into :class:`~promptuna.run.FailedTrial` / :class:`FailedScoring` so the
executor loop stays simple.
"""

from abc import ABC, abstractmethod
from collections.abc import Iterator
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import UTC, datetime
from difflib import SequenceMatcher
from itertools import combinations
from pathlib import Path
from typing import Any, Literal, Protocol

from lmdk import CompletionResponse, complete, render_template
from pydantic import BaseModel, ConfigDict, create_model

from promptuna.program import Example, Experiment
from promptuna.run import (
    FailedTrial,
    SuccessfulTrial,
    Trial,
    _stream_trials,
    _validate_examples,
    _validate_experiment,
)

# ---------------------------------------------------------------------------
# Scoring: scales, scores, scorers, metrics
# ---------------------------------------------------------------------------


class Scale(ABC):
    """Defines the set of values a score can take."""

    @abstractmethod
    def validate(self, value: int | float | str):
        """Raise an error if ``value`` does not belong to the scale."""
        ...

    @abstractmethod
    def normalize(self, value: int | float | str) -> float:
        """Map ``value`` to the ``[0, 1]`` interval."""
        ...


class Range(Scale):
    """Continuous numeric interval bounded by ``floor`` and ``ceiling``."""

    def __init__(self, floor: float, ceiling: float):
        if floor >= ceiling:
            raise ValueError("Range floor must be lower than ceiling")
        self.floor = floor
        self.ceiling = ceiling

    def validate(self, value: int | float | str):  # noqa: D102
        if isinstance(value, str):
            value = float(value)
        if not self.floor <= value <= self.ceiling:
            raise ValueError

    def normalize(self, value: int | float | str) -> float:  # noqa: D102
        if isinstance(value, str):
            value = float(value)
        return (value - self.floor) / (self.ceiling - self.floor)


class Ordinal(Scale):
    """Discrete values ordered worst to best; adjacent levels are equidistant when normalizing.

    Examples:
        ``["terrible", "OK", "fantastic"]`` or ``[1, 2, 3, 4, 5]``.
    """

    def __init__(self, levels: list[str | int | float]):
        if len(levels) < 2:
            raise ValueError("Ordinal scale requires at least two levels")
        if len(set(levels)) != len(levels):
            raise ValueError("Ordinal scale levels must be unique")
        self.levels = levels

    def validate(self, value: int | float | str):  # noqa: D102
        if value not in self.levels:
            raise ValueError

    def normalize(self, value: int | float | str) -> float:  # noqa: D102
        return self.levels.index(value) / (len(self.levels) - 1)


@dataclass
class RawScore:
    """Pre-normalization scorer output."""

    raw: int | float | str
    reason: str = ""


@dataclass
class Score:
    """Evaluation result for one (example, metric).

    Produced by the harness from a :class:`RawScore` and the metric's scale.
    ``normalized`` is always populated — downstream aggregates rely on this.
    """

    raw: int | float | str
    normalized: float
    reason: str = ""


class ProgrammaticScorer(Protocol):
    """Signature of any programmatic (non-LLM) scoring function."""

    def __call__(  # noqa: D102
        self,
        output: Any,
        example: Example,
    ) -> RawScore: ...


class LLMJudgeScorer(Protocol):
    """Signature of any LLM-judge scoring function.

    Receives the rendered program prompt so the judge can reason about both
    the question and the model's answer. The judge's own prompt template
    lives on ``LLMJudgeMetric.prompt_template``; the judge model lives on
    ``metric.model``.
    """

    def __call__(  # noqa: D102
        self,
        output: Any,
        example: Example,
        metric: "LLMJudgeMetric",
        model: str,
        rendered_prompt: str,
        generation_kwargs: dict[str, Any] | None = None,
    ) -> RawScore: ...


@dataclass
class ProgrammaticMetric:
    """A metric whose scorer is plain Python."""

    name: str
    description: str
    scale: Scale
    scorer: ProgrammaticScorer


default_judge_template = (Path(__file__).parent / "prompt_templates" / "judge.jinja").read_text()


@dataclass
class LLMJudgeMetric:
    """A metric scored by an LLM judge.

    ``description`` is surfaced to the default judge as ``METRIC``. ``repeats``
    captures judge stochasticity; each repeat becomes its own ``Scoring``
    tagged with ``replicate``.
    """

    name: str
    description: str
    scale: Scale
    scorer: LLMJudgeScorer
    model: str
    prompt_template: str = default_judge_template
    repeats: int = 1


Metric = ProgrammaticMetric | LLMJudgeMetric
"""Programmatic or LLM-judge metric (dispatch with ``isinstance``)."""


# ---------------------------------------------------------------------------
# Scoring results
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SuccessfulScoring:
    """A metric successfully applied to a trial, producing a ``Score``.

    Sentinel zero scores emitted for failed trials also live here: from the
    scorer's perspective a score was recorded. Callers that want to separate
    "real" scores from sentinel zeros can check ``isinstance(trial,
    FailedTrial)``.
    """

    trial: Trial
    metric: Metric
    score: Score
    replicate: int = 0


@dataclass(frozen=True)
class FailedScoring:
    """A scorer crashed (e.g. judge returned malformed output).

    Excluded from quality aggregates so a flaky judge does not bias results.
    """

    trial: Trial
    metric: Metric
    error: Exception
    replicate: int = 0


Scoring = SuccessfulScoring | FailedScoring
"""The result of applying one Metric to one Trial (tagged union)."""


@dataclass
class RunInfo:
    """Captures when an experiment was executed and against which code version."""

    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    version: str | None = None  # can be a commit sha, a tag, ...


@dataclass(frozen=True)
class Aggregate:
    """Summary statistics over a set of values.

    Used wherever a single number would hide useful dispersion. ``sd`` is
    the sample standard deviation (``n-1`` denominator); it is ``0.0`` when
    ``n <= 1``, since dispersion is undefined with a single observation.
    """

    mean: float
    sd: float
    n: int


@dataclass
class RunResults:
    """Summary of one experiment run across a whole dataset.

    Results are stored along two parallel axes:

    - ``trials``: one entry per ``(example, program-replicate)``. Telemetry
      iterates this list so an example evaluated by N metrics is not
      overcounted.
    - ``scorings``: one entry per ``(trial, metric, judge-replicate)``.
      Failed trials contribute sentinel zero scores (the program is what's
      under evaluation); scorer errors contribute ``FailedScoring`` entries
      and are excluded from quality aggregates.

    Telemetry aggregates skip failed trials (those with no ``response``).
    """

    experiment: Experiment
    run: RunInfo
    trials: list[Trial]
    scorings: list[Scoring]

    # ------------------------------------------------------------------
    # Raw accessors
    # ------------------------------------------------------------------

    @property
    def successful_trials(self) -> list[SuccessfulTrial]:
        """Which trials executed without raising?"""
        return [t for t in self.trials if isinstance(t, SuccessfulTrial)]

    @property
    def successful_responses(self) -> list[CompletionResponse]:
        """What raw LM responses came back from successful trials?"""
        return [t.response for t in self.successful_trials if t.response is not None]

    @property
    def successful_scorings(self) -> list[SuccessfulScoring]:
        """Which scorings produced a score (no scorer crash)?"""
        return [r for r in self.scorings if isinstance(r, SuccessfulScoring)]

    # ------------------------------------------------------------------
    # Reliability
    # ------------------------------------------------------------------

    @property
    def failure_rate(self) -> float:
        """What fraction of program invocations crashed?"""
        return 1.0 - len(self.successful_trials) / len(self.trials) if self.trials else 0.0

    @property
    def scoring_failure_rate(self) -> float:
        """What fraction of scorings crashed in the scorer itself?"""
        if not self.scorings:
            return 0.0
        errors = sum(1 for r in self.scorings if isinstance(r, FailedScoring))
        return errors / len(self.scorings)

    # ------------------------------------------------------------------
    # Quality
    # ------------------------------------------------------------------

    @property
    def overall(self) -> Aggregate:
        """What's the headline score for the whole run, with dispersion?

        Aggregated over per-metric means so every metric carries equal
        weight regardless of how many replicates or examples it has.
        ``n`` is the number of metrics that produced at least one score.
        """
        return _aggregate(agg.mean for agg in self.per_metric().values())

    def per_example(self) -> dict[int, Aggregate]:
        """How does each example score, aggregated across metrics and replicates?

        Keyed by ``id(example)``. The mean pools every normalized score
        recorded for the example; useful to spot hard examples, but mixes
        heterogeneous metrics so interpret the dispersion with care.
        """
        scored = self.successful_scorings
        examples = {id(r.trial.example): r.trial.example for r in scored}
        return {
            ex_id: _aggregate(r.score.normalized for r in scored if r.trial.example is ex)
            for ex_id, ex in examples.items()
        }

    def per_metric(self) -> dict[str, Aggregate]:
        """How does each metric score across the dataset, aggregated across examples and replicates?

        Aggregated over per-example means so every example carries equal
        weight. The resulting ``sd`` measures **dataset heterogeneity** for
        the metric (how much examples differ), not measurement noise — see
        :meth:`replicate_noise` for that.
        """
        per_cell = self.per_example_and_metric()
        by_metric: dict[str, list[float]] = {}
        for (_ex_id, metric_name), agg in per_cell.items():
            by_metric.setdefault(metric_name, []).append(agg.mean)
        return {name: _aggregate(means) for name, means in by_metric.items()}

    def per_example_and_metric(self) -> dict[tuple[int, str], Aggregate]:
        """What's the score for each (example, metric) cell, aggregated across replicates only?

        The atomic unit of dispersion: ``sd`` here is pure measurement
        noise (program sampling x judge sampling) for one cell, with no
        dataset or metric mixing. Keyed by ``(id(example), metric.name)``.
        """
        cells: dict[tuple[int, str], list[float]] = {}
        for r in self.successful_scorings:
            key = (id(r.trial.example), r.metric.name)
            cells.setdefault(key, []).append(r.score.normalized)
        return {key: _aggregate(vals) for key, vals in cells.items()}

    def replicate_noise(self) -> dict[str, Aggregate]:
        """How noisy is each metric's measurement, on average?

        For each metric, takes the per-cell ``sd`` from
        :meth:`per_example_and_metric` and aggregates across examples. The
        resulting ``mean`` is the metric's **noise floor**; large values
        suggest bumping ``repeats`` or swapping the judge. Distinct from
        :meth:`per_metric` ``.sd``, which measures dataset heterogeneity.
        """
        per_cell = self.per_example_and_metric()
        by_metric: dict[str, list[float]] = {}
        for (_ex_id, metric_name), agg in per_cell.items():
            by_metric.setdefault(metric_name, []).append(agg.sd)
        return {name: _aggregate(sds) for name, sds in by_metric.items()}

    # ------------------------------------------------------------------
    # Telemetry
    # ------------------------------------------------------------------

    def replicate_divergence(self) -> Aggregate | None:
        """How much does the raw LM output wander between program replicates?

        Per example, :func:`content_divergence` over the completion contents of
        its replicates, aggregated across examples. ``0.0`` means every
        replicate returned byte-identical text. Unlike :meth:`replicate_noise`
        this needs no metrics, so it is the only stochasticity signal a plain
        ``run`` job has. It measures *text* instability, not quality
        instability — harmless rewording counts as divergence — so read it as
        telemetry beside the noise floor, never as a score.

        Returns ``None`` when no example has two or more successful replicates:
        divergence is undefined, not zero, from a single sample.
        """
        by_example: dict[int, list[str]] = {}
        for trial in self.successful_trials:
            if trial.response is not None:
                by_example.setdefault(id(trial.example), []).append(trial.response.content)
        per_example = [d for c in by_example.values() if (d := content_divergence(c)) is not None]
        return _aggregate(per_example) if per_example else None

    @property
    def latency(self) -> float:
        """How much compute time did program calls consume in total, in seconds?

        Sum of per-trial latencies — equivalent to serial wall-clock,
        independent of how many workers actually ran the experiment.
        """
        return sum(r.latency for r in self.successful_responses)

    @property
    def output_tokens(self) -> int:
        """How many output tokens did the run produce in total?"""
        return sum(r.output_tokens for r in self.successful_responses)

    @property
    def speed(self) -> float:
        """What's the average program throughput in output tokens per second?"""
        lat = self.latency
        return self.output_tokens / lat if lat > 0 else 0.0


def content_divergence(contents: list[str]) -> float | None:
    """Mean pairwise dissimilarity (``1 - difflib`` ratio) over replicate outputs.

    ``0.0`` for identical strings, approaching ``1.0`` for unrelated ones.
    ``None`` when fewer than two contents are given.
    """
    if len(contents) < 2:
        return None
    ratios = [SequenceMatcher(None, a, b).ratio() for a, b in combinations(contents, 2)]
    return 1.0 - sum(ratios) / len(ratios)


def _aggregate(values) -> Aggregate:
    """Return mean, sample SD and count for ``values``.

    Empty input yields ``Aggregate(0.0, 0.0, 0)``; single-element input
    yields ``sd=0.0``.
    """
    vals = list(values)
    n = len(vals)
    if n == 0:
        return Aggregate(mean=0.0, sd=0.0, n=0)
    m = sum(vals) / n
    if n == 1:
        return Aggregate(mean=m, sd=0.0, n=1)
    var = sum((v - m) ** 2 for v in vals) / (n - 1)
    return Aggregate(mean=m, sd=var**0.5, n=n)


# ---------------------------------------------------------------------------
# Built-in LLM judge
# ---------------------------------------------------------------------------


def _schema_for_scale(scale: Scale) -> type[BaseModel]:
    """Build a ``{raw, reason}`` pydantic schema typed against ``scale``.

    - ``Range`` → ``raw: float``.
    - ``Ordinal`` → ``raw: Literal[<levels>]`` so the model is forced to
      pick one of the allowed values.
    - Anything else → ``raw: Any`` (best effort; harness scale validation
      still runs on the returned value).
    """
    if isinstance(scale, Range):
        raw_ann: Any = float
    elif isinstance(scale, Ordinal):
        raw_ann = Literal[tuple(scale.levels)]  # ty: ignore[invalid-type-form]
    else:
        raw_ann = Any
    return create_model(
        "JudgeOutput",
        __config__=ConfigDict(extra="forbid"),
        raw=(raw_ann, ...),
        reason=(str, ...),
    )


def default_llm_judge(
    output: Any,
    example: Example,
    metric: LLMJudgeMetric,
    model: str,
    rendered_prompt: str,
    generation_kwargs: dict[str, Any] | None = None,
) -> RawScore:
    """Render the judge template, call the model, return a ``RawScore``.

    The default template (``default_judge_template``) expects these variables:

    - ``RENDERED_PROMPT``: the exact prompt the program sent to the model.
    - ``OUTPUT``: the program's post-processed output (stringified).
    - ``REFERENCE``: ``example.reference`` (may be ``None``; the default
      template wraps this block in an ``{% if REFERENCE %}``).
    - ``METRIC``: ``metric.description`` — what the judge is evaluating for.

    The output schema is derived from ``metric.scale``. Any error (template
    rendering, model call, schema validation) propagates so the harness
    records a ``FailedScoring`` rather than silently producing a bad score.
    """
    schema = _schema_for_scale(metric.scale)
    prompt = render_template(
        template=metric.prompt_template,
        RENDERED_PROMPT=rendered_prompt,
        OUTPUT=str(output),
        REFERENCE=example.reference,
        METRIC=metric.description,
    )
    response = complete(
        model=model,
        prompt=prompt,
        output_schema=schema,
        generation_kwargs=generation_kwargs,
    )
    parsed = response.parsed
    assert parsed is not None, "judge model returned no structured output"
    return RawScore(raw=parsed.raw, reason=parsed.reason)


# ---------------------------------------------------------------------------
# Experiment orchestration
# ---------------------------------------------------------------------------


def evaluate(
    experiment: Experiment,
    examples: list[Example],
    metrics: list[Metric],
    workers: int = 1,
) -> RunResults:
    """Run ``experiment`` over ``examples`` and score every ``metric``.

    Blocks until the whole run is done. For incremental consumption use
    :func:`stream_evaluate`.
    """
    trials: list[Trial] = []
    scorings: list[Scoring] = []
    for item in stream_evaluate(experiment, examples, metrics, workers=workers):
        if isinstance(item, (SuccessfulTrial, FailedTrial)):
            trials.append(item)
        else:
            scorings.append(item)
    return RunResults(
        experiment=experiment,
        run=RunInfo(),
        trials=trials,
        scorings=scorings,
    )


def stream_evaluate(
    experiment: Experiment,
    examples: list[Example],
    metrics: list[Metric],
    workers: int = 1,
) -> Iterator[Trial | Scoring]:
    """Run the experiment, yielding trials and scorings as they land.

    Order is not deterministic: items arrive in completion order. A trial is
    always yielded before any of its scorings.

    The same thread pool is shared between program calls and LLM-judge
    scorers so workers stay saturated: scoring for an example starts as soon
    as its trial completes, without waiting for the rest of the examples.
    Programmatic scorers run inline on the consumer thread (they are
    cheap and not I/O-bound).
    """
    _validate_run(experiment=experiment, examples=examples, metrics=metrics)

    if not examples:
        return

    with ThreadPoolExecutor(max_workers=max(workers, 1)) as pool:
        score_futures: list[Future[Scoring]] = []

        for trial in _stream_trials(pool, experiment, examples):
            yield trial
            yield from _dispatch_scorings(pool, trial, metrics, score_futures)

        for fut in as_completed(score_futures):
            yield fut.result()  # score_metric never raises


def _dispatch_scorings(
    pool: ThreadPoolExecutor,
    trial: Trial,
    metrics: list[Metric],
    score_futures: list[Future[Scoring]],
) -> Iterator[Scoring]:
    """Score ``trial`` against every metric.

    Programmatic metrics run inline and are yielded immediately (deterministic
    and cheap, so repeats are ignored). LLM-judge metrics are stochastic and
    I/O-bound: each replicate is offloaded to ``pool`` and appended to
    ``score_futures`` for the caller to drain later.
    """
    for metric in metrics:
        if isinstance(metric, ProgrammaticMetric):
            yield score_metric(trial, metric)
        else:
            for r in range(metric.repeats):
                score_futures.append(pool.submit(score_metric, trial, metric, replicate=r))


def score_metric(trial: Trial, metric: Metric, replicate: int = 0) -> Scoring:
    """Apply ``metric`` to ``trial``.

    Total function: any exception (scorer crash, malformed judge output,
    out-of-scale value) is captured into a :class:`FailedScoring`.
    Failed trials short-circuit to a sentinel zero score so they still
    contribute to quality aggregates.
    """
    if isinstance(trial, FailedTrial):
        return SuccessfulScoring(
            trial=trial,
            metric=metric,
            score=Score(raw=0, normalized=0.0, reason=f"trial failed: {trial.error!r}"),
            replicate=replicate,
        )

    try:
        if isinstance(metric, ProgrammaticMetric):
            raw_score = metric.scorer(trial.output, trial.example)
        else:  # LLMJudgeMetric
            raw_score = metric.scorer(
                trial.output,
                trial.example,
                metric,
                metric.model,
                trial.rendered_prompt,
            )
        metric.scale.validate(raw_score.raw)
        score = Score(
            raw=raw_score.raw,
            normalized=metric.scale.normalize(raw_score.raw),
            reason=raw_score.reason,
        )
        return SuccessfulScoring(trial=trial, metric=metric, score=score, replicate=replicate)
    except Exception as err:
        return FailedScoring(trial=trial, metric=metric, error=err, replicate=replicate)


def _validate_run(
    experiment: Experiment,
    examples: list[Example],
    metrics: list[Metric],
) -> None:
    """Preflight checks. Raise ``ValueError`` on the first problem found.

    Catches configuration mistakes cheaply, before any LM call is made.
    Does not perform any network I/O.
    """
    _validate_examples(examples)
    _validate_metrics(metrics)
    _validate_experiment(experiment)


def _validate_metrics(metrics: list[Metric]) -> None:
    if not metrics:
        raise ValueError("no metrics provided")

    names = [m.name for m in metrics]
    if len(set(names)) != len(names):
        raise ValueError(f"metric names must be unique, got {names!r}")

    for m in metrics:
        if isinstance(m, LLMJudgeMetric):
            if not m.model:
                raise ValueError(f"metric {m.name!r}: model is empty")
            if not m.prompt_template:
                raise ValueError(f"metric {m.name!r}: prompt_template is empty")
            if m.repeats < 1:
                raise ValueError(f"metric {m.name!r}: repeats must be >= 1, got {m.repeats}")
