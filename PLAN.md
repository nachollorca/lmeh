# Evaluation Harness Architecture for LLM Functions

## 1. Objective and System Overview

The primary goal of this package is to provide an evaluation harness for benchmarking functions that leverage Large Language Models (LLMs). Because LLM outputs and LLM-based judges may be stochastic, the architecture should support repeated evaluations and aggregated scoring. However, the MVP should prioritize the single-pass path first: one target execution and one score per metric, while preserving result metadata that allows repetitions to be added later without changing the public result shape.

To aggregate scores across different tasks and metrics, all scores must be normalized to a standard `[0, 1]` range. Therefore, the system enforces that all evaluated metrics must be **bounded** (having a defined minimum and maximum).

In the future, we may introduce unbounded scales (e.g., `max=None`) which would require either empirical bounding, asymptoting scaling or my favorite: **batch normalization** (waiting for an entire evaluation suite to finish, computing the empirical min/max, and then normalizing the set).

The architecture separates concerns into six primary layers:
1. **Measurement Scales (`scale.py`)**: Defines the nature of the values a metric can take, how to validate them, and how to normalize them.
2. **Scorers (`scorer.py`)**: Defines *how* the score is extracted (e.g., using an LLM judge or a deterministic Python function).
3. **Metrics (`metric.py`)**: Defines *what* is being measured (name, description, scale), orchestrates the evaluation execution via composition with a `Scale` and a `Scorer`, and specifies whether the evaluation requires a reference.
4. **Datasets (`dataset.py`)**: Defines the examples that feed the target function and the optional expected outputs used for evaluation.
5. **Results (`result.py`)**: Defines the per-example/per-metric evaluation records, including score values, repetition metadata, and failure information.
6. **Task Orchestration (`task.py`)**: The execution engine that binds datasets, target functions (using `lmdk`), and metrics to automate the evaluation loop.

For the MVP, `lmdk` is the only runtime dependency and is a required dependency rather than an optional integration.

---

## 2. Measurement Scales (`scale.py`)

This module leverages the Strategy pattern. It defines an abstract base class `Scale` and concrete implementations based on Stevens's levels of measurement. This prevents ambiguity and standardizes normalization logic.

### Base Protocol
```python
class Scale(ABC):
    @abstractmethod
    def validate(self, value: Any) -> bool: ...

    @abstractmethod
    def normalize(self, value: Any) -> float: ...

    @abstractmethod
    def format_for_prompt(self) -> str: ...
```

### Concrete Scale Implementations

To leave no room for interpretation, the scales map directly to statistical terminology:

- **`Binary(Scale)`**:
  - **Description**: A variable that can only take one of two mutually exclusive values (e.g., `True/False`, `Pass/Fail`).
  - **Normalization**: Maps to `0.0` or `1.0`.
- **`Ordinal(Scale)`**:
  - **Description**: Categorical variables with a clear, defined order but unknown exact distances between them (e.g., `["Terrible", "Acceptable", "Perfect"]`).
  - **Normalization**: Based on index position `index / (len(categories) - 1)`.
- **`Discrete(Scale)`**:
  - **Description**: A set of fixed, evenly spaced numerical values (e.g., Likert scales represented as `[1, 2, 3, 4, 5]`).
  - **Normalization**: `(value - min) / (max - min)`.
- **`Continuous(Scale)`**:
  - **Description**: A continuous numerical range with a meaningful zero and exact distances (e.g., exact bounds like `min=0.0, max=1.0`).
  - **Normalization**: `(value - min) / (max - min)`.


---

## 3. Scorers (`scorer.py`)

To cleanly separate scoring execution from the metric definition, scorers are implemented as distinct classes following the Strategy pattern.

### The `Score` Entity
A simple structure encapsulating the evaluation result:
*   `value`: The raw measured value.
*   `reasoning`: Optional explanation for the score (typically provided by an LLM, but also fillable by a deterministic Python function scorer).
*   `normalized`: The `[0, 1]` normalized score, populated by the `Metric` using the `Scale`.

