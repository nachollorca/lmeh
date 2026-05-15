"""Core data contracts shared across the harness.

Conceptual flow:

    Dataset -> Example
    Experiment = TargetFunction + ExperimentConfig
    Trial = result of running one Experiment on one Example
    Metric = scoring definition
    MetricResult = one Metric applied to one Trial
    RunResults = all Trials and MetricResults from one Experiment run

The harness keeps generation and scoring separate:
- Trials store target execution results.
- MetricResults store metric results.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

from lmdk import CompletionRequest, CompletionResponse
from pydantic import BaseModel


@dataclass
class Example:
    """A single dataset row.

    Some metrics (e.g. "is length less than X") do not need a ground truth,
    hence ``reference`` is optional.

    Args:
        inputs: Arbitrary inputs the target needs — domain objects, raw text,
            whatever the production caller would pass. The target decides how
            to turn these into a prompt; the harness never renders templates
            on its behalf.
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
        prompt_template: Jinja-style template passed to the target, which is
            responsible for rendering it into the final user message.
        generation_kwargs: Extra arguments forwarded to the model call.
        output_schema: Optional pydantic schema enforcing structured output.
    """

    model: str  # not sweepable over search space
    prompt_template: str  # sweepable
    generation_kwargs: dict[str, Any] | None = None  # sweepable
    output_schema: type[BaseModel] | None = None  # not sweepable


@dataclass(frozen=True)
class TargetOutput:
    """What every ``TargetFunction`` must return.

    Separates the three things the harness cares about:

    - ``response``: the raw ``CompletionResponse`` from ``lmdk``. Carries the
      originating ``CompletionRequest`` on ``response.request`` (i.e. the
      final, fully-rendered prompt and kwargs that were sent to the model),
      along with telemetry (latency, token counts, finish reason, native
      ``output`` parsed/unparsed). Treated as immutable by the harness.
    - ``output``: the post-processed product the function actually wants to
      expose. Scorers consume this. If the target does no post-processing,
      it equals ``response.output``.

    Use ``TargetOutput.passthrough(response)`` for the no-postprocessing case.
    """

    response: CompletionResponse
    output: Any

    @property
    def request(self) -> CompletionRequest | None:
        """Shortcut to ``response.request``: the final request sent to the LM."""
        return self.response.request

    @classmethod
    def passthrough(cls, response: CompletionResponse) -> "TargetOutput":
        """Build a ``TargetOutput`` with no post-processing applied."""
        return cls(response=response, output=response.output)


class TargetFunction(Protocol):
    """The shape every function under evaluation must follow.

    A target is a function that achieves a goal using **exactly one** LM
    completion. It may run arbitrary deterministic code before the call to
    prepare the prompt (e.g. format inputs, render the template) and after
    the call to refine the model's response (e.g. parse, validate, repair).
    Chains of multiple LM calls are out of scope.

    The target is the sole owner of prompt rendering: it transforms
    ``inputs``, renders them into ``prompt_template``, and dispatches the
    result as a single user message. The harness never re-renders the
    template; it reads the exact string the target sent back off
    ``TargetOutput.request.prompt`` (see ``Trial.rendered_prompt``).
    """

    def __call__(  # noqa: D102
        self,
        inputs: dict[str, Any],
        model: str,
        prompt_template: str,
        generation_kwargs: dict | None = None,
        output_schema: type[BaseModel] | None = None,
    ) -> TargetOutput: ...


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
        raw: Raw score in the metric's native scale.
        normalized: ``raw`` mapped to ``[0, 1]`` for cross-metric aggregation.
        reason: Optional rationale (typically populated by LLM judges).
    """

    raw: int | float | str
    normalized: float
    reason: str = ""


