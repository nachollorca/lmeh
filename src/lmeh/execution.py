"""Acts upon the data contracts.

Two entry points:

- :func:`run_experiment` blocks and returns a fully-populated :class:`RunResults`.
- :func:`stream_experiment` yields :class:`Trial` and :class:`Scoring` items
  as soon as they are ready, so callers can render progress or persist
  partial results and survive mid-run crashes.

Both share the same threaded engine. ``run_trial`` and ``score_metric`` are
total functions: they never raise, instead wrapping failures into
``FailedTrial`` / ``FailedScoring`` so the executor loop stays simple.
"""

from collections.abc import Iterator
from concurrent.futures import Future, ThreadPoolExecutor, as_completed

from pydantic import BaseModel

from .datatypes import (
    Dataset,
    Example,
    Experiment,
    FailedScoring,
    FailedTrial,
    LLMJudgeMetric,
    LMConfig,
    Metric,
    ProgrammaticMetric,
    RunInfo,
    RunResults,
    Score,
    Scoring,
    SuccessfulScoring,
    SuccessfulTrial,
    TargetFunction,
    Trial,
)


def run_experiment(
    experiment: Experiment,
    dataset: Dataset,
    metrics: list[Metric],
    workers: int = 1,
) -> RunResults:
    """Run ``experiment`` over ``dataset`` and score every ``metric``.

    Blocks until the whole run is done. For incremental consumption use
    :func:`stream_experiment`.
    """
    trials: list[Trial] = []
    scorings: list[Scoring] = []
    for item in stream_experiment(experiment, dataset, metrics, workers=workers):
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


def stream_experiment(
    experiment: Experiment,
    dataset: Dataset,
    metrics: list[Metric],
    workers: int = 1,
) -> Iterator[Trial | Scoring]:
    """Run the experiment, yielding trials and scorings as they land.

    Order is not deterministic: items arrive in completion order. A trial is
    always yielded before any of its scorings.

    The same thread pool is shared between target calls and LLM-judge
    scorers so workers stay saturated: scoring for an example starts as soon
    as its trial completes, without waiting for the rest of the dataset.
    Programmatic scorers run inline on the consumer thread (they are
    cheap and not I/O-bound).
    """
    _validate_run(experiment=experiment, dataset=dataset, metrics=metrics)

    if not dataset:
        return

    with ThreadPoolExecutor(max_workers=max(workers, 1)) as pool:
        trial_futures: dict[Future[Trial], Example] = {
            pool.submit(
                run_trial,
                experiment.target,
                experiment.prompt_template,
                experiment.config,
                ex,
            ): ex
            for ex in dataset
        }
        score_futures: list[Future[Scoring]] = []

        for fut in as_completed(trial_futures):
            trial = fut.result()  # run_trial never raises
            yield trial

            for metric in metrics:
                if isinstance(metric, ProgrammaticMetric):
                    # Cheap, run inline and yield immediately.
                    yield score_metric(trial, metric)
                else:
                    # LLM judge: I/O-bound, offload to the pool.
                    score_futures.append(pool.submit(score_metric, trial, metric))

        for fut in as_completed(score_futures):
            yield fut.result()  # score_metric never raises


def run_trial(
    target: TargetFunction,
    prompt_template: str,
    config: LMConfig,
    example: Example,
) -> Trial:
    """Execute ``target`` against one ``example``.

    ``example.inputs`` is unpacked as keyword arguments, so the target's
    parameter names must match the dict keys.

    Total function: any exception raised by the target is captured into a
    :class:`FailedTrial`. The target is what is under evaluation, so its
    failures are data, not bugs in the harness.
    """
    try:
        result = target(prompt_template=prompt_template, config=config, **example.inputs)
        return SuccessfulTrial(example=example, result=result)
    except Exception as err:
        return FailedTrial(example=example, error=err)


def score_metric(trial: Trial, metric: Metric) -> Scoring:
    """Apply ``metric`` to ``trial``.

    Total function: any exception (scorer crash, malformed judge output,
    out-of-scale value) is captured into a :class:`FailedScoring`.

    Failed trials short-circuit to a sentinel zero score so they still
    contribute to quality aggregates — the target is what is under
    evaluation.
    """
    if isinstance(trial, FailedTrial):
        return SuccessfulScoring(
            trial=trial,
            metric=metric,
            score=Score(raw=0, normalized=0.0, reason=f"trial failed: {trial.error!r}"),
        )

    try:
        if isinstance(metric, ProgrammaticMetric):
            score = metric.scorer(trial.result.output, trial.example)
        else:  # LLMJudgeMetric
            score = metric.scorer(
                trial.result.output,
                trial.example,
                metric,
                metric.config,
                trial.rendered_prompt,
            )
        metric.scale.validate(score.raw)
        # Trust scorer-provided normalized value if scale already validated raw;
        # recompute to keep the contract consistent.
        score.normalized = metric.scale.normalize(score.raw)
        return SuccessfulScoring(trial=trial, metric=metric, score=score)
    except Exception as err:
        return FailedScoring(trial=trial, metric=metric, error=err)


def _validate_run(
    experiment: Experiment,
    dataset: Dataset,
    metrics: list[Metric],
) -> None:
    """Preflight checks. Raise ``ValueError`` on the first problem found.

    Catches configuration mistakes cheaply, before any LM call is made.
    Does not perform any network I/O.
    """
    _validate_dataset(dataset)
    _validate_metrics(metrics)
    _validate_experiment(experiment)


def _validate_dataset(dataset: Dataset) -> None:
    if not dataset:
        raise ValueError("dataset is empty")

    has_ref = [ex.reference is not None for ex in dataset]
    if any(has_ref) and not all(has_ref):
        raise ValueError(
            "dataset mixes examples with and without `reference`; "
            "make this all-or-nothing so reference-dependent metrics are unambiguous"
        )


def _validate_metrics(metrics: list[Metric]) -> None:
    if not metrics:
        raise ValueError("no metrics provided")

    names = [m.name for m in metrics]
    if len(set(names)) != len(names):
        raise ValueError(f"metric names must be unique, got {names!r}")

    for m in metrics:
        if isinstance(m, LLMJudgeMetric):
            if not m.config.model:
                raise ValueError(f"metric {m.name!r}: config.model is empty")
            if not m.prompt_template:
                raise ValueError(f"metric {m.name!r}: prompt_template is empty")


def _validate_experiment(experiment: Experiment) -> None:
    if not experiment.prompt_template:
        raise ValueError("experiment.prompt_template is empty")
    cfg = experiment.config
    if not cfg.model:
        raise ValueError("experiment.config.model is empty")
    if cfg.output_schema is not None and not (
        isinstance(cfg.output_schema, type) and issubclass(cfg.output_schema, BaseModel)
    ):
        raise ValueError("experiment.config.output_schema must be a pydantic BaseModel subclass")
