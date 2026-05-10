"""Test for data contracts."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

from lmdk import CompletionResponse
from pydantic import BaseModel

# Note: `output` relates to `prediction`, `obtained`. `reference` relates to `truth`, `expected`


@dataclass
class Example:
    """A single datset row, with the optional expected output (it might not be needed for some metrics)."""

    inputs: dict[str, Any]
    reference: Any | None = None


@dataclass
class Dataset:
    """A collection of examples to test a function."""

    examples: list[Example]


@dataclass
class Config:
    """The moving pieces of an Experiment that the harness can sweep.

    For MVP we are single-turn only: `prompt_template` is rendered once with
    the example inputs and sent as a single user message. No system
    instruction, no message list. Multi-turn can be added later as a
    non-breaking extension.
    """

    model: str
    prompt_template: str
    generation_kwargs: dict[str, Any] | None = None
    output_schema: type[BaseModel] | None = None


class TargetFunction(Protocol):
    """The shape every function under evaluation must follow.

    Mirrors `Config` 1:1 so the harness can call
    `target(example.inputs, **vars(config))` without per-target glue.

    Contract: render `prompt_template` with `inputs`, send as one user
    message, return the resulting `CompletionResponse`.
    """

    def __call__(
        self,
        inputs: dict[str, Any],
        model: str,
        prompt_template: str,
        generation_kwargs: dict | None = None,
        output_schema: type[BaseModel] | None = None,
    ) -> CompletionResponse: ...


@dataclass
class JudgeConfig:
    """The knobs of an LLM judge, kept separate from the target's `Config`."""

    model: str
    generation_kwargs: dict[str, Any] | None = None


@dataclass
class Experiment:
    """A target paired with the configuration under test."""

    name: str
    target: TargetFunction
    config: Config


@dataclass
class RunInfo:
    """Captures *when* an experiment was executed, and with which version."""

    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    commit_sha: str | None = None


@dataclass
class Score:
    """The evaluation result for one example and one metric."""

    value: int | float | str | bool
    normalized: float
    reason: str = ""


class DeterministicScorer(Protocol):
    """Defines the signature that any deterministic scoring function must follow."""

    def __call__(
        self,
        output: Any,
        example: Example,
    ) -> Score: ...


class StochasticScorer(Protocol):
    """Defines the signature of any LLM judge."""

    def __call__(
        self,
        output: Any,
        example: Example,
        config: JudgeConfig,
        rendered_prompt: str,
    ) -> Score: ...


class Scale(ABC):
    """Pinpoints the possible values a score can take."""

    @abstractmethod
    def validate(self, value: int | float | str):
        """Raises an error if the value given does not fit in the Scale."""
        ...

    @abstractmethod
    def normalize(self, value: int | float | str) -> float:
        """Normalizes the value between 0 and 1."""
        ...


class Range(Scale):
    """For continuous intervals of floats with a min and a max. I.e.: from 0 to 1."""

    def __init__(self, min: float, max: float):
        if min > max:
            raise ValueError("Are u dumb?")
        self.min = min
        self.max = max

    def validate(self, value: float | int):
        if not self.min <= value <= self.max:
            raise ValueError

    def normalize(self, value: int | float) -> float:
        return (value - self.min) / (self.max - self.min)


class Ordinal(Scale):
    """For any discrete (categorical or numerical) values.

    Must be in order from worse to best, we assume same distance. E.g.:
        - terrible, OK, fantastic
        - 1, 2, 3, 4, 5
    """

    def __init__(self, possible_values: list[str | int]):
        self.possible_values = possible_values

    def validate(self, value: int | float | str):
        if value not in self.possible_values:
            raise ValueError

    def normalize(self, value: int | float | str) -> float:
        return self.possible_values.index(value) / (len(self.possible_values) - 1)


@dataclass
class Metric:
    """Defines what is to measure."""

    name: str
    description: str
    requires_reference: bool
    scale: Scale
    scorer: DeterministicScorer | StochasticScorer
    judge_config: JudgeConfig | None = None  # required iff `scorer` is stochastic


@dataclass
class Trial:
    """One execution of an Experiment against one Example.

    Holds the full `CompletionResponse` so downstream code can read the model
    output, latency, token counts, finish reason, etc., without having to
    re-run the target.
    """

    example: Example
    response: CompletionResponse
    rendered_prompt: str
    error: Exception | None = None


@dataclass
class Scoring:
    """One metric applied to one Trial."""

    trial: Trial
    metric: Metric
    score: Score


@dataclass
class DatasetResults:
    """Summarizes the evaluation run across the whole dataset.

    Two parallel axes:
      - `trials`: one per example. Telemetry aggregates (latency, output
        tokens) iterate this list, so an example evaluated by N metrics is
        not overcounted.
      - `scorings`: |trials| × |metrics|. Quality aggregates iterate this.
    """

    experiment: Experiment
    run: RunInfo
    trials: list[Trial]
    scorings: list[Scoring]

    # ---- quality aggregates --------------------------------------------

    @property
    def mean_normalized(self) -> float:
        """Average normalized score across every scoring."""
        return _mean(s.score.normalized for s in self.scorings)

    def per_example(self) -> dict[int, float]:
        """Mean normalized score for each example (keyed by example id)."""
        return {
            id(ex): _mean(s.score.normalized for s in self.scorings if s.trial.example is ex)
            for ex in {id(s.trial.example): s.trial.example for s in self.scorings}.values()
        }

    def per_metric(self) -> dict[str, float]:
        """Mean normalized score for each metric (keyed by metric name)."""
        names = {s.metric.name for s in self.scorings}
        return {
            name: _mean(s.score.normalized for s in self.scorings if s.metric.name == name)
            for name in names
        }

    # ---- telemetry aggregates ------------------------------------------

    @property
    def mean_latency(self) -> float:
        """Average wall-clock latency across trials (seconds)."""
        return _mean(t.response.latency for t in self.trials)

    @property
    def mean_output_tokens(self) -> float:
        """Average output token count across trials."""
        return _mean(t.response.output_tokens for t in self.trials)

    @property
    def total_output_tokens(self) -> int:
        """Total output tokens consumed by the run."""
        return sum(t.response.output_tokens for t in self.trials)


def _mean(values) -> float:
    values = list(values)
    return sum(values) / len(values) if values else 0.0
