# Evaluation Harness Architecture and Implementation Plan

## 1. Objective, Scope, and MVP Boundaries

The goal of this package is to provide an evaluation harness for benchmarking functions that use Large Language Models (LLMs). The harness runs a target function over a dataset, evaluates each output with one or more metrics, records per-example/per-metric results, and computes normalized aggregate scores.

Because both target LLM calls and LLM-based judges may be stochastic, the architecture must preserve enough metadata to support repeated target executions and repeated judge evaluations later. However, the MVP intentionally implements the simplest reliable path first:

- one target execution per example
- one scorer execution per metric
- one score per example/metric pair
- bounded metric scales only
- normalized scores in the `[0, 1]` range
- `lmdk` as a required runtime dependency
- target functions must return non-streaming `lmdk.CompletionResponse` objects with request metadata

All metric scores must be normalized to `[0, 1]` so that aggregation across metrics and tasks is meaningful. Therefore, every MVP scale must be bounded and capable of validating and normalizing raw score values.

Future versions may add unbounded scales, repeated target execution, repeated judging, empirical/batch normalization, variance estimates, confidence intervals, richer dataset wrappers, and more advanced reporting. These are intentionally out of scope for the MVP unless explicitly noted as schema-preserving extension points.

---

## 2. Architecture Overview

The system is organized into six core modules:

1. **Core data contracts (`dataset.py`, `result.py`)**
   - Define examples, intermediate scores, final evaluation records, and aggregate summaries.
2. **Measurement scales (`scale.py`)**
   - Define the legal values a metric may return and how those values normalize to `[0, 1]`.
3. **Scorers (`scorer.py`)**
   - Extract raw metric values from outputs using either deterministic Python code or an LLM judge.
4. **Metrics (`metric.py`)**
   - Define what is being measured and compose a `Scale` with a `Scorer`.
5. **Task orchestration (`task.py`)**
   - Run target functions over examples, route outputs to metrics, capture failures, and produce records.
6. **Aggregation (`result.py` or `aggregation.py`)**
   - Compute metric-level summaries from evaluation records.

The core dependency flow should be:

```text
Example / Score / EvaluationRecord
          ↓
        Scale
          ↓
        Scorer
          ↓
        Metric
          ↓
        Task
          ↓
     Aggregation
```

Implementation should follow this dependency order so each layer can be tested before higher-level orchestration is introduced.

---

## 3. Core Data Contracts

### 3.1 Examples (`dataset.py`)

A dataset is an iterable of examples. Each `Example` separates what the target function can see from what only the evaluator can see.

```python
@dataclass(frozen=True)
class Example:
    id: str
    inputs: Mapping[str, Any]
    reference: Any | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
```

Fields:

- `id`: Stable identifier for debugging, tracking, grouping, and aggregation.
- `inputs`: Keyword arguments passed to the target function via `target(**example.inputs)`.
- `reference`: Optional evaluator-only expected output. This is used by reference-based metrics but must never be passed to the target function.
- `metadata`: Optional evaluator/reporting metadata. This is not passed to the target function by default.

For the first version, `Dataset` can simply mean `Iterable[Example]`. A named dataset wrapper can be added later if dataset-level metadata such as `name`, `split`, or `version` becomes necessary.

JSONL maps naturally to this shape:

```json
{"id": "qa-001", "inputs": {"question": "What is the capital of France?"}, "reference": "Paris", "metadata": {"topic": "geography"}}
```

### 3.2 Intermediate Score (`result.py`)

`Score` is the intermediate score returned by a scorer and then validated/normalized by a metric.

```python
@dataclass
class Score:
    value: Any
    reasoning: str | None = None
    normalized: float | None = None
```

Fields:

- `value`: Raw score value returned by the scorer.
- `reasoning`: Optional explanation, commonly from an LLM judge but also allowed for deterministic scorers.
- `normalized`: `[0, 1]` normalized score. Scorers should normally leave this as `None`; `Metric.evaluate` populates it after scale validation.

The MVP may mutate the returned `Score` or return a new populated `Score`, but the behavior should be consistent and documented in code.

