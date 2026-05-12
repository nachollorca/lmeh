# TODO — firing up the grill

`src/lmeh/datatypes.py` defines the *nouns* (`Example`, `Experiment`, `Trial`,
`Metric`, `Scoring`, `RunResults`) and the *protocols* for pluggable pieces
(`TargetFunction`, `DeterministicScorer`, `StochasticScorer`). What's missing
is the *verb*: a runner that turns these ingredients into a `RunResults`.

Minimal next file: `src/lmeh/runner.py` exposing roughly

```python
def run(experiment: Experiment, dataset: Dataset, metrics: list[Metric],
        *, version: str | None = None, max_concurrency: int = 8) -> RunResults: ...
```

## What the runner must do

1. **Trial production**
   - Iterate the `Dataset`.
   - Call `experiment.target(inputs=ex.inputs, **asdict(experiment.config))`
     for each `Example`.
   - Wrap the result (or exception) into a `Trial`.
   - Nothing today turns `Experiment + Dataset` into `list[Trial]`.

2. **Scoring**
   - For each successful `Trial × Metric`, dispatch to the right scorer:
     - `DeterministicScorer(output, example)`
     - `StochasticScorer(output, example, config=metric.judge_config,
       rendered_prompt=trial.rendered_prompt)`
   - Then `metric.scale.validate(score.value)` and set
     `score.normalized = metric.scale.normalize(score.value)`.
   - **Open question**: today `Score` requires both `value` and `normalized`
     from the scorer, but `Scale` clearly wants to own normalization. Decide
     which side computes it (probably the runner, via `Scale`).

3. **Pre-flight checks** (currently only documented in docstrings, unenforced)
   - `metric.requires_reference` ⇒ every `Example.reference` is not `None`.
   - `metric.judge_config is not None` iff `scorer` is a `StochasticScorer`.
   - Sensible error if dataset is empty, metrics is empty, etc.

4. **Assembly**
   - Wrap into `RunResults(experiment, RunInfo(version=...), trials, scorings)`.

5. **Cross-experiment glue** (optional but implied by the shape of
   `ExperimentConfig` being sweepable)
   - `run_suite(experiments, dataset, metrics) -> list[RunResults]`
   - A comparison/report helper on top.

6. **Execution concerns**
   - Concurrency: model calls are I/O-bound. `asyncio.gather` or a thread
     pool with a concurrency cap.
   - Retries / timeouts.
   - Progress reporting.
   - Persistence: serialize `RunResults` to disk. Note that
     `Trial.error: Exception` and `TargetFunction` callables are not
     trivially JSON-able — likely want a `to_dict` that drops or repr-s them.

## Suggested order of attack

1. Decide the `Score` vs `Scale` normalization split.
2. Synchronous, single-threaded `run(...)` end-to-end with pre-flight checks.
3. A couple of tiny smoke tests with a fake `TargetFunction` and a trivial
   deterministic metric.
4. Add concurrency.
5. Add persistence / `to_dict`.
6. `run_suite` + reporting.
