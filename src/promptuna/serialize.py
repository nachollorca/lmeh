"""Serialize streaming job events to JSON-safe envelopes.

Each yielded ``Trial``, ``Scoring``, ``Step``, or ``Proposal`` is wrapped in a stable envelope
suitable for SSE transport, on-disk job persistence (:mod:`promptuna.jobs`), and
unit tests. Fatal job failures use :func:`serialize_error`. Callers assign ``seq``
and ``step_index`` as events are emitted. ``step`` events appear only on optimize
jobs.
"""

import hashlib
import json
from typing import Any, Literal

from lmdk import CompletionRequest, CompletionResponse, Message
from pydantic import BaseModel

from promptuna.evaluate import (
    FailedScoring,
    LLMJudgeMetric,
    Metric,
    ProgrammaticMetric,
    Scoring,
    SuccessfulScoring,
)
from promptuna.optimize import Proposal, Step
from promptuna.program import Example
from promptuna.run import FailedTrial, SuccessfulTrial, Trial

EventType = Literal["trial", "scoring", "step", "proposal", "error"]


def serialize_event(
    event: Trial | Scoring | Step | Proposal,
    *,
    job_id: str,
    seq: int,
    step_index: int,
) -> dict[str, Any]:
    """Convert one stream item into a JSON-safe event envelope."""
    if isinstance(event, (SuccessfulTrial, FailedTrial)):
        event_type: EventType = "trial"
        payload = _serialize_trial(event)
    elif isinstance(event, (SuccessfulScoring, FailedScoring)):
        event_type = "scoring"
        payload = _serialize_scoring(event)
    elif isinstance(event, Step):
        event_type = "step"
        payload = _serialize_step(event)
    elif isinstance(event, Proposal):
        event_type = "proposal"
        payload = _serialize_proposal(event)
    else:
        raise TypeError(f"unsupported event type: {type(event)!r}")

    return {
        "seq": seq,
        "job_id": job_id,
        "step_index": step_index,
        "type": event_type,
        "payload": payload,
    }


def serialize_error(
    *,
    job_id: str,
    seq: int,
    message: str,
    step_index: int = 0,
) -> dict[str, Any]:
    """Build a JSON-safe error envelope for fatal job failures."""
    return {
        "seq": seq,
        "job_id": job_id,
        "step_index": step_index,
        "type": "error",
        "payload": {"message": message},
    }


def _example_id(example: Example) -> str:
    """Stable identifier for a dataset row, shared by all of its replicates."""
    key = json.dumps(
        {"inputs": example.inputs, "reference": example.reference},
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def _trial_id(trial: Trial) -> str:
    """Stable identifier for one ``(example, replicate)`` within one run."""
    return f"{_example_id(trial.example)}:{trial.replicate}"


def _exception_error(error: Exception) -> dict[str, str]:
    return {"type": type(error).__name__, "message": str(error)}


def _serialize_example(example: Example) -> dict[str, Any]:
    return {
        "inputs": _serialize_value(example.inputs),
        "reference": _serialize_value(example.reference),
    }


def _serialize_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, BaseModel):
        return value.model_dump()
    if isinstance(value, dict):
        return {str(key): _serialize_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_serialize_value(item) for item in value]
    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        return {"value": repr(value), "serialization": "fallback"}


def _serialize_output(output: Any) -> Any:
    serialized = _serialize_value(output)
    if isinstance(serialized, dict) and serialized.get("serialization") == "fallback":
        return serialized
    try:
        json.dumps(serialized)
        return serialized
    except (TypeError, ValueError):
        return {"value": repr(output), "serialization": "fallback"}


def _serialize_message(message: Message) -> dict[str, str]:
    return {"role": message.role, "content": message.content}


def _serialize_output_schema(schema: type[BaseModel] | None) -> dict[str, Any] | None:
    if schema is None:
        return None
    if issubclass(schema, BaseModel):
        return schema.model_json_schema()
    return {"type": schema.__name__, "serialization": "fallback"}


def _serialize_completion_request(request: CompletionRequest) -> dict[str, Any]:
    return {
        "model_id": request.model_id,
        "prompt": [_serialize_message(message) for message in request.prompt],
        "system_instruction": request.system_instruction,
        "output_schema": _serialize_output_schema(request.output_schema),
        "generation_kwargs": _serialize_value(request.generation_kwargs),
    }


def _serialize_completion_response(response: CompletionResponse) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "content": response.content,
        "input_tokens": response.input_tokens,
        "output_tokens": response.output_tokens,
        "latency": response.latency,
    }
    if response.parsed is not None:
        payload["parsed"] = _serialize_value(response.parsed)
    return payload


def _serialize_trial(trial: Trial) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "status": "success" if isinstance(trial, SuccessfulTrial) else "failed",
        "trial_id": _trial_id(trial),
        "example_id": _example_id(trial.example),
        "example": _serialize_example(trial.example),
        "replicate": trial.replicate,
    }
    if isinstance(trial, SuccessfulTrial):
        payload["output"] = _serialize_output(trial.output)
        telemetry: dict[str, Any] = {}
        if trial.request is not None:
            telemetry["rendered_prompt"] = trial.rendered_prompt
            telemetry["request"] = _serialize_completion_request(trial.request)
        if trial.response is not None:
            telemetry["response"] = _serialize_completion_response(trial.response)
        if telemetry:
            payload["telemetry"] = telemetry
    else:
        payload["error"] = _exception_error(trial.error)
    return payload


def _serialize_metric(metric: Metric) -> dict[str, str]:
    payload = {"name": metric.name, "description": metric.description}
    if isinstance(metric, ProgrammaticMetric):
        payload["kind"] = "programmatic"
    elif isinstance(metric, LLMJudgeMetric):
        payload["kind"] = "llm_judge"
    return payload


def _serialize_scoring(scoring: Scoring) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "trial_id": _trial_id(scoring.trial),
        "example_id": _example_id(scoring.trial.example),
        "metric": _serialize_metric(scoring.metric),
        "replicate": scoring.replicate,
    }
    if isinstance(scoring, SuccessfulScoring):
        payload["status"] = "success"
        payload["score"] = {
            "raw": _serialize_value(scoring.score.raw),
            "normalized": scoring.score.normalized,
            "reason": scoring.score.reason,
        }
    else:
        payload["status"] = "failed"
        payload["error"] = _exception_error(scoring.error)
    return payload


def _serialize_aggregate(aggregate: Any) -> dict[str, float | int]:
    return {"mean": aggregate.mean, "sd": aggregate.sd, "n": aggregate.n}


def _serialize_proposal(proposal: Proposal) -> dict[str, Any]:
    return {
        "prompt_template": proposal.prompt_template,
        "thinking": proposal.thinking.model_dump() if proposal.thinking is not None else None,
        "advice": proposal.advice,
    }


def _serialize_step(step: Step) -> dict[str, Any]:
    result = step.result
    payload: dict[str, Any] = {
        "score": step.score,
        "prompt_template": step.prompt_template,
        "thinking": step.thinking.model_dump() if step.thinking is not None else None,
        "advice": step.advice,
        "summary": {
            "overall": _serialize_aggregate(result.overall),
            "per_metric": {
                name: _serialize_aggregate(aggregate)
                for name, aggregate in result.per_metric().items()
            },
            "failure_rate": result.failure_rate,
            "scoring_failure_rate": result.scoring_failure_rate,
        },
    }
    return payload