### 3.3 Evaluation Records (`result.py`)

The MVP needs a stable per-example/per-metric record shape so debugging, aggregation, and future repetition support can be added without changing the public contract.

```python
@dataclass
class EvaluationRecord:
    example_id: str
    metric_name: str
    target_repetition: int
    judge_repetition: int

    output: Any | None
    raw_score: Any | None
    normalized_score: float | None
    reasoning: str | None

    error_stage: Literal["target", "scorer", "validation", "metric"] | None = None
    error_message: str | None = None

    example_metadata: Mapping[str, Any] = field(default_factory=dict)
```

Fields:

- `example_id`: ID of the evaluated example.
- `metric_name`: Stable metric name used for grouping and aggregation.
- `target_repetition`: Always `0` in the MVP. Reserved for repeated target executions.
- `judge_repetition`: Always `0` in the MVP. Reserved for repeated LLM-judge evaluations.
- `output`: Extracted `CompletionResponse.output` from the target, if target execution succeeded.
- `raw_score`: Raw score value returned by the scorer, if scoring succeeded.
- `normalized_score`: Validated `[0, 1]` score, if validation and normalization succeeded.
- `reasoning`: Optional scorer explanation.
- `error_stage`: Stage at which the record failed, if any.
- `error_message`: Human-readable failure details.
- `example_metadata`: Copied from `Example.metadata` for grouping and reporting.

Error stages:

- `"target"`: Target function raised, returned the wrong type, returned a streaming response, or returned a `CompletionResponse` without request metadata.
- `"scorer"`: Deterministic scorer or stochastic judge execution failed.
- `"validation"`: Scorer returned a value that does not belong to the metric scale.
- `"metric"`: Metric configuration/data issue, such as a missing required reference.

For failed records, unavailable score fields should be `None`. The harness should continue evaluating remaining examples and metrics after record-level failures.

### 3.4 Aggregate Summaries (`result.py` or `aggregation.py`)

MVP aggregation is metric-level mean normalized score.

```python
@dataclass
class MetricSummary:
    metric_name: str
    mean_normalized_score: float | None
    n_success: int
    n_errors: int
```

Errored records are ignored when computing `mean_normalized_score`, but counted in `n_errors`. If a metric has no successful records, `mean_normalized_score` is `None`.

A convenient task return value can group records and summaries:

```python
@dataclass
class EvaluationResult:
    records: list[EvaluationRecord]
    summaries: list[MetricSummary]
```

---

## 4. Measurement Scales (`scale.py`)

Scales define which raw values are legal for a metric and how legal values normalize to `[0, 1]`. This module uses the Strategy pattern: a base `Scale` protocol plus concrete scale implementations.

### 4.1 Base Protocol

```python
class Scale(ABC):
    @abstractmethod
    def validate(self, value: Any) -> bool: ...

    @abstractmethod
    def normalize(self, value: Any) -> float: ...

    @abstractmethod
    def format_for_prompt(self) -> str: ...
```

Expected behavior:

- `validate(value)` returns whether `value` belongs to the scale.
- `normalize(value)` converts a valid raw value into a float in `[0, 1]`.
- `format_for_prompt()` returns judge-facing instructions that describe valid values.

`normalize` may assume the value has already been validated, but defensive implementations are acceptable.

### 4.2 Concrete Scale Implementations

#### `Binary(Scale)`

A variable that can take only one of two mutually exclusive values.

Examples:

- `True` / `False`
- `"pass"` / `"fail"`
- `"yes"` / `"no"`

Normalization maps the negative value to `0.0` and the positive value to `1.0`.

#### `Ordinal(Scale)`

A categorical scale with a clear order but unknown or non-uniform distance between categories.

Example:

```python
Ordinal(["Terrible", "Acceptable", "Perfect"])
```

Normalization:

```python
index / (len(categories) - 1)
```

#### `Discrete(Scale)`

A bounded set of fixed, evenly spaced numerical values.

Example:

```python
Discrete([1, 2, 3, 4, 5])
```

Normalization:

