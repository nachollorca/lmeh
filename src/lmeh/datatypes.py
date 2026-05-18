"""Core data contracts shared across the harness.

Conceptual flow:

    Dataset -> Example
    Experiment = TargetFunction + TargetConfig
    Trial = result of running one Experiment on one Example
    Metric = scoring definition
    Scoring = one Metric applied to one Trial
    RunResults = all Trials and Scorings from one Experiment run

The harness keeps generation and scoring separate:
- Trials store target execution results.
- Scorings store metric results.

This module is organized in two halves:

1. Types the *user* defines or constructs when wiring up an evaluation
   (examples, targets, metrics, scales).
2. Types the *harness* produces and the user only reads (trials, scorings,
   run results).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

from lmdk import CompletionRequest, CompletionResponse
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Inputs: things the user defines
# ---------------------------------------------------------------------------


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
"""A dataset is a simple iterator of examples. In the future can contain metadata and splits."""


@dataclass
class TargetConfig:
    """The moving pieces of a ``TargetFunction`` that the harness can sweep.

    A ``TargetFunction`` receives an instance of this config plus the
    per-example ``inputs`` it must render into ``prompt_template``.

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
    ``inputs``, renders them into ``config.prompt_template``, and dispatches
    the result as a single user message. The harness never re-renders the
    template; it reads the exact string the target sent back off
    ``TargetOutput.request.prompt`` (see ``Trial.rendered_prompt``).
    """

    def __call__(  # noqa: D102
        self,
        inputs: dict[str, Any],
        config: TargetConfig,
    ) -> TargetOutput: ...


@dataclass
class Experiment:
    """A named target paired with the configuration under test."""

    name: str
    target: TargetFunction
    config: TargetConfig


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
class Score:
    """The evaluation result for one example and one metric.

    Args:
        raw: Raw score in the metric's native scale.
        normalized: ``raw`` mapped to ``[0, 1]`` for cross-metric aggregation.
        reason: Optional rationale (typically populated by LLM judges).
    """

    raw: int | float | str
    normalized: float | None = None
    reason: str = ""


class ProgrammaticScorer(Protocol):
    """Signature of any programmatic (non-LLM) scoring function."""

    def __call__(  # noqa: D102
        self,
        output: Any,
        example: Example,
    ) -> Score: ...


default_judge_template = """
You will be acting as an expert judge to evaluate the result produced by an LLM-based function.
Your task is to assess and score how well the result meets the specified evaluation metric.

Here is the original prompt that was sent to the LLM:

<rendered_prompt>
{{RENDERED_PROMPT}}
</rendered_prompt>

Here is the result that was obtained from the LLM:

<output>
{{OUTPUT}}
</output>

{% if REFERENCE %}
This is the golden-standard expected reference:

<reference>
{{REFERENCE}}
</reference>
{% endif %}

And this is the specific metric you should use to evaluate the result:

<metric>
{{METRIC}}
</metric>

