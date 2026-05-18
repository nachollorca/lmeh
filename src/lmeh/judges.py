"""Built-in LLM judges.

Provides ``default_llm_judge`` — a batteries-included scorer that:

1. Builds a pydantic output schema from the metric's ``Scale``.
2. Renders the judge prompt template with the trial's context.
3. Calls the judge model with structured output.
4. Returns a ``Score`` populated from the parsed response.

The default template (``default_judge_template`` in ``lmeh.datatypes``)
expects these variables, which the default judge always provides:

- ``RENDERED_PROMPT``: the exact prompt the target sent to the model.
- ``OUTPUT``: the target's post-processed output (stringified).
- ``REFERENCE``: ``example.reference`` (may be ``None``; the default
  template wraps this block in an ``{% if REFERENCE %}``).
- ``METRIC``: ``metric.description`` — what the judge is evaluating for.

Users who need different behavior should write their own scorer matching
the ``LLMJudgeScorer`` protocol.
"""

from typing import Any, Literal

from lmdk import complete, render_template
from pydantic import BaseModel, ConfigDict, create_model

from lmeh.datatypes import Example, LLMJudgeMetric, LMConfig, Ordinal, Range, Scale, Score


def _schema_for_scale(scale: Scale) -> type[BaseModel]:
    """Build a ``{raw, reason}`` pydantic schema typed against ``scale``.

    - ``Range`` → ``raw: float``.
    - ``Ordinal`` → ``raw: Literal[<levels>]`` so the model is forced to
      pick one of the allowed values.
    - Anything else → ``raw: Any`` (best effort; harness scale validation
      still runs on the returned value).
    """
    if isinstance(scale, Range):
        raw_ann: Any = float
    elif isinstance(scale, Ordinal):
        raw_ann = Literal[tuple(scale.levels)]  # ty: ignore[invalid-type-form]
    else:
        raw_ann = Any
    return create_model(
        "JudgeOutput",
        __config__=ConfigDict(extra="forbid"),
        raw=(raw_ann, ...),
        reason=(str, ...),
    )


def default_llm_judge(
    output: Any,
    example: Example,
    metric: LLMJudgeMetric,
    config: LMConfig,
    rendered_prompt: str,
) -> Score:
    """Render the judge template, call the model, return a ``Score``.

    The output schema is derived from ``metric.scale``. Any error (template
    rendering, model call, schema validation) propagates so the harness
    records a ``FailedScoring`` rather than silently producing a bad score.
    """
    schema = _schema_for_scale(metric.scale)
    prompt = render_template(
        template=metric.prompt_template,
        RENDERED_PROMPT=rendered_prompt,
        OUTPUT=str(output),
        REFERENCE=example.reference,
        METRIC=metric.description,
    )
    response = complete(
        model=config.model,
        prompt=prompt,
        output_schema=schema,
        generation_kwargs=config.generation_kwargs,
    )
    parsed = response.parsed
    assert parsed is not None, "judge model returned no structured output"
    return Score(raw=parsed.raw, reason=parsed.reason)
