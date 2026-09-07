"""Job lifecycle: background threads, queues, SSE event bridging, and on-disk jobs."""

from __future__ import annotations

import asyncio
import json
import threading
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any

from promptuna.evaluate import Metric, Scoring, stream_evaluate
from promptuna.jobs import (
    JobArchive,
    JobConfig,
    JobKind,
    JobRecord,
    JobStatus,
    get_jobs_root,
    list_job_manifests,
    load_job,
    load_manifest,
    load_summary,
    stream_job,
)
from promptuna.jobs import (
    delete_job as _delete_job_dir,
)
from promptuna.optimize import Proposal, Step, stream_optimize
from promptuna.program import Example, Experiment
from promptuna.run import Trial, stream_run

_WAIT_TIMEOUT_SECONDS = 1.0

StreamSource = Callable[[], Iterator[Trial | Scoring | Step | Proposal]]


@dataclass
class JobState:
    """In-memory job record for one streaming job."""

    job_id: str
    kind: JobKind
    archive: JobArchive
    status: JobStatus = "running"
    events: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None
    _cond: threading.Condition = field(default_factory=threading.Condition)


_jobs: dict[str, JobState] = {}
_jobs_lock = threading.Lock()


def _has_running_job() -> bool:
    return any(job.status == "running" for job in _jobs.values())


def _append_event(job: JobState, envelope: dict[str, Any]) -> None:
    with job._cond:
        job.events.append(envelope)
        job._cond.notify_all()


def _finish_job(job: JobState) -> None:
    with job._cond:
        job._cond.notify_all()


def start_run_job(
    *,
    config: JobConfig,
    experiment: Experiment,
    examples: list[Example],
    workers: int,
) -> str:
    """Start a run job and return its ``job_id``."""
    return _start_job(
        "run",
        lambda: stream_run(experiment, examples, workers=workers),
        config=config,
    )


def start_evaluate_job(
    *,
    config: JobConfig,
    experiment: Experiment,
    examples: list[Example],
    metrics: list[Metric],
    workers: int,
) -> str:
    """Start an evaluate job and return its ``job_id``."""
    return _start_job(
        "evaluate",
        lambda: stream_evaluate(experiment, examples, metrics, workers=workers),
        config=config,
    )


def start_optimize_job(
    *,
    config: JobConfig,
    experiment: Experiment,
    examples: list[Example],
    metrics: list[Metric],
    workers: int,
    steps: int,
    proposer_model: str,
) -> str:
    """Start an optimize job and return its ``job_id``."""
    return _start_job(
        "optimize",
        lambda: stream_optimize(
            experiment,
            examples,
            metrics,
            proposer_model=proposer_model,
            steps=steps,
            workers=workers,
        ),
        config=config,
    )


def _start_job(kind: JobKind, build_source: StreamSource, *, config: JobConfig) -> str:
    with _jobs_lock:
        if _has_running_job():
            raise ConflictError("another job is already running")
        job_id = str(uuid.uuid4())
        archive = JobArchive.open(get_jobs_root(), job_id, config)
        job = JobState(job_id=job_id, kind=kind, archive=archive)
        _jobs[job_id] = job

    thread = threading.Thread(
        target=_job_thread,
        args=(job, build_source),
        daemon=True,
        name=f"promptuna-{kind}-{job_id[:8]}",
    )
    thread.start()
    return job_id


class ConflictError(Exception):
    """Raised when a second job is started while one is running."""


class JobNotFoundError(Exception):
    """Raised when ``job_id`` is unknown."""


def get_job(job_id: str) -> JobState:
    """Return job state or raise :class:`JobNotFoundError`."""
    try:
        return _jobs[job_id]
    except KeyError as exc:
        raise JobNotFoundError(job_id) from exc


def _job_thread(job: JobState, build_source: StreamSource) -> None:
    try:
        for envelope in stream_job(job.archive, build_source()):
            _append_event(job, envelope)
        job.status = "done"
    except Exception as exc:
        job.status = "error"
        job.error = str(exc)
    finally:
        _finish_job(job)


async def stream_job_events(job_id: str):
    """Async generator yielding SSE ``data:`` lines for ``job_id``."""
    job = get_job(job_id)
    offset = 0
    while True:
        batch, done = await asyncio.to_thread(_wait_for_events, job, offset)
        for envelope in batch:
            yield f"data: {json.dumps(envelope)}\n\n"
            offset += 1
        if done and offset >= len(job.events):
            break


def _wait_for_events(job: JobState, offset: int) -> tuple[list[dict[str, Any]], bool]:
    with job._cond:
        while offset >= len(job.events) and job.status == "running":
            job._cond.wait(timeout=_WAIT_TIMEOUT_SECONDS)
        return job.events[offset:], job.status != "running"


def reset_jobs() -> None:
    """Clear all jobs (tests only)."""
    with _jobs_lock:
        _jobs.clear()


def list_jobs() -> list[dict[str, Any]]:
    """Return manifests for all on-disk jobs, newest-first."""
    return list_job_manifests(get_jobs_root())


def delete_job(job_id: str) -> None:
    """Delete an on-disk job. Refuse while it is still running."""
    with _jobs_lock:
        job = _jobs.get(job_id)
        if job is not None and job.status == "running":
            raise ConflictError("job is still running")
        _delete_job_dir(get_jobs_root(), job_id)
        _jobs.pop(job_id, None)


def load_job_detail(job_id: str) -> JobRecord:
    """Load a job from memory when active, otherwise from disk."""
    try:
        job = get_job(job_id)
    except JobNotFoundError:
        return load_job(get_jobs_root(), job_id)

    manifest = load_manifest(job.archive.job_dir)
    summary = None if job.status == "running" else load_summary(job.archive.job_dir)
    return JobRecord(manifest=manifest, events=list(job.events), summary=summary)
