# PLAN: Core execution verbs

## Goal

Implement the action layer for the existing LMEH data contracts. The harness should be able to:

1. Run an `Experiment` over a `Dataset` to produce one `Trial` per `Example`.
2. Score every `(Trial, Metric)` pair to produce `MetricResult`s.
3. Return a `RunResults` object with telemetry, quality aggregates, and failure accounting.
4. Use thread-based parallelism for both generation and scoring via a global `max_workers` argument.

## Design principles

- Keep generation and scoring separate.
- Keep functions small and easy to unit test.
- Use functional-style orchestration rather than stateful runner classes.
- Fail early during preflight when the run configuration is invalid.
- Do not fail the whole run when a target call or metric scorer fails.
- Preserve deterministic output order even when using threads.
- Treat scales as authoritative for score normalization.

## Data contract updates

### `MetricResult`

Update `MetricResult` so metric evaluation can have three states:

- successful metric evaluation: `score` is set
- failed metric evaluation: `error` is set
- skipped metric evaluation: `skipped_reason` is set

Skipped results represent non-applicable metric/example pairs, not failures. The main known case is a metric with `requires_reference=True` applied to an example whose `reference is None`.

Add properties:

- `succeeded`
- `failed`
- `skipped`

### `RunResults`

Update quality aggregates to use only successful metric results.

Add:

- `successful_metric_results`
- `failed_metric_results`
- `skipped_metric_results`
- `metric_failure_rate`
- `metric_skip_rate`

Update:

- `mean_normalized`
- `per_example()`
- `per_metric()`

Quality aggregates should include only successful metric results. Skipped results should be ignored, not treated as zero. Metric failure rate should count failed results over attempted applicable results, i.e. exclude skipped results from the denominator. Telemetry aggregates remain based on successful trials.

## New module

Create:

```text
src/lmeh/run.py
```

This module should contain the core verbs.

## Public API

Implement the main entry point:

```python
run_experiment(experiment, dataset, metrics, *, max_workers=1, version=None) -> RunResults
```

Responsibilities:

1. Preflight validate inputs.
2. Generate trials.
3. Score trials.
4. Return `RunResults` with `RunInfo(version=version)`.

## Preflight validation

Implement a helper like:

```python
validate_run_inputs(dataset, metrics) -> None
```

Checks:

- Metric names must be unique.

Do **not** fail preflight when a metric has `requires_reference=True` and some examples have `reference is None`. Those metric/example pairs should be skipped during scoring and ignored in quality/failure aggregates.

Allow empty datasets and empty metric lists unless there is a strong reason not to.

## Trial generation

Implement:

```python
run_trial(experiment, example) -> Trial
run_trials(experiment, dataset, *, max_workers=1) -> list[Trial]
```

`run_trial` should call `experiment.target` with:

- `inputs=example.inputs`
- `model=experiment.config.model`
- `prompt_template=experiment.config.prompt_template`
- `generation_kwargs=experiment.config.generation_kwargs`
- `output_schema=experiment.config.output_schema`

If the target succeeds, return a successful `Trial`.

If the target raises, catch the exception and return a failed `Trial` with `error` set. Target failures should not stop the run.

`run_trials` should apply `run_trial` to every example and preserve dataset order.

## Scoring

Implement:

```python
score_metric(trial, metric) -> MetricResult
score_trials(trials, metrics, *, max_workers=1) -> list[MetricResult]
```

`score_trials` should evaluate every `(trial, metric)` pair. This guarantees:

```text
len(metric_results) == len(trials) * len(metrics)
```

`score_metric` should catch scorer/evaluation exceptions and return a failed `MetricResult` instead of raising.

Scoring flow:

1. If `metric.requires_reference` and `trial.example.reference is None`, return a skipped `MetricResult`.
2. If the trial failed, return a failed `MetricResult`.
3. Extract model output from the trial response using a dedicated helper.
4. If `metric.judge_config is None`, call the scorer as a deterministic scorer.
5. Otherwise, call it as a stochastic scorer with `judge_config` and `trial.rendered_prompt`.
6. Normalize the returned score through the metric scale.
7. Return a successful `MetricResult`.

## Score normalization

Implement:

```python
normalize_score(metric, score) -> Score
```

The metric scale is authoritative:

- Validate `score.raw` with `metric.scale.validate`.
- Compute normalized value with `metric.scale.normalize`.
- Return a new `Score` preserving `raw` and `reason`, but replacing `normalized` with the computed value.
- Raise if the computed normalized value is outside `[0, 1]`.

Any exception here should be caught by `score_metric` and represented as a failed `MetricResult`.

## Output extraction

Use the canonical `lmdk.CompletionResponse.output` property directly when scoring.

No separate `response_output` helper is needed. At most, add a small `trial_output(trial) -> Any` helper if it improves readability:

```python
def trial_output(trial):
    if trial.response is None:
        raise ValueError("Trial has no response")
    return trial.response.output
```

No other part of the runner should inspect `content` or `parsed` directly.

## Parallelism

Use `concurrent.futures.ThreadPoolExecutor`.

Implement one internal helper like:

```python
_parallel_map_ordered(fn, items, *, max_workers)
```

Behavior:

- If `max_workers <= 1`, run sequentially.
- If `max_workers > 1`, use a thread pool.
- Preserve input order.

Use this helper for both:

- `run_trials`
- `score_trials`

The same global `max_workers` passed to `run_experiment` should control both target execution and metric scoring.

## Failure semantics

- Invalid run configuration fails before generation.
- Target function exceptions become failed `Trial`s.
- Metric/reference mismatches become skipped `MetricResult`s.
- Metric scorer exceptions become failed `MetricResult`s.
- Failed trials still generate failed metric results for every applicable metric.
- Failed trials generate skipped metric results for non-applicable metrics, such as reference-requiring metrics on examples without references.
- Quality aggregates include only successful metric results.
- Metric failure-rate aggregates exclude skipped metric results from the denominator.
- Telemetry aggregates ignore failed trials.

## Suggested implementation order

1. Update `MetricResult` in `src/lmeh/datatypes.py`.
2. Update `RunResults` quality aggregates in `src/lmeh/datatypes.py`.
3. Create `src/lmeh/run.py`.
4. Implement preflight validation.
5. Implement ordered threaded map helper.
6. Implement trial generation functions.
7. Implement output extraction using `CompletionResponse.output` directly.
8. Implement score normalization.
9. Implement metric scoring functions.
10. Implement `run_experiment` orchestration.
11. Run a quick import/smoke check.

Formal tests can be added after reviewing the implementation shape.