class DeterministicScorer(Protocol):
    """Signature of any deterministic (non-LLM) scoring function."""

    def __call__(  # noqa: D102
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

    def __call__(  # noqa: D102
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
    """Discrete (categorical or numerical) values ordered worst to best.

    Adjacent values are assumed equidistant when normalizing.

    Examples:
        ``["terrible", "OK", "fantastic"]`` or ``[1, 2, 3, 4, 5]``.

    Args:
        levels: Allowed values, sorted from worst to best.
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
class Metric:
    """Defines a single quantity to measure on a Trial.

    Args:
        name: Unique identifier used in aggregates.
        description: Human-readable explanation of what is measured.
        requires_reference: Whether ``Example.reference`` must be present.
        scale: Scale used to validate and normalize raw scores.
        scorer: Callable producing the score; deterministic or LLM-based.
        judge_config: Required for LLM-judge metrics. If present, the harness
            calls ``scorer`` as a ``StochasticScorer``; otherwise it calls it as
            a ``DeterministicScorer``.
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

    Exactly one of ``result`` or ``error`` is set:

    - On success, ``result`` holds the ``TargetOutput`` returned by the
      target, so downstream code can read the post-processed output, the raw
      response, latency, token counts, finish reason, etc., without re-running
      the target.
    - On failure, ``error`` holds the exception raised by the target so the
      run can continue and surface the failure in aggregates.
    """

    example: Example
    result: TargetOutput | None = None
    error: Exception | None = None

    @property
    def succeeded(self) -> bool:
        """Marks if the trial executed without errors."""
        return self.result is not None and self.error is None

    @property
    def rendered_prompt(self) -> str | None:
        """The exact user prompt sent by the target.

        The harness assumes targets send exactly one user message. ``None`` for
        failed trials, which have no response to inspect.
        """
        request = self.result.request if self.result else None
        return request.prompt[0].content if request else None  # We assume just one prompt


@dataclass
class MetricResult:
    """The result of applying one Metric to one Trial."""

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
    - ``metric_results``: ``|trials| * |metrics|``. Quality aggregates iterate this.

    Telemetry aggregates skip failed trials (those with no ``response``).
    """

    experiment: Experiment
    run: RunInfo
    trials: list[Trial]
    metric_results: list[MetricResult]

    @property
    def successful_trials(self) -> list[Trial]:
        """List of trials executed without errors."""
        return [t for t in self.trials if t.succeeded]

    @property
    def successful_responses(self) -> list[CompletionResponse]:
        """Raw LM responses from successful trials."""
        from typing import cast

        return [cast(TargetOutput, t.result).response for t in self.successful_trials]

    @property
    def failure_rate(self) -> float:
        """Fraction of trials that errored out, in ``[0, 1]``."""
        return 1.0 - len(self.successful_trials) / len(self.trials) if self.trials else 0.0

    @property
    def mean_normalized(self) -> float:
        """Average normalized score across every metric result."""
        return _mean(r.score.normalized for r in self.metric_results)

    def per_example(self) -> dict[int, float]:
        """Return mean normalized score per example, keyed by ``id(example)``."""
        return {
            id(ex): _mean(r.score.normalized for r in self.metric_results if r.trial.example is ex)
            for ex in {id(r.trial.example): r.trial.example for r in self.metric_results}.values()
        }

    def per_metric(self) -> dict[str, float]:
        """Return mean normalized score per metric, keyed by metric name."""
        names = {r.metric.name for r in self.metric_results}
        return {
            name: _mean(r.score.normalized for r in self.metric_results if r.metric.name == name)
            for name in names
        }

    @property
    def mean_latency(self) -> float:
        """Average wall-clock latency across successful trials, in seconds."""
        return _mean(r.latency for r in self.successful_responses)

    @property
    def mean_output_tokens(self) -> float:
        """Average output token count across successful trials."""
        return _mean(r.output_tokens for r in self.successful_responses)

    @property
    def total_output_tokens(self) -> int:
        """Total output tokens consumed by successful trials."""
        return sum(r.output_tokens for r in self.successful_responses)


def _mean(values) -> float:
    """Return the arithmetic mean of ``values``, or ``0.0`` if empty."""
    values = list(values)
    return sum(values) / len(values) if values else 0.0