### Scorer Types
*   **`StochasticScorer`**: Leverages an LLM judge through `lmdk.complete`. It provides a default prompt template (which users can override) that incorporates the `output`, the full `example` (`example.inputs`, `example.reference`, and `example.metadata` as needed), the `original_prompt` (the contextual prompt given to the target LLM), optional `system_instruction`, and the scale instructions. For the MVP, it performs a single judge call. The API may reserve `judge_repetitions: int = 1` as a future extension point, allowing the same output to be judged multiple times later. When implemented, repeated judge scores should be retained individually and aggregated by the metric/task layer.
    * The stochastic scorer **must** use `lmdk.complete(..., output_schema=...)` rather than parsing free-form text. The structured judge schema must contain at least `value` and `reasoning` fields. The `value` field is validated and normalized by the metric's scale.
*   **`DeterministicScorer`**: Executes a custom Python function (e.g., regex matching, string length, heuristics). It does not provide a default; the user must explicitly pass the scoring function.

### Deterministic Scoring Function Protocol
For the MVP, deterministic scoring functions should follow this protocol:
```python
def scoring_fn(
    *,
    output: Any,
    example: Example,
    original_prompt: Sequence[Message] | None = None,
    system_instruction: str | None = None,
) -> Score: ...
```

---

## 4. Metrics (`metric.py`)

This module defines the `Metric` orchestrator. It utilizes the **Composition pattern** to completely separate *what* is being measured from *how* the value is extracted.

A metric has the following core identity fields:
```python
@dataclass(frozen=True)
class Metric:
    name: str
    description: str
    scale: Scale
    scorer: Scorer
    requires_reference: bool = False
```

`name` must be stable because it is used in result records and aggregation.

### Measurement Paradigms
The `Metric` class indicates its data requirements via a `requires_reference: bool` attribute:
*   **Reference-Free** (`requires_reference=False`): Evaluates the output entirely on its own merits (e.g., Tone, Fluency, Hallucination).
*   **Reference-Based** (`requires_reference=True`): Evaluates the output by comparing it against a reference ground truth (e.g., Recall, Exact Match, Semantic Similarity).

### Data Flow
1. User instantiates a `Scale` (e.g., `my_scale = Discrete([1, 2, 3, 4, 5])`).
2. User instantiates a `Scorer` (e.g., `my_scorer = StochasticScorer(model="gpt-4")` or `DeterministicScorer(scoring_fn=my_func)`).
3. User instantiates a `Metric`, passing the scale, scorer, and whether it requires a reference.
4. Upon evaluation (`metric.evaluate(output, example, original_prompt=None, system_instruction=None)`):
    * The metric checks if a reference is required and available as `example.reference`.
    * The metric requests a score from the scorer: `scorer.score(output, example, original_prompt, system_instruction, scale.format_for_prompt())`.
    * For the MVP, both deterministic and stochastic scorers return a single `Score`.
    * Each raw value is passed to `scale.validate(value)`.
    * If valid, `scale.normalize(value)` computes the `[0, 1]` normalized value and updates the corresponding `Score` object.
    * The populated score is returned. Future repeated-judge support may return or record multiple `Score` objects while preserving individual repetitions for variance analysis and downstream aggregation.

---

## 5. Datasets (`dataset.py`)

A dataset is an iterable of examples. Each example separates what the target function can see from what the evaluator can see.

### Example Entity
```python
@dataclass(frozen=True)
class Example:
    id: str
    inputs: Mapping[str, Any]
    reference: Any | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
```

*   `id`: Stable identifier for tracking, debugging, and aggregation.
*   `inputs`: Keyword arguments passed to the target function: `target(**example.inputs)`.
*   `reference`: Optional expected output. This should stay simple: the thing we expect the target to produce, not extra grading configuration.
*   `metadata`: Optional information for grouping, filtering, or reporting. It is not passed to the target by default.

References are evaluator-only and must never be passed to the target function. Reference-free metrics can ignore them.

### Serialized Shape
JSONL maps naturally to the same structure:
```json
{"id": "qa-001", "inputs": {"question": "What is the capital of France?"}, "reference": "Paris", "metadata": {"topic": "geography"}}
```

