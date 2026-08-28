"""Tests for promptuna.serialize."""

import json
from typing import Literal

import pytest
from helpers import make_run_results, make_trial
from pydantic import BaseModel

from promptuna.evaluate import FailedScoring, Score, SuccessfulScoring
from promptuna.optimize import Proposal, Step, Thinking, stream_optimize
from promptuna.run import FailedTrial
from promptuna.serialize import serialize_error, serialize_event


class _BlockSchema(BaseModel):
    confidence: Literal["weak", "decent", "strong"]


def _assert_json_roundtrip(payload: dict) -> None:
    encoded = json.dumps(payload)
    decoded = json.loads(encoded)
    assert decoded == payload


def _sample_thinking() -> Thinking:
    return Thinking(
        reinstate_goal="Maximize headline score.",
        trajectory_summary="Baseline weak; step 1 improved.",
        failure_analysis="Model skips reasoning.",
        what_works="Explicit step-by-step instructions.",
        what_hurts="Overlong prompts add noise.",
        improvement_hypothesis="Shorter rubric should reduce confusion.",
        edit_plan="Refine best checkpoint; tighten scoring criteria.",
    )


def test_serialize_error():
    event = serialize_error(job_id="job-1", seq=5, message="worker crashed")

    assert event == {
        "seq": 5,
        "job_id": "job-1",
        "step_index": 0,
        "type": "error",
        "payload": {"message": "worker crashed"},
    }
    _assert_json_roundtrip(event)


def test_serialize_successful_trial(experiment, example, exact_match_metric):
    trial = make_trial(example, output="4", rendered_prompt="Answer: 2+2?")

    event = serialize_event(trial, job_id="run-1", seq=0, step_index=0)

    assert event["seq"] == 0
    assert event["job_id"] == "run-1"
    assert event["step_index"] == 0
    assert event["type"] == "trial"
    payload = event["payload"]
    assert payload["status"] == "success"
    assert payload["output"] == "4"
    assert payload["example"]["inputs"] == example.inputs
    assert payload["example"]["reference"] == example.reference
    assert payload["telemetry"]["rendered_prompt"] == "Answer: 2+2?"
    assert payload["telemetry"]["request"]["model_id"] == "model"
    assert payload["telemetry"]["response"]["content"] == "4"
    _assert_json_roundtrip(event)


def test_serialize_failed_trial(example):
    trial = FailedTrial(example=example, error=ValueError("boom"), replicate=1)

    event = serialize_event(trial, job_id="run-1", seq=1, step_index=0)

    payload = event["payload"]
    assert payload["status"] == "failed"
    assert payload["replicate"] == 1
    assert payload["error"] == {"type": "ValueError", "message": "boom"}
    assert "telemetry" not in payload
    _assert_json_roundtrip(event)


def test_serialize_successful_scoring(experiment, example, exact_match_metric):
    trial = make_trial(example)
    scoring = SuccessfulScoring(
        trial=trial,
        metric=exact_match_metric,
        score=Score(raw=1.0, normalized=1.0, reason="exact match"),
    )

    event = serialize_event(scoring, job_id="run-1", seq=2, step_index=0)

    payload = event["payload"]
    assert event["type"] == "scoring"
    assert payload["status"] == "success"
    trial_event = serialize_event(trial, job_id="x", seq=0, step_index=0)
    assert payload["trial_id"] == trial_event["payload"]["trial_id"]
    assert payload["metric"] == {
        "name": "exact_match",
        "description": "Output must match the reference answer.",
        "kind": "programmatic",
    }
    assert payload["score"] == {
        "raw": 1.0,
        "normalized": 1.0,
        "reason": "exact match",
    }
    _assert_json_roundtrip(event)


def test_serialize_failed_scoring(experiment, example, exact_match_metric):
    trial = make_trial(example)
    scoring = FailedScoring(
        trial=trial,
        metric=exact_match_metric,
        error=RuntimeError("judge crashed"),
    )

    event = serialize_event(scoring, job_id="run-1", seq=3, step_index=0)

    payload = event["payload"]
    assert payload["status"] == "failed"
    assert payload["error"] == {"type": "RuntimeError", "message": "judge crashed"}
    assert "score" not in payload
    _assert_json_roundtrip(event)


