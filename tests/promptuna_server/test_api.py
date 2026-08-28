"""Tests for the promptuna-server HTTP API."""

from __future__ import annotations

import json
import threading
from functools import partial
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from helpers import fake_complete
from promptuna_server import jobs
from promptuna_server.main import app

from promptuna.jobs import get_jobs_root, load_job
from promptuna.optimize import Proposal, stream_optimize
from promptuna.projects import set_projects_root
from promptuna.run import stream_run as library_stream_run

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "test_project"


@pytest.fixture(autouse=True)
def isolated_jobs():
    jobs.reset_jobs()
    yield
    jobs.reset_jobs()


@pytest.fixture(autouse=True)
def projects_root():
    set_projects_root(FIXTURES.parent)
    yield
    set_projects_root(None)


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def fake_complete_patch():
    with patch("lmdk.complete", side_effect=fake_complete):
        yield


def _read_sse_events(response) -> list[dict]:
    events: list[dict] = []
    for line in response.iter_lines():
        if line.startswith("data: "):
            events.append(json.loads(line.removeprefix("data: ")))
    return events


def _wait_for_events(client: TestClient, job_id: str) -> list[dict]:
    with client.stream("GET", f"/api/jobs/{job_id}/events") as response:
        assert response.status_code == 200
        return _read_sse_events(response)


def test_health(client: TestClient):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_catalog_lists_fixture_project_names(client: TestClient):
    response = client.get("/api/catalog")
    assert response.status_code == 200
    body = response.json()
    assert body["projects_root"] == str(FIXTURES.parent.resolve())
    assert body["projects"] == [
        {
            "name": "test_project",
            "programs": ["echo"],
            "metrics": ["exact_match"],
            "prompts": ["baseline"],
            "datasets": ["dev"],
        }
    ]


def test_concurrent_job_returns_409(client: TestClient, fake_complete_patch):
    started = threading.Event()
    release = threading.Event()

    def blocking_stream_run(*args, **kwargs):
        started.set()
        assert release.wait(timeout=2)
        yield from library_stream_run(*args, **kwargs)

    with patch("promptuna_server.jobs.stream_run", side_effect=blocking_stream_run):
        first = client.post(
            "/api/run",
            json={
                "project": "test_project",
                "program": "echo",
                "prompt": "baseline",
                "model": "test:model",
                "examples": "dev",
                "workers": 1,
            },
        )
        assert first.status_code == 200
        job_id = first.json()["job_id"]
        assert started.wait(timeout=2)

        second = client.post(
            "/api/run",
            json={
                "project": "test_project",
                "program": "echo",
                "prompt": "baseline",
                "model": "test:model",
                "examples": "dev",
                "workers": 1,
            },
        )
        assert second.status_code == 409
        release.set()

    events = _wait_for_events(client, job_id)
    assert events
    assert all(event["job_id"] == job_id for event in events)
    assert all(event["type"] == "trial" for event in events)


def test_run_streams_trial_events(client: TestClient, fake_complete_patch):
    start = client.post(
        "/api/run",
        json={
            "project": "test_project",
            "program": "echo",
            "prompt": "baseline",
            "model": "test:model",
            "examples": "dev",
            "workers": 2,
        },
    )
    job_id = start.json()["job_id"]
    events = _wait_for_events(client, job_id)

    assert [event["type"] for event in events] == ["trial", "trial"]
    assert all(event["step_index"] == 0 for event in events)
    assert events[0]["seq"] == 0
    assert events[1]["seq"] == 1


def test_run_repeats_multiplies_trials(client: TestClient, fake_complete_patch):
    start = client.post(
        "/api/run",
        json={
            "project": "test_project",
            "program": "echo",
            "prompt": "baseline",
            "model": "test:model",
            "examples": "dev",
            "workers": 1,
            "repeats": 2,
        },
    )
    job_id = start.json()["job_id"]
    events = _wait_for_events(client, job_id)

    assert [event["type"] for event in events] == ["trial"] * 4
    assert sorted(event["payload"]["replicate"] for event in events) == [0, 0, 1, 1]
    detail = client.get(f"/api/jobs/{job_id}").json()
    assert detail["manifest"]["repeats"] == 2