```python
(value - min_value) / (max_value - min_value)
```

#### `Continuous(Scale)`

A bounded numerical range with meaningful distances.

Example:

```python
Continuous(min=0.0, max=1.0)
```

Normalization:

```python
(value - min_value) / (max_value - min_value)
```

---

## 5. Scorers (`scorer.py`)

Scorers define how a raw score value is extracted from a target output. They do not define what the metric means and should not perform final normalization. They return `Score` objects that are later validated and normalized by `Metric`.

### 5.1 Base Scorer Protocol

```python
class Scorer(Protocol):
    def score(
        self,
        *,
        output: Any,
        example: Example,
        original_prompt: Sequence[Message] | None = None,
        system_instruction: str | None = None,
        scale_instructions: str | None = None,
    ) -> Score: ...
```

The scorer receives:

- `output`: Target function output extracted from `CompletionResponse.output`.
- `example`: Full evaluator-side example, including inputs, reference, and metadata.
- `original_prompt`: Prompt/messages sent by the target to the model, when available.
- `system_instruction`: System-level instruction sent by the target, when available.
- `scale_instructions`: Prompt-ready description of valid score values.

### 5.2 Deterministic Scorer

`DeterministicScorer` wraps an explicit Python function. There is no default scoring function; users must provide one.

MVP scoring function protocol:

```python
def scoring_fn(
    *,
    output: Any,
    example: Example,
    original_prompt: Sequence[Message] | None = None,
    system_instruction: str | None = None,
) -> Score: ...
```

The wrapper adapts this function to the common `Scorer` protocol. Deterministic scorers may use `example.inputs`, `example.reference`, and `example.metadata` as needed.

### 5.3 Stochastic Scorer

`StochasticScorer` uses an LLM judge through `lmdk.complete`.

Requirements:

- It must call `lmdk.complete(..., output_schema=...)` rather than parse free-form text.
- The structured output schema must contain at least:
  - `value`
  - `reasoning`
- It should provide a default judge prompt template.
- Users may override the prompt template.
- It performs a single judge call in the MVP.

The default prompt should be able to incorporate:

- target `output`
- `example.inputs`
- `example.reference`, if present
- `example.metadata`, if useful
- `original_prompt`
- `system_instruction`
- metric description, supplied by the metric if needed
- `scale_instructions`

The scorer returns `Score(value=..., reasoning=...)`. The metric validates `value` against the scale and computes `normalized`.

---

## 6. Metrics (`metric.py`)

A metric defines what is being measured. It composes a `Scale` with a `Scorer` and owns validation, normalization, and reference-requirement checks.

```python
@dataclass(frozen=True)
class Metric:
    name: str
    description: str
    scale: Scale
    scorer: Scorer
    requires_reference: bool = False
```

Fields:

- `name`: Stable identifier used in result records and aggregation.
- `description`: Human-readable description of what the metric measures.
- `scale`: Defines valid raw values and normalization.
- `scorer`: Extracts the raw score value.
- `requires_reference`: Whether `example.reference` is required.

### 6.1 Measurement Paradigms

Reference-free metrics evaluate the output on its own merits.

Examples:

- tone
- fluency
- concision
- toxicity
- hallucination risk when no ground truth is available

Reference-based metrics compare the output to an expected answer or ground truth.

Examples:

- exact match
- recall
- semantic similarity
- factual correctness against a reference

### 6.2 Evaluation Flow

`Metric.evaluate(...)` should perform the following steps:

1. If `requires_reference=True`, check that `example.reference` is available.
2. Call `scorer.score(...)`, passing:
   - `output`
   - `example`
   - `original_prompt`
   - `system_instruction`
   - `scale.format_for_prompt()`
3. Receive a `Score` with a raw `value`.
4. Validate `score.value` with `scale.validate(score.value)`.
5. Normalize with `scale.normalize(score.value)`.
6. Populate `score.normalized`.
7. Return the populated `Score`.

Metric-level errors should be distinguishable from scorer execution errors and validation errors so `Task` can produce precise `EvaluationRecord.error_stage` values.

---

