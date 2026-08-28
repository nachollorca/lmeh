"""Render :class:`~promptuna.evaluate.RunResults` and optimization trajectories as markdown."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from promptuna.evaluate import Aggregate, Example, RunResults
from promptuna.run import SuccessfulTrial

if TYPE_CHECKING:
    from promptuna.optimize import Step, Thinking

_MAX_WEAK_EXAMPLES = 3
_VERBATIM_FENCE = "````"

MetricBreakdown = tuple[str, float, str]
WeakExampleEntry = tuple[Example, float, list[MetricBreakdown]]


def fence_verbatim(tag: str, content: str) -> str:
    """Wrap *content* in a four-backtick fenced block labelled *tag*."""
    return f"{_VERBATIM_FENCE}{tag}\n{content}\n{_VERBATIM_FENCE}"


def _fmt(agg: Aggregate) -> str:
    """Render an ``Aggregate`` as ``mean ± sd (n=...)``."""
    return f"{agg.mean:.2f} ± {agg.sd:.2f} (n={agg.n})"


def _weakest_examples(result: RunResults, limit: int) -> list[WeakExampleEntry]:
    """Return up to ``limit`` lowest-scoring imperfect examples with per-metric detail.

    Each entry is ``(example, mean_normalized, [(metric, normalized, reason)])``,
    sorted worst-first. Examples are pooled across metrics and replicates by
    ``id(example)``, mirroring ``RunResults.per_example``. Examples with a
    perfect mean (``>= 1.0``) are excluded — they have no room to improve, so
    surfacing them as "weak" would be misleading. ``limit`` is therefore a cap,
    not a target: fewer (or zero) entries come back when fewer examples are
    imperfect.
    """
    grouped: dict[int, tuple[Example, list[MetricBreakdown]]] = {}
    for scoring in result.successful_scorings:
        example = scoring.trial.example
        _, breakdown = grouped.setdefault(id(example), (example, []))
        breakdown.append((scoring.metric.name, scoring.score.normalized, scoring.score.reason))

    ranked: list[WeakExampleEntry] = []
    for example, breakdown in grouped.values():
        mean_score = sum(n for _, n, _ in breakdown) / len(breakdown)
        if mean_score >= 1.0:
            continue  # perfect score — no room to improve, not a "weak" example
        ranked.append((example, mean_score, breakdown))

    ranked.sort(key=lambda entry: entry[1])
    return ranked[:limit]


def _render_quality(results: RunResults) -> str:
    """Render the quality section for a single run."""
    lines = ["### Quality", ""]

    per_metric = results.per_metric()
    if per_metric:
        noise = results.replicate_noise()
        lines.extend(
            [
                "| Metric | Score | Replicate noise |",
                "| --- | --- | --- |",
            ]
        )
        for name in sorted(per_metric):
            lines.append(f"| `{name}` | {_fmt(per_metric[name])} | {_fmt(noise[name])} |")

    return "\n".join(lines)


def _render_reliability(results: RunResults) -> str:
    """Render the reliability section for a single run."""
    return "\n".join(
        [
            "### Reliability",
            "",
            f"- **Trials**: {len(results.successful_trials)} successful / "
            f"{len(results.trials)} total",
            f"- **Trial failure rate**: {results.failure_rate:.2%}",
            f"- **Scorings**: {len(results.successful_scorings)} successful / "
            f"{len(results.scorings)} total",
            f"- **Scoring failure rate**: {results.scoring_failure_rate:.2%}",
        ]
    )


def _trial_for_example(results: RunResults, example: Example) -> SuccessfulTrial | None:
    """Return a successful trial for ``example``, if one exists."""
    for trial in results.successful_trials:
        if trial.example is example:
            return trial
    return None


def _render_weak_example(
    index: int,
    example: Example,
    mean_score: float,
    breakdown: list[MetricBreakdown],
    trial: SuccessfulTrial | None,
) -> list[str]:
    """Render one weak example for the error-analysis section.

    When ``trial`` is given, the block shows the rendered prompt the LM saw and
    the program output; otherwise it falls back to the raw dataset inputs.
    Either way it lists the per-metric scores and judge reasons.
    """
    lines = [f"#### Example {index} - score {mean_score:.2f}", ""]
    if trial is not None:
        lines.extend(
            [
                "**Rendered Prompt:**",
                "",
                fence_verbatim("rendered_prompt", trial.rendered_prompt),
                "",
                "**Output:**",
                "",
                repr(trial.output),
                "",
            ]
        )
    else:
        lines.extend(
            [
                "**Inputs:**",
                "",
                f"`{example.inputs!r}`",
                "",
            ]
        )
    lines.extend(["**Quality:**", ""])
    for metric_name, normalized, reason in breakdown:
        detail = f"- `{metric_name}`: {normalized:.2f}"
        if reason:
            detail += f" — {reason}"
        lines.append(detail)
    return lines


def _render_weak_examples(
    results: RunResults, *, error_format: Literal["inputs", "rendered"] = "inputs"
) -> str:
    """Render error analysis (weakest-example detail) for a single run."""
    weak = _weakest_examples(results, _MAX_WEAK_EXAMPLES)
    lines = ["### Error Analysis", ""]
    if weak:
        for i, (example, mean_score, breakdown) in enumerate(weak, start=1):
            trial = _trial_for_example(results, example) if error_format == "rendered" else None
            lines.extend(_render_weak_example(i, example, mean_score, breakdown, trial))
    elif results.successful_scorings:
        lines.append("All examples scored perfectly.")
    else:
        lines.append("(no scores)")
    return "\n".join(lines)


def _render_telemetry(results: RunResults) -> str:
    """Render the telemetry section for a single run."""
    lines = [
        "### Telemetry",
        "",
        "Totals across successful trials only.",
        "",
        f"- **Total latency**: {results.latency:.3f} s",
        f"- **Total output tokens**: {results.output_tokens}",
        f"- **Throughput**: {results.speed:.1f} tok/s",
    ]
    divergence = results.replicate_divergence()
    if divergence is not None:
        lines.append(f"- **Replicate divergence**: {_fmt(divergence)}")
    return "\n".join(lines)


def render_run(
    results: RunResults,
    *,
    telemetry: bool = True,
    error_format: Literal["inputs", "rendered"] | None = "inputs",
) -> str:
    """Render a single run as markdown sections.

    Args:
        results: The run to render.
        telemetry: Omit the telemetry section when ``False``.
        error_format: How the error-analysis section shows each weak example — raw
            ``Example.inputs`` (``"inputs"``) or the rendered prompt and program
            output from its trial (``"rendered"``). ``None`` omits the error-analysis
            section entirely (quality and reliability still render).
    """
    sections: list[str] = [
        _render_quality(results),
        _render_reliability(results),
    ]
    if error_format is not None:
        sections.append(_render_weak_examples(results, error_format=error_format))
    if telemetry:
        sections.append(_render_telemetry(results))
    return "\n\n".join(sections)


def _signed(delta: float) -> str:
    """Format a score delta with an explicit sign, e.g. ``+0.09`` / ``-0.01``."""
    return f"{delta:+.2f}"


def _render_step_heading(step: Step, index: int, baseline_score: float, is_best: bool) -> str:
    """Build the per-step ``##`` heading for :func:`render_history`."""
    role = "baseline" if index == 0 else "candidate"
    parts = [f"## Step {index} — {role} · score {step.score:.2f}"]
    if index > 0:
        parts.append(f"Δ {_signed(step.score - baseline_score)} vs baseline")
    if is_best:
        parts.append("⭐ best")
    return " · ".join(parts)


