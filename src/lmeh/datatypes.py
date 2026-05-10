"""Core data contracts shared across the harness."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

from lmdk import CompletionResponse
from pydantic import BaseModel


@dataclass
class Example:
    """A single dataset row.

    Some metrics (e.g. "is length less than X") do not need a ground truth,
    hence ``reference`` is optional.

    Args:
        inputs: Variables to process into the prompt template.
        reference: Expected output, if available.
    """

    inputs: dict[str, Any]
    reference: Any | None = None


Dataset = list[Example]


@dataclass
class ExperimentConfig:
    """The moving pieces of an Experiment that the harness can sweep.

    A ``TargetFunction`` receives these fields plus the per-example ``inputs``
    that get processed into ``prompt_template``.

    Args:
        model: Identifier of the model to call.
        prompt_template: Jinja style template rendered into the user message.
        generation_kwargs: Extra arguments forwarded to the model call.
        output_schema: Optional pydantic schema enforcing structured output.
    """

    model: str
    prompt_template: str
    generation_kwargs: dict[str, Any] | None = None
    output_schema: type[BaseModel] | None = None


class TargetFunction(Protocol):
    """The shape every function under evaluation must follow.

    The implementation may transform ``inputs``, render them into
    ``prompt_template``, and dispatch the result as a single user message,
    returning the model's ``CompletionResponse``.
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
class Experiment:
    """A named target paired with the configuration under test."""

    name: str
    target: TargetFunction
    config: ExperimentConfig


@dataclass
class Score:
    """The evaluation result for one example and one metric.

    Args:
        value: Raw score in the metric's native scale.
        normalized: ``value`` mapped to ``[0, 1]`` for cross-metric aggregation.
        reason: Optional rationale (typically populated by LLM judges).
    """

    value: int | float | str
    normalized: float
    reason: str = ""


class DeterministicScorer(Protocol):
    """Signature of any deterministic (non-LLM) scoring function."""

    def __call__(
        self,
        output: Any,
        example: Example,
    ) -> Score: ...


@dataclass
class JudgeConfig:
    """The knobs of an LLM judge, kept separate from the target's config."""

    model: str
    generation_kwargs: dict[str, Any] | None = None


class StochasticScorer(Protocol):
    """Signature of any LLM-judge scoring function.

    Receives the rendered target prompt so the judge can reason about both
    the question and the model's answer.
    """

    def __call__(
        self,
        output: Any,
        example: Example,
        config: JudgeConfig,
        rendered_prompt: str,
    ) -> Score: ...


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
        if floor > ceiling:
            raise ValueError
        self.floor = floor
        self.ceiling = ceiling

    def validate(self, value: float | int):
        if not self.floor <= value <= self.ceiling:
            raise ValueError

    def normalize(self, value: int | float) -> float:
        return (value - self.floor) / (self.ceiling - self.floor)


class Ordinal(Scale):
    """Discrete (categorical or numerical) values ordered worst to best.

    Adjacent values are assumed equidistant when normalizing.

    Examples:
        ``["terrible", "OK", "fantastic"]`` or ``[1, 2, 3, 4, 5]``.

    Args:
        levels: Allowed values, sorted from worst to best.
    """

    def __init__(self, levels: list[str | int]):
        self.levels = levels

    def validate(self, value: int | float | str):
        if value not in self.levels:
            raise ValueError

    def normalize(self, value: int | float | str) -> float:
        return self.levels.index(value) / (len(self.levels) - 1)


@dataclass
class Metric:
    """Defines a single quantity to measure on a Trial.

    Args:
        name: Unique identifier used in aggregates.
        description: Human-readable explanation of what is measured.
        requires_reference: Whether ``Example.reference`` must be present.
        scale: Scale used to validate and normalize raw scores.
        scorer: Callable producing the score; deterministic or LLM-based.
        judge_config: Required iff ``scorer`` is a ``StochasticScorer``.
    """

    name: str
    description: str
    requires_reference: bool
    scale: Scale
    scorer: DeterministicScorer | StochasticScorer
    judge_config: JudgeConfig | None = None


@dataclass
class Trial:
    """One execution of an Experiment against one Example.

    Exactly one of ``response`` or ``error`` is set:

    - On success, ``response`` holds the full ``CompletionResponse`` so
      downstream code can read output, latency, token counts, finish reason,
      etc., without re-running the target.
    - On failure, ``error`` holds the exception raised by the target so the
      run can continue and surface the failure in aggregates.
    """

    example: Example
    rendered_prompt: str
    response: CompletionResponse | None = None
    error: Exception | None = None


@dataclass
class Scoring:
    """One metric applied to one Trial."""

    trial: Trial
    metric: Metric
    score: Score


@dataclass
class RunInfo:
    """Captures when an experiment was executed and against which code version."""

    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    version: str | None = None  # can be a commit sha, a tag, ...


@dataclass
class RunResults:
    """Summary of one experiment run across a whole dataset.

    Results are stored along two parallel axes:

    - ``trials``: one entry per example. Telemetry aggregates (latency,
      output tokens) iterate this list so an example evaluated by N metrics
      is not overcounted.
    - ``scorings``: ``|trials| × |metrics|``. Quality aggregates iterate this.

    Telemetry aggregates skip failed trials (those with no ``response``).
    """

    experiment: Experiment
    run: RunInfo
    trials: list[Trial]
    scorings: list[Scoring]

    @property
    def successful_trials(self) -> list[Trial]:
        return [t for t in self.trials if t.succeeded]

    @property
    def mean_normalized(self) -> float:
        """Average normalized score across every scoring."""
        return _mean(s.score.normalized for s in self.scorings)

    def per_example(self) -> dict[int, float]:
        """Return mean normalized score per example, keyed by ``id(example)``."""
        return {
            id(ex): _mean(s.score.normalized for s in self.scorings if s.trial.example is ex)
            for ex in {id(s.trial.example): s.trial.example for s in self.scorings}.values()
        }

    def per_metric(self) -> dict[str, float]:
        """Return mean normalized score per metric, keyed by metric name."""
        names = {s.metric.name for s in self.scorings}
        return {
            name: _mean(s.score.normalized for s in self.scorings if s.metric.name == name)
            for name in names
        }

    @property
    def mean_latency(self) -> float:
        """Average wall-clock latency across successful trials, in seconds."""
        return _mean(t.response.latency for t in self.successful_trials)

    @property
    def mean_output_tokens(self) -> float:
        """Average output token count across successful trials."""
        return _mean(t.response.output_tokens for t in self.successful_trials)

    @property
    def total_output_tokens(self) -> int:
        """Total output tokens consumed by successful trials."""
        return sum(t.response.output_tokens for t in self.successful_trials)


def _mean(values) -> float:
    """Return the arithmetic mean of ``values``, or ``0.0`` if empty."""
    values = list(values)
    return sum(values) / len(values) if values else 0.0