## 7. Task Orchestration (`task.py`)

`Task` is the execution runner. It binds a dataset, a target function, and metrics into a full evaluation loop.

### 7.1 Task Inputs

A task needs:

- a dataset: `Iterable[Example]`
- a target function: called as `target(**example.inputs)`
- one or more metrics: `Sequence[Metric]`

For the MVP, the target function must return a non-streaming `lmdk.CompletionResponse` and nothing else.

The target function must call `lmdk.core.complete(..., return_request=True)` or otherwise return a `CompletionResponse` with populated request metadata. This is required so evaluators can inspect the original prompt and system instruction.

### 7.2 Execution Lifecycle

For each example:

1. Execute the target function once:

   ```python
   response = target(**example.inputs)
   ```

2. Validate the target response:
   - must be a non-streaming `lmdk.CompletionResponse`
   - must include `response.request`

3. Extract target context:
   - `output = response.output`
   - `original_prompt = response.request.prompt`
   - `system_instruction = response.request.system_instruction`

4. For each metric, call:

   ```python
   metric.evaluate(
       output=output,
       example=example,
       original_prompt=original_prompt,
       system_instruction=system_instruction,
   )
   ```

5. Convert the resulting `Score` into an `EvaluationRecord`.

6. If an error occurs, create an errored `EvaluationRecord` rather than stopping the full evaluation run.

### 7.3 Target Failures

If target execution fails for an example, the task should still create one errored record per metric so summaries report the correct number of metric-level failures.

For target failures:

- `error_stage="target"`
- `output=None`
- `raw_score=None`
- `normalized_score=None`
- `reasoning=None`
- `target_repetition=0`
- `judge_repetition=0`

### 7.4 Metric and Scorer Failures

If scoring or metric evaluation fails for one metric, other metrics for the same example should still run when possible.

Failure mapping:

- missing required reference → `error_stage="metric"`
- scorer function or LLM judge raises → `error_stage="scorer"`
- invalid raw score value → `error_stage="validation"`
- unexpected metric-layer issue → `error_stage="metric"`

### 7.5 Task Return Value

The task should return both raw records and aggregate summaries:

```python
EvaluationResult(
    records=records,
    summaries=summarize(records),
)
```

This keeps debugging data and high-level reporting together while still allowing callers to recompute custom aggregations.

---

## 8. Aggregation

Aggregation operates on `EvaluationRecord` objects and should not depend on target functions, datasets, metrics, or scorers.

MVP aggregation groups records by `metric_name` and computes:

- `n_success`: number of records with `normalized_score is not None` and no error
- `n_errors`: number of records with `error_stage is not None`
- `mean_normalized_score`: arithmetic mean of successful normalized scores, or `None` if there are no successes

Pseudo-code:

```python
def summarize(records: Sequence[EvaluationRecord]) -> list[MetricSummary]:
    summaries = []
    for metric_name, group in group_by_metric(records):
        successes = [r.normalized_score for r in group if r.error_stage is None and r.normalized_score is not None]
        errors = [r for r in group if r.error_stage is not None]
        summaries.append(
            MetricSummary(
                metric_name=metric_name,
                mean_normalized_score=mean(successes) if successes else None,
                n_success=len(successes),
                n_errors=len(errors),
            )
        )
    return summaries
```

Later aggregation can add variance, confidence intervals, per-metadata breakdowns, and repetition-aware summaries without changing `EvaluationRecord`.

---

## 9. Ordered Implementation Plan

### Step 1: Create the package skeleton

Create the initial module files:

```text
eh/
  __init__.py
  dataset.py
  result.py
  scale.py
  scorer.py
  metric.py
  task.py
```

If tests exist or will be added immediately, mirror these modules under the test directory.

### Step 2: Implement core data contracts

Implement:

- `Example` in `dataset.py`
- `Score` in `result.py`
- `EvaluationRecord` in `result.py`
- `MetricSummary` in `result.py`
- `EvaluationResult` in `result.py`

Add basic tests for construction, defaults, and immutability where expected.

### Step 3: Implement scales

Implement:

