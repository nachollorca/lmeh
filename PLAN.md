# Evaluation Harness Architecture for LLM Functions

## 1. Objective and System Overview

The primary goal of this package is to provide an evaluation harness for benchmarking functions that leverage Large Language Models (LLMs). Because LLM outputs are inherently stochastic, measuring their performance requires repeated evaluations and aggregated scoring. 

To aggregate scores across different runs, tasks, and metrics, all scores must be normalized to a standard `[0, 1]` range. Therefore, the system enforces that all evaluated metrics must be **bounded** (having a defined minimum and maximum).

In the future, we may introduce unbounded scales (e.g., `max=None`) which would require either empirical bounding, asymptoting scaling or my favorite: **batch normalization** (waiting for an entire evaluation suite to finish, computing the empirical min/max, and then normalizing the set).

The architecture separates concerns into five primary layers:
1. **Measurement Scales (`scale.py`)**: Defines the nature of the values a metric can take, how to validate them, and how to normalize them.
2. **Scorers (`scorer.py`)**: Defines *how* the score is extracted (e.g., using an LLM judge or a deterministic Python function).
3. **Metrics (`metric.py`)**: Defines *what* is being measured (name, description, scale), orchestrates the evaluation execution via composition with a `Scorer`, and specifies whether the evaluation requires a reference.
4. **Datasets (`dataset.py`)**: Defines the examples that feed the target function and the optional expected outputs used for evaluation.
5. **Task Orchestration (`task.py`)**: The execution engine that binds datasets, target functions (using `lmdk`), and metrics to automate the evaluation loop.

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

*   **`Binary(Scale)`**:
    *   **Description**: A variable that can only take one of two mutually exclusive values (e.g., `True/False`, `Pass/Fail`).
    *   **Normalization**: Maps to `0.0` or `1.0`.
*   **`Ordinal(Scale)`**:
    *   **Description**: Categorical variables with a clear, defined order but unknown exact distances between them (e.g., `["Terrible", "Acceptable", "Perfect"]`).
    *   **Normalization**: Based on index position `index / (len(categories) - 1)`.
*   **`Discrete(Scale)`**:
    *   **Description**: A set of fixed, evenly spaced numerical values (e.g., Likert scales represented as `[1, 2, 3, 4, 5]`). 
    *   **Normalization**: `(value - min) / (max - min)`.
*   **`Continuous(Scale)`**:
    *   **Description**: A continuous numerical range with a meaningful zero and exact distances (e.g., exact bounds like `min=0.0, max=1.0`).
    *   **Normalization**: `(value - min) / (max - min)`.


---

## 3. Scorers (`scorer.py`)

To cleanly separate scoring execution from the metric definition, scorers are implemented as distinct classes following the Strategy pattern.

### The `Score` Entity
A simple structure encapsulating the evaluation result:
*   `value`: The raw measured value.
*   `reasoning`: Optional explanation for the score (typically provided by an LLM).
*   `normalized`: The `[0, 1]` normalized score, populated by the `Metric` using the `Scale`.

### Scorer Types
*   **`StochasticScorer`**: Leverages an LLM judge. It provides a default prompt template (which users can override) that incorporates the `output`, optional `reference`, optional `inputs`/`example`, optional `original_prompt` (the contextual instruction/prompt given to the target LLM), and the scale instructions. Because LLM judges are themselves stochastic, it supports `judge_repetitions: int = 1`, allowing the same output to be judged multiple times. The repeated judge scores are retained individually and aggregated by the metric/task layer.
*   **`DeterministicScorer`**: Executes a custom Python function (e.g., regex matching, string length, heuristics). It does not provide a default; the user must explicitly pass the scoring function.

---

## 4. Metrics (`metric.py`)

This module defines the `Metric` orchestrator. It utilizes the **Composition pattern** to completely separate *what* is being measured from *how* the value is extracted.

### Measurement Paradigms
The `Metric` class indicates its data requirements via a `requires_reference: bool` attribute:
*   **Reference-Free** (`requires_reference=False`): Evaluates the output entirely on its own merits (e.g., Tone, Fluency, Hallucination).
*   **Reference-Based** (`requires_reference=True`): Evaluates the output by comparing it against a reference ground truth (e.g., Recall, Exact Match, Semantic Similarity).

### Data Flow
1. User instantiates a `Scale` (e.g., `my_scale = Discrete([1, 2, 3, 4, 5])`).
2. User instantiates a `Scorer` (e.g., `my_scorer = StochasticScorer(model="gpt-4")` or `DeterministicScorer(scoring_fn=my_func)`).
3. User instantiates a `Metric`, passing the scale, scorer, and whether it requires a reference.
4. Upon evaluation (`metric.evaluate(output, reference=None, inputs=None, example=None, original_prompt=None)`):
    * The metric checks if a reference is required and provided.
    * The metric requests one or more scores from the scorer: `scorer.score(output, reference, inputs, example, original_prompt, scale.format_for_prompt())`.
    * For deterministic scorers this usually returns a single `Score`; for stochastic scorers it may return multiple `Score` objects according to `judge_repetitions`.
    * Each raw value is passed to `scale.validate(value)`.
    * If valid, `scale.normalize(value)` computes the `[0, 1]` normalized value and updates the corresponding `Score` object.
    * The populated score or collection of scores is returned, preserving individual repetitions for variance analysis and downstream aggregation.

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

## 6. Task Orchestration (`task.py`)

This module provides the `Task` abstraction, which serves as the execution runner that binds datasets, target functions, and metrics together. It specifically leverages the `lmdk` package's `CompletionResponse` structure to seamlessly extract both the generated result and the execution context.

### Execution Lifecycle
1. **Data Iteration**: The `Task` iterates over a dataset of `Example` objects.
2. **Target Execution**: For each example, it executes a user-defined Target Function as `target(**example.inputs)`. This function uses `lmdk.core.complete` (with `return_request=True`) and returns a `CompletionResponse`. Because target LLM calls are stochastic, `Task` supports `target_repetitions: int = 1`, causing each dataset example to be passed through the target function multiple times.
3. **Context Extraction**: The orchestrator handles each `CompletionResponse` automatically to extract:
    * `output = response.output`: Leverages the smart unboxing property to get the actual parsed payload.
    * `original_prompt = response.request.prompt`: The exact message sequence sent to the model, vital for scorers that evaluate instruction following or context relevance.
4. **Evaluation Routing**: The extracted payload, original prompt, example inputs, full example, and reference are passed to the configured metrics via `metric.evaluate(output=output, reference=example.reference, inputs=example.inputs, example=example, original_prompt=original_prompt)`.
5. **Repetition Tracking**: Results preserve both repetition axes:
    * `target_repetition`: repeated executions of the target function for the same dataset example.
    * `judge_repetition`: repeated LLM-judge scores for the same generated output when using `StochasticScorer`.
6. **Aggregation**: The resulting normalized `[0, 1]` scores and optional LLM reasonings are collected and aggregated to compute the final performance of the Target Function. Aggregation should report central tendency as well as variance across target repetitions and, where applicable, judge repetitions.