def _render_step_intent(thinking: Thinking) -> str:
    """Compact rationale for a proposed step (hypothesis + edit plan)."""
    return "\n\n".join(
        [
            "### Intent",
            "",
            f"**Hypothesis:** {thinking.improvement_hypothesis}",
            "",
            f"**Edit plan:** {thinking.edit_plan}",
        ]
    )


def render_history(steps: list[Step]) -> str:
    """Render an optimization trajectory as markdown.

    Returns:
        Human-readable string; empty input yields ``""``.
    """
    if not steps:
        return ""

    baseline_score = steps[0].score
    best_index = max(range(len(steps)), key=lambda i: steps[i].score)
    # Error analysis only earns its keep on the checkpoints the proposer is asked
    # to act on: the best one it may refine and the latest one it just tried, both
    # with rendered prompts. Superseded candidates omit it entirely — their score
    # delta and template already carry the signal, and stale per-example detail
    # just bloats the trajectory. ``best`` and ``last`` collapse when they coincide.
    detailed = {best_index, len(steps) - 1}

    step_blocks: list[str] = []
    for i, step in enumerate(steps):
        error_format: Literal["inputs", "rendered"] | None = "rendered" if i in detailed else None
        sections = [_render_step_heading(step, i, baseline_score, is_best=i == best_index)]
        if i > 0 and step.thinking is not None:
            sections.append(_render_step_intent(step.thinking))
        sections.extend(
            [
                "### Template",
                "",
                fence_verbatim("template", step.prompt_template),
                render_run(step.result, telemetry=False, error_format=error_format),
            ]
        )
        step_blocks.append("\n\n".join(sections))

    return "\n\n---\n\n".join(step_blocks)