Now go ahead and score the result obtained by the LLM function for the given metric.""".strip()


@dataclass
class JudgeConfig:
    """The knobs of an LLM judge, kept separate from the target's config.

    Args:
        model: Identifier of the judge model.
        prompt_template: Jinja-style template the judge renders before
            calling the model. Defaults to ``default_judge_template``.
        generation_kwargs: Extra arguments forwarded to the judge call.
    """

    model: str
    prompt_template: str = default_judge_template
    generation_kwargs: dict[str, Any] | None = None


class LLMJudgeScorer(Protocol):
    """Signature of any LLM-judge scoring function.

    Receives the rendered target prompt so the judge can reason about both
    the question and the model's answer.
    """

    def __call__(  # noqa: D102
        self,
        output: Any,
        example: Example,
        metric: "Metric",
        config: JudgeConfig,
        rendered_prompt: str,
    ) -> Score: ...


@dataclass
class Metric:
    """Defines a single quantity to measure on a Trial.

    Args:
        name: Unique identifier used in aggregates.
        description: Human-readable explanation of what is measured.
        scale: Scale used to validate and normalize raw scores.
        scorer: Callable producing the score; deterministic or LLM-based.
        judge_config: Required for LLM-judge metrics. If present, the harness
            calls ``scorer`` as an ``LLMJudgeScorer``; otherwise it calls it as
            a ``ProgrammaticScorer``.
    """

    name: str
    description: str
    scale: Scale
    scorer: ProgrammaticScorer | LLMJudgeScorer
    judge_config: JudgeConfig | None = None


# ---------------------------------------------------------------------------
# Outputs: things the harness produces (users read, rarely construct)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SuccessfulTrial:
    """A trial whose target executed without raising.

    ``result`` carries the post-processed output plus the raw
    ``CompletionResponse`` (latency, tokens, finish reason, originating
    request, etc.).
    """

    example: Example
    result: TargetOutput

    @property
    def rendered_prompt(self) -> str:
        """The exact user prompt sent by the target.

        The harness assumes targets send exactly one user message.
        """
        request = self.result.request
        assert request is not None, "Successful trial must carry a request"
        return request.prompt[0].content


@dataclass(frozen=True)
class FailedTrial:
    """A trial whose target raised. ``error`` is surfaced in aggregates."""

    example: Example
    error: Exception


Trial = SuccessfulTrial | FailedTrial
"""One execution of an Experiment against one Example.

A tagged union: pattern-match on ``SuccessfulTrial`` / ``FailedTrial`` (or
use ``isinstance``) to consume. The target is what's under evaluation, so
failed trials remain in ``RunResults.trials`` and count against the run.
"""


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


@dataclass(frozen=True)
class FailedScoring:
    """A scorer crashed (e.g. judge returned malformed output).

    Excluded from quality aggregates so a flaky judge does not bias results.
    """

    trial: Trial
    metric: Metric
    error: Exception


Scoring = SuccessfulScoring | FailedScoring
"""The result of applying one Metric to one Trial (tagged union)."""


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
    - ``scorings``: one entry per (trial, metric) pair. Failed trials
      contribute zero scores (the target is what's under evaluation);
      scorer errors contribute entries with ``error`` set and are excluded
      from quality aggregates.

    Telemetry aggregates skip failed trials (those with no ``response``).
    """

    experiment: Experiment
    run: RunInfo
    trials: list[Trial]
    scorings: list[Scoring]

    @property
    def successful_trials(self) -> list[SuccessfulTrial]:
        """List of trials executed without errors."""
        return [t for t in self.trials if isinstance(t, SuccessfulTrial)]

    @property
    def successful_responses(self) -> list[CompletionResponse]:
        """Raw LM responses from successful trials."""
        return [t.result.response for t in self.successful_trials]

    @property
    def failure_rate(self) -> float:
        """Fraction of trials that errored out, in ``[0, 1]``."""
        return 1.0 - len(self.successful_trials) / len(self.trials) if self.trials else 0.0

    @property
    def successful_scorings(self) -> list[SuccessfulScoring]:
        """Scorings that produced a score (excludes scorer errors)."""
        return [r for r in self.scorings if isinstance(r, SuccessfulScoring)]

    @property
    def mean_normalized(self) -> float:
        """Average normalized score across every successful scoring."""
        return _mean(r.score.normalized for r in self.successful_scorings)

    def per_example(self) -> dict[int, float]:
        """Return mean normalized score per example, keyed by ``id(example)``."""
        scored = self.successful_scorings
        return {
            id(ex): _mean(r.score.normalized for r in scored if r.trial.example is ex)
            for ex in {id(r.trial.example): r.trial.example for r in scored}.values()
        }

    def per_metric(self) -> dict[str, float]:
        """Return mean normalized score per metric, keyed by metric name."""
        scored = self.successful_scorings
        names = {r.metric.name for r in scored}
        return {
            name: _mean(r.score.normalized for r in scored if r.metric.name == name)
            for name in names
        }

    @property
    def scoring_failure_rate(self) -> float:
        """Fraction of scorings where the scorer itself errored, in ``[0, 1]``."""
        if not self.scorings:
            return 0.0
        errors = sum(1 for r in self.scorings if isinstance(r, FailedScoring))
        return errors / len(self.scorings)

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