- base `Scale`
- `Binary`
- `Ordinal`
- `Discrete`
- `Continuous`

Test each scale for:

- valid values
- invalid values
- normalization boundaries
- midpoint normalization where applicable
- prompt formatting
- invalid constructor arguments, such as empty categories or equal min/max bounds

This layer should have no dependency on `lmdk`.

### Step 4: Implement scorer interfaces and deterministic scorer

Implement:

- `Scorer` protocol or abstract base class
- `DeterministicScorer`

Test that deterministic scorers:

- call the provided function with expected arguments
- return `Score`
- propagate or wrap exceptions in a way `Task` can map to `error_stage="scorer"`

At this stage, avoid implementing `StochasticScorer` unless needed immediately. Deterministic scoring is enough to validate the metric and task pipeline.

### Step 5: Implement metrics

Implement `Metric.evaluate(...)` with:

- reference requirement checks
- scorer invocation
- scale validation
- scale normalization
- populated `Score.normalized`
- clear exception types or error signals for missing references, scorer errors, and validation errors

Test with deterministic scorers first.

### Step 6: Implement aggregation

Implement `summarize(records)` using `EvaluationRecord` and `MetricSummary`.

Test:

- normal successful records
- mixed success/error records
- all-error metrics
- multiple metrics
- records with `normalized_score=None`

### Step 7: Implement task orchestration for deterministic metrics

Implement `Task` and `Task.run()` for the basic path:

- iterate examples
- call target as `target(**example.inputs)`
- require non-streaming `lmdk.CompletionResponse`
- require `response.request is not None`
- extract `output`, `original_prompt`, and `system_instruction`
- run each metric
- produce `EvaluationRecord` objects
- continue after record-level failures
- return `EvaluationResult(records=..., summaries=...)`

Test this with fake or lightweight `CompletionResponse` objects if possible, or with minimal `lmdk` calls if necessary.

### Step 8: Harden task error handling

Add tests for:

- target raises
- target returns wrong type
- target returns `CompletionResponse` without request metadata
- metric missing required reference
- scorer raises
- scorer returns invalid scale value
- one metric fails while another succeeds
- one example fails while later examples still run

Ensure target failures produce one errored record per metric.

### Step 9: Implement stochastic scorer

Implement `StochasticScorer` using `lmdk.complete(..., output_schema=...)`.

Include:

- structured judge output schema with `value` and `reasoning`
- default prompt template
- optional user-provided prompt template
- model/provider configuration as required by `lmdk`
- conversion from judge response to `Score`

Test with mocked `lmdk.complete` first. Add integration tests only if the project supports live model tests.

### Step 10: Add public exports and examples

Update `eh/__init__.py` to export the public API:

- `Example`
- `Score`
- `EvaluationRecord`
- `MetricSummary`
- `EvaluationResult`
- scales
- scorers
- `Metric`
- `Task`
- aggregation helper if public

Add at least one minimal example showing:

- a small dataset
- a target function returning `CompletionResponse`
- a deterministic metric
- task execution
- printed summaries

Add a second example for `StochasticScorer` if live LLM usage is acceptable.

### Step 11: Documentation and polish

Document:

- target function requirements
- reference-free vs reference-based metrics
- scale normalization guarantees
- error handling semantics
- MVP limitations
- future repetition fields

Review names, imports, type hints, and exceptions for API clarity.

---

## 10. Future Work

The following should remain out of the MVP unless needed by immediate users:

- target repetitions greater than one
- judge repetitions greater than one
- preserving multiple judge scores per output
- variance and confidence interval reporting
- repetition-aware aggregation
- unbounded scales
- empirical min/max normalization
- batch normalization after a suite completes
- richer dataset class with `name`, `split`, and `version`
- dataset loading helpers for JSONL/CSV/etc.
- metadata-based grouped summaries
- streaming target responses
- target functions that return raw values instead of `CompletionResponse`
- custom aggregation plugins

The MVP schema already reserves `target_repetition` and `judge_repetition`, so repeated evaluation can be added later without changing the public `EvaluationRecord` shape.