def test_serialize_step(experiment, examples, exact_match_metric):
    result = make_run_results(experiment, examples[:1], exact_match_metric, scores=[0.8])
    step = Step(
        prompt_template="Answer: {{ question }}",
        result=result,
        thinking=_sample_thinking(),
    )

    event = serialize_event(step, job_id="run-1", seq=4, step_index=0)

    payload = event["payload"]
    assert event["type"] == "step"
    assert payload["score"] == pytest.approx(0.8)
    assert payload["prompt_template"] == "Answer: {{ question }}"
    assert payload["thinking"]["improvement_hypothesis"] == (
        "Shorter rubric should reduce confusion."
    )
    assert payload["summary"]["overall"]["mean"] == pytest.approx(0.8)
    assert payload["summary"]["per_metric"]["exact_match"]["mean"] == pytest.approx(0.8)
    _assert_json_roundtrip(event)


def test_serialize_step_without_thinking(experiment, examples, exact_match_metric):
    result = make_run_results(experiment, examples[:1], exact_match_metric, scores=[0.5])
    step = Step(prompt_template="baseline", result=result)

    event = serialize_event(step, job_id="run-1", seq=0, step_index=0)

    assert event["payload"]["thinking"] is None
    _assert_json_roundtrip(event)


def test_serialize_proposal():
    proposal = Proposal(
        thinking=_sample_thinking(),
        prompt_template="Answer: {{ question }}",
        advice="Expand the output schema to include confidence.",
    )

    event = serialize_event(proposal, job_id="run-1", seq=0, step_index=1)

    assert event["type"] == "proposal"
    assert event["step_index"] == 1
    assert event["payload"]["prompt_template"] == "Answer: {{ question }}"
    assert event["payload"]["advice"] == "Expand the output schema to include confidence."
    assert event["payload"]["thinking"]["edit_plan"] == (
        "Refine best checkpoint; tighten scoring criteria."
    )
    _assert_json_roundtrip(event)


def test_serialize_proposal_without_advice():
    proposal = Proposal(thinking=None, prompt_template="baseline")

    event = serialize_event(proposal, job_id="run-1", seq=0, step_index=0)

    assert event["payload"]["advice"] is None
    _assert_json_roundtrip(event)


def test_serialize_proposal_without_thinking():
    proposal = Proposal(thinking=None, prompt_template="baseline")

    event = serialize_event(proposal, job_id="run-1", seq=0, step_index=0)

    assert event["payload"]["thinking"] is None
    _assert_json_roundtrip(event)


def test_serialize_output_schema_in_trial_telemetry(experiment, example):
    trial = make_trial(example, output_schema=_BlockSchema)

    event = serialize_event(trial, job_id="run-1", seq=0, step_index=0)

    schema = event["payload"]["telemetry"]["request"]["output_schema"]
    assert schema["properties"]["confidence"]["enum"] == ["weak", "decent", "strong"]
    _assert_json_roundtrip(event)


def test_serialize_non_json_output_uses_fallback(example):
    class CustomOutput:
        def __repr__(self) -> str:
            return "CustomOutput()"

    trial = make_trial(example, output=CustomOutput())

    event = serialize_event(trial, job_id="run-1", seq=0, step_index=0)

    assert event["payload"]["output"] == {
        "value": "CustomOutput()",
        "serialization": "fallback",
    }
    _assert_json_roundtrip(event)


def test_stream_optimize_events_are_json_serializable(
    experiment, examples, exact_match_metric, fake_complete_factory
):
    def proposer(steps, model):
        return Proposal(thinking=None, prompt_template="Improved: {{ question }}")

    with fake_complete_factory("wrong"):
        step_index = 0
        for seq, item in enumerate(
            stream_optimize(
                experiment=experiment,
                examples=examples[:1],
                metrics=[exact_match_metric],
                proposer_model=experiment.model,
                steps=1,
                proposer=proposer,
            )
        ):
            event = serialize_event(item, job_id="test-run", seq=seq, step_index=step_index)
            if isinstance(item, Step):
                step_index += 1
            _assert_json_roundtrip(event)
            assert event["type"] in {"trial", "scoring", "step", "proposal"}

        assert step_index == 2


def test_replicates_share_example_id_but_not_trial_id(example):
    first = serialize_event(make_trial(example), job_id="j", seq=0, step_index=0)["payload"]
    second = serialize_event(make_trial(example, replicate=1), job_id="j", seq=1, step_index=0)[
        "payload"
    ]

    assert first["example_id"] == second["example_id"]
    assert first["trial_id"] != second["trial_id"]
    assert first["trial_id"].startswith(first["example_id"])