def test_evaluate_streams_trial_and_scoring_events(client: TestClient, fake_complete_patch):
    start = client.post(
        "/api/evaluate",
        json={
            "project": "test_project",
            "program": "echo",
            "prompt": "baseline",
            "model": "test:model",
            "examples": "dev",
            "metrics": ["exact_match"],
            "workers": 1,
        },
    )
    job_id = start.json()["job_id"]
    events = _wait_for_events(client, job_id)

    types = [event["type"] for event in events]
    assert types.count("trial") == 2
    assert types.count("scoring") == 2
    assert "step" not in types
    assert all(event["step_index"] == 0 for event in events)


def test_optimize_streams_checkpoint_events(client: TestClient, fake_complete_factory):
    def proposer(steps, model):
        return Proposal(thinking=None, prompt_template="Improved: {{ question }}")

    with (
        fake_complete_factory("wrong"),
        patch(
            "promptuna_server.jobs.stream_optimize",
            partial(stream_optimize, proposer=proposer),
        ),
    ):
        start = client.post(
            "/api/optimize",
            json={
                "project": "test_project",
                "program": "echo",
                "prompt": "baseline",
                "model": "test:model",
                "examples": "dev",
                "metrics": ["exact_match"],
                "workers": 1,
                "steps": 1,
                "proposer_model": "test:model",
            },
        )
        job_id = start.json()["job_id"]
        events = _wait_for_events(client, job_id)

    types = [event["type"] for event in events]
    assert "proposal" in types
    assert "trial" in types
    assert "scoring" in types
    assert "step" in types
    assert types.index("proposal") < types.index("trial")
    assert types.index("trial") < types.index("step")

    step_indices = [event["step_index"] for event in events if event["type"] == "step"]
    assert step_indices == [0, 1]

    proposal_indices = [event["step_index"] for event in events if event["type"] == "proposal"]
    assert proposal_indices == [0, 1]


def test_unknown_job_events_returns_404(client: TestClient):
    response = client.get("/api/jobs/does-not-exist/events")
    assert response.status_code == 404


def test_run_persists_archive(client: TestClient, fake_complete_patch):
    start = client.post(
        "/api/run",
        json={
            "project": "test_project",
            "program": "echo",
            "prompt": "baseline",
            "model": "test:model",
            "examples": "dev",
            "workers": 1,
        },
    )
    job_id = start.json()["job_id"]
    events = _wait_for_events(client, job_id)

    record = load_job(get_jobs_root(), job_id)
    assert record.manifest["kind"] == "run"
    assert record.manifest["status"] == "done"
    assert record.events == events
    assert record.summary is not None
    assert record.summary["trial_count"] == len(events)


def test_late_sse_subscriber_replays_completed_job(client: TestClient, fake_complete_patch):
    start = client.post(
        "/api/run",
        json={
            "project": "test_project",
            "program": "echo",
            "prompt": "baseline",
            "model": "test:model",
            "examples": "dev",
            "workers": 1,
        },
    )
    job_id = start.json()["job_id"]
    first_events = _wait_for_events(client, job_id)

    second_events = _wait_for_events(client, job_id)
    assert second_events == first_events


def test_list_jobs_returns_persisted_manifests(client: TestClient, fake_complete_patch):
    start = client.post(
        "/api/run",
        json={
            "project": "test_project",
            "program": "echo",
            "prompt": "baseline",
            "model": "test:model",
            "examples": "dev",
            "workers": 1,
        },
    )
    job_id = start.json()["job_id"]
    _wait_for_events(client, job_id)

    response = client.get("/api/jobs")
    assert response.status_code == 200
    item = next(item for item in response.json()["jobs"] if item["job_id"] == job_id)
    assert item["kind"] == "run"
    assert item["status"] == "done"
    assert item["project"] == "test_project"


def test_get_job_returns_manifest_events_and_summary(client: TestClient, fake_complete_patch):
    start = client.post(
        "/api/evaluate",
        json={
            "project": "test_project",
            "program": "echo",
            "prompt": "baseline",
            "model": "test:model",
            "examples": "dev",
            "metrics": ["exact_match"],
            "workers": 1,
        },
    )
    job_id = start.json()["job_id"]
    events = _wait_for_events(client, job_id)

    response = client.get(f"/api/jobs/{job_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["manifest"]["job_id"] == job_id
    assert body["manifest"]["kind"] == "evaluate"
    assert body["events"] == events
    assert body["summary"] is not None
    trial_events = [event for event in events if event["type"] == "trial"]
    assert body["summary"]["trial_count"] == len(trial_events)


def test_get_unknown_job_returns_404(client: TestClient):
    response = client.get("/api/jobs/does-not-exist")
    assert response.status_code == 404