For the first version, `Dataset` can simply be `Iterable[Example]`. A named wrapper can be added later if needed for dataset-level metadata like `name`, `split`, or `version`.

---

## 6. Results (`result.py`)

The MVP needs a stable per-example/per-metric result contract so aggregation, debugging, and future repetitions can be added without changing the public shape.

### Evaluation Record
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

* `output`: The extracted `CompletionResponse.output` from the target, when target execution succeeded.
* `raw_score`: The unnormalized value returned by the scorer, when scoring succeeded.
* `normalized_score`: The `[0, 1]` score after scale validation and normalization.
* `reasoning`: Optional judge or deterministic-scorer explanation.
* `error_stage`: Identifies where the evaluation failed:
  * `"target"`: target function raised, returned the wrong type, or returned a `CompletionResponse` without request metadata.
  * `"scorer"`: deterministic scorer or stochastic judge execution failed.
  * `"validation"`: scorer returned a value that does not belong to the metric scale.
  * `"metric"`: metric configuration/data issue, such as a missing required reference.
* `error_message`: Human-readable failure detail.

For failed records, score fields should be `None` when unavailable. The harness should continue evaluating remaining examples and metrics after a record-level failure.

### Aggregation Result
For the MVP, aggregation can be minimal:
```python
@dataclass
class MetricSummary:
    metric_name: str
    mean_normalized_score: float | None
    n_success: int
    n_errors: int
```

Errored records are ignored when computing `mean_normalized_score`, but their count is reported through `n_errors`. If a metric has no successful records, `mean_normalized_score` is `None`.

---

## 7. Task Orchestration (`task.py`)

This module provides the `Task` abstraction, which serves as the execution runner that binds datasets, target functions, and metrics together. It specifically leverages the `lmdk` package's `CompletionResponse` structure to seamlessly extract both the generated result and the execution context.

### Execution Lifecycle
1. **Data Iteration**: The `Task` iterates over a dataset of `Example` objects.
2. **Target Execution**: For each example, it executes a user-defined Target Function as `target(**example.inputs)`. For the MVP, the target function **must** return a non-streaming `lmdk.CompletionResponse` and nothing else. The target must call `lmdk.core.complete(..., return_request=True)` so the evaluator can access the original request metadata. For the MVP, each example is passed through the target function once. The API may reserve `target_repetitions: int = 1` as a future extension point for repeated target executions.
3. **Context Extraction**: The orchestrator handles each `CompletionResponse` automatically to extract:
    * `output = response.output`: Leverages the smart unboxing property to get the actual parsed payload.
    * `original_prompt = response.request.prompt`: The exact message sequence sent to the model, vital for scorers that evaluate instruction following or context relevance.
    * `system_instruction = response.request.system_instruction`: The optional system-level instruction sent alongside the prompt.

    If the target returns anything other than a `CompletionResponse`, or if `response.request is None`, the task records a target-stage error for that example/metric rather than attempting to score it.
4. **Evaluation Routing**: The extracted payload, original prompt, system instruction, and full example are passed to the configured metrics via `metric.evaluate(output=output, example=example, original_prompt=original_prompt, system_instruction=system_instruction)`. Metrics and scorers access target inputs and references through `example.inputs` and `example.reference`, avoiding duplicated arguments.
5. **Repetition Metadata**: Even in the MVP, result records should include repetition fields so the result schema remains stable when repeated execution is added later:
    * `target_repetition`: `0` for the MVP; later identifies repeated executions of the target function for the same dataset example.
    * `judge_repetition`: `0` for the MVP; later identifies repeated LLM-judge scores for the same generated output when using `StochasticScorer`.
6. **Error Handling**: Failures are captured as `EvaluationRecord` objects with `error_stage` and `error_message` populated. A failure for one example or metric should not stop the whole task. Configuration errors that prevent the task from being constructed may still fail fast.
7. **Aggregation**: The resulting normalized `[0, 1]` scores and optional LLM reasonings are collected and aggregated to compute the final performance of the Target Function. For the MVP, aggregation reports the mean normalized score per metric, ignoring errored records while reporting the number of errors. Later versions can add variance, confidence intervals, and decomposition across target repetitions and judge repetitions.
