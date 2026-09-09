"""Persist streaming job output on disk.

Server and CLI surfaces write under the active projects workspace:

``<projects_root>/jobs/<job_id>/manifest.json`` — job config snapshot (references, not code).
``<projects_root>/jobs/<job_id>/events.jsonl`` — append-only
:func:`~promptuna.serialize.serialize_event` envelopes, one JSON object per line.
``<projects_root>/jobs/<job_id>/summary.json`` — denormalized rollup written when the job
finishes.

The library surface (plain Python imports, no on-disk project layout) can opt in via
:func:`stream_job` and :func:`get_library_jobs_root` (``<cwd>/.promptuna_jobs/``).

Job directories are optimized for durable read-back and reporting, not perfect re-execution.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import traceback
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Any, Literal

from promptuna.evaluate import Scoring, content_divergence
from promptuna.optimize import Proposal, Step
from promptuna.projects import get_projects_root
from promptuna.run import Trial
from promptuna.serialize import serialize_error, serialize_event

SCHEMA_VERSION = 1
_MANIFEST_NAME = "manifest.json"
_EVENTS_NAME = "events.jsonl"
_SUMMARY_NAME = "summary.json"
LIBRARY_JOBS_DIR = ".promptuna_jobs"
WORKSPACE_JOBS_DIR = "jobs"

JobKind = Literal["run", "evaluate", "optimize"]
JobStatus = Literal["running", "done", "error"]


def get_jobs_root() -> Path:
    """Return ``<projects_root>/jobs`` for server and CLI surfaces."""
    return get_projects_root() / WORKSPACE_JOBS_DIR


def get_library_jobs_root() -> Path:
    """Return ``<cwd>/.promptuna_jobs`` for library-surface jobs."""
    return Path.cwd() / LIBRARY_JOBS_DIR


def stream_job(
    archive: JobArchive,
    source: Iterator[Trial | Scoring | Step | Proposal],
) -> Iterator[dict[str, Any]]:
    """Persist one streaming job and yield serialized event envelopes.

    Each item from ``source`` is wrapped via :func:`~promptuna.serialize.serialize_event`,
    appended to ``archive``, and yielded. On normal completion the archive is finalized
    with status ``done``. On failure an error envelope is appended, the archive is
    finalized with status ``error``, the error envelope is yielded, and the exception
    is re-raised.

    Workspace surfaces (server, CLI) call this by default. Library users opt in by
    opening a :class:`JobArchive` (often under :func:`get_library_jobs_root`) and
    passing a core stream such as :func:`~promptuna.run.stream_run`.
    """
    job_id = archive.job_id
    seq = 0
    step_index = 0
    try:
        for item in source:
            envelope = serialize_event(item, job_id=job_id, seq=seq, step_index=step_index)
            archive.append_event(envelope)
            yield envelope
            seq += 1
            if isinstance(item, Step):
                step_index += 1
        archive.finalize("done")
    except Exception as exc:
        stacktrace = "".join(traceback.format_exception(exc))
        error_envelope = serialize_error(
            job_id=job_id,
            seq=seq,
            message=str(exc),
            stacktrace=stacktrace,
            step_index=step_index,
        )
        archive.append_event(error_envelope)
        archive.finalize("error", error=str(exc), stacktrace=stacktrace)
        yield error_envelope
        raise


def sha256_file(path: Path) -> str:
    """Return the SHA-256 hex digest of a file."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _promptuna_version() -> str:
    try:
        return version("promptuna")
    except Exception:
        return "unknown"


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _aggregate(values: list[float]) -> dict[str, float | int]:
    n = len(values)
    if n == 0:
        return {"mean": 0.0, "sd": 0.0, "n": 0}
    mean = sum(values) / n
    if n == 1:
        return {"mean": mean, "sd": 0.0, "n": 1}
    var = sum((value - mean) ** 2 for value in values) / (n - 1)
    return {"mean": mean, "sd": var**0.5, "n": n}


@dataclass(frozen=True)
class JobConfig:
    """Inputs needed to build a job manifest."""

    kind: JobKind
    projects_root: Path
    project: str
    program: str
    prompt: str
    examples: str
    dataset_path: Path
    model: str
    workers: int
    repeats: int = 1
    metrics: tuple[str, ...] | None = None
    steps: int | None = None
    proposer_model: str | None = None


def build_manifest(*, job_id: str, config: JobConfig) -> dict[str, Any]:
    """Build the initial manifest for a new on-disk job."""
    manifest: dict[str, Any] = {
        "job_id": job_id,
        "schema_version": SCHEMA_VERSION,
        "promptuna_version": _promptuna_version(),
        "kind": config.kind,
        "status": "running",
        "started_at": _utc_now(),
        "finished_at": None,
        "projects_root": str(config.projects_root.resolve()),
        "project": config.project,
        "program": config.program,
        "prompt": config.prompt,
        "examples": config.examples,
        "dataset_path": str(config.dataset_path.resolve()),
        "dataset_sha256": sha256_file(config.dataset_path),
        "model": config.model,
        "workers": config.workers,
        "repeats": config.repeats,
        "error": None,
        "error_stacktrace": None,
    }
    if config.metrics is not None:
        manifest["metrics"] = list(config.metrics)
    if config.steps is not None:
        manifest["steps"] = config.steps
    if config.proposer_model is not None:
        manifest["proposer_model"] = config.proposer_model
    return manifest


class JobArchive:
    """Append-only writer for one on-disk job."""

    def __init__(self, job_dir: Path, manifest: dict[str, Any]):
        self.job_dir = job_dir
        self._manifest = manifest
        self._events_path = job_dir / _EVENTS_NAME
        self._manifest_path = job_dir / _MANIFEST_NAME

    @classmethod
    def open(cls, jobs_root: Path, job_id: str, config: JobConfig) -> JobArchive:
        """Create ``<jobs_root>/<job_id>/`` and write the initial manifest."""
        job_dir = jobs_root / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        manifest = build_manifest(job_id=job_id, config=config)
        archive = cls(job_dir, manifest)
        archive._write_manifest()
        archive._events_path.touch()
        return archive

    @property
    def job_id(self) -> str:
        """Return the job id from the manifest."""
        return self._manifest["job_id"]

    def append_event(self, envelope: dict[str, Any]) -> None:
        """Append one serialized event envelope to ``events.jsonl``."""
        line = json.dumps(envelope, separators=(",", ":"), sort_keys=True)
        with self._events_path.open("a", encoding="utf-8") as handle:
            handle.write(line)
            handle.write("\n")
            handle.flush()

    def finalize(
        self,
        status: JobStatus,
        *,
        error: str | None = None,
        stacktrace: str | None = None,
    ) -> dict[str, Any]:
        """Mark the job finished and write ``summary.json``."""
        events = load_events(self.job_dir)
        summary = fold_summary(events, self._manifest)
        summary["status"] = status
        if error is not None:
            summary["error"] = error
        if stacktrace is not None:
            summary["error_stacktrace"] = stacktrace

        self._manifest["status"] = status
        self._manifest["finished_at"] = _utc_now()
        self._manifest["error"] = error
        self._manifest["error_stacktrace"] = stacktrace
        self._write_manifest()
        _write_json(self.job_dir / _SUMMARY_NAME, summary)
        return summary

    def _write_manifest(self) -> None:
        _write_json(self._manifest_path, self._manifest)


@dataclass(frozen=True)
class JobRecord:
    """A fully loaded on-disk job."""

    manifest: dict[str, Any]
    events: list[dict[str, Any]]
    summary: dict[str, Any] | None


def load_manifest(job_dir: Path) -> dict[str, Any]:
    """Load ``manifest.json`` from a job directory."""
    return json.loads((job_dir / _MANIFEST_NAME).read_text(encoding="utf-8"))


def load_events(job_dir: Path) -> list[dict[str, Any]]:
    """Load all envelopes from ``events.jsonl``."""
    path = job_dir / _EVENTS_NAME
    if not path.is_file() or path.stat().st_size == 0:
        return []

    events: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                events.append(json.loads(stripped))
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_no}: invalid JSON") from exc
    return events


def load_summary(job_dir: Path) -> dict[str, Any] | None:
    """Load ``summary.json`` when present."""
    path = job_dir / _SUMMARY_NAME
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def load_job(jobs_root: Path, job_id: str) -> JobRecord:
    """Load manifest, events, and optional summary for one job."""
    job_dir = jobs_root / job_id
    if not job_dir.is_dir():
        raise FileNotFoundError(job_id)
    return JobRecord(
        manifest=load_manifest(job_dir),
        events=load_events(job_dir),
        summary=load_summary(job_dir),
    )


def delete_job(jobs_root: Path, job_id: str) -> None:
    """Delete ``<jobs_root>/<job_id>/`` and every file it holds."""
    job_dir = jobs_root / job_id
    if not job_dir.is_dir():
        raise FileNotFoundError(job_id)
    shutil.rmtree(job_dir)


def list_job_ids(jobs_root: Path) -> list[str]:
    """Return job ids sorted newest-first by manifest ``started_at``."""
    if not jobs_root.is_dir():
        return []

    jobs: list[tuple[str, str]] = []
    for path in jobs_root.iterdir():
        manifest_path = path / _MANIFEST_NAME
        if not path.is_dir() or not manifest_path.is_file():
            continue
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        jobs.append((manifest.get("started_at", ""), path.name))

    jobs.sort(reverse=True)
    return [job_id for _, job_id in jobs]


def list_job_manifests(jobs_root: Path) -> list[dict[str, Any]]:
    """Return manifests for all on-disk jobs, newest-first."""
    return [load_manifest(jobs_root / job_id) for job_id in list_job_ids(jobs_root)]


def _cell_key(event: dict[str, Any]) -> tuple[int, str]:
    """Group key pooling an example's replicates within one step.

    ``step_index`` keeps optimize steps from bleeding into one another (it is
    always 0 for run and evaluate). Events written before ``example_id`` existed
    fall back to ``trial_id``, which is per-replicate: groups degenerate to a
    single member, exactly the previous behaviour.
    """
    payload = event["payload"]
    return (event["step_index"], payload.get("example_id", payload["trial_id"]))


def _quality_rollup(successful_scorings: list[dict[str, Any]]) -> dict[str, Any]:
    """Roll scorings up per ``(example, metric)`` cell.

    A cell pools replicates only, so its ``sd`` is pure measurement noise:
    ``per_metric`` averages the cell means (one weight per example) and the
    leftover ``sd`` becomes the metric's noise floor.
    """
    cells: dict[tuple[int, str, str], list[float]] = {}
    for event in successful_scorings:
        step, example = _cell_key(event)
        key = (step, example, event["payload"]["metric"]["name"])
        cells.setdefault(key, []).append(event["payload"]["score"]["normalized"])

    cell_means: dict[str, list[float]] = {}
    cell_sds: dict[str, list[float]] = {}
    for (_step, _example, metric_name), values in cells.items():
        aggregate = _aggregate(values)
        cell_means.setdefault(metric_name, []).append(float(aggregate["mean"]))
        cell_sds.setdefault(metric_name, []).append(float(aggregate["sd"]))

    per_metric = {name: _aggregate(means) for name, means in cell_means.items()}
    return {
        "per_metric": per_metric,
        "replicate_noise": {name: _aggregate(sds) for name, sds in cell_sds.items()},
        "overall": _aggregate([float(a["mean"]) for a in per_metric.values()])
        if per_metric
        else None,
    }


def _telemetry_rollup(successful_trials: list[dict[str, Any]]) -> dict[str, Any]:
    """Sum response telemetry and measure how far an example's replicates drifted."""
    contents: dict[tuple[int, str], list[str]] = {}
    input_tokens = 0
    output_tokens = 0
    latency = 0.0
    for event in successful_trials:
        response = event["payload"].get("telemetry", {}).get("response")
        if response is None:
            continue
        if response.get("content") is not None:
            contents.setdefault(_cell_key(event), []).append(response["content"])
        input_tokens += int(response.get("input_tokens") or 0)
        output_tokens += int(response.get("output_tokens") or 0)
        latency += float(response.get("latency") or 0.0)

    divergences = [d for c in contents.values() if (d := content_divergence(c)) is not None]
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "latency": latency,
        "replicate_divergence": _aggregate(divergences) if divergences else None,
    }


def _steps_rollup(steps: list[dict[str, Any]]) -> dict[str, Any]:
    """Extract step summaries and identify the best step."""
    step_summaries = [
        {
            "step_index": event["step_index"],
            "score": event["payload"]["score"],
            "prompt_template": event["payload"]["prompt_template"],
            "summary": event["payload"]["summary"],
        }
        for event in steps
    ]
    result: dict[str, Any] = {"steps": step_summaries}
    if step_summaries:
        result["best_step"] = max(step_summaries, key=lambda item: item["score"])
    return result


def fold_summary(events: list[dict[str, Any]], manifest: dict[str, Any]) -> dict[str, Any]:
    """Fold event envelopes into a denormalized summary dict.

    TODO: Revisit whether this should delegate to :mod:`promptuna.report` instead of
    re-deriving aggregates here.
    """
    trials = [event for event in events if event.get("type") == "trial"]
    scorings = [event for event in events if event.get("type") == "scoring"]
    steps = [event for event in events if event.get("type") == "step"]

    successful_trials = [event for event in trials if event["payload"]["status"] == "success"]
    successful_scorings = [event for event in scorings if event["payload"]["status"] == "success"]

    trial_count = len(trials)
    scoring_count = len(scorings)
    failure_rate = 0.0 if trial_count == 0 else 1.0 - len(successful_trials) / trial_count
    scoring_failure_rate = (
        0.0 if scoring_count == 0 else (scoring_count - len(successful_scorings)) / scoring_count
    )
    quality = _quality_rollup(successful_scorings)

    summary: dict[str, Any] = {
        "job_id": manifest["job_id"],
        "kind": manifest["kind"],
        "trial_count": trial_count,
        "scoring_count": scoring_count,
        "failure_rate": failure_rate,
        "scoring_failure_rate": scoring_failure_rate,
        "overall": quality["overall"],
        "per_metric": quality["per_metric"],
        "replicate_noise": quality["replicate_noise"],
        "telemetry": _telemetry_rollup(successful_trials),
    }

    if manifest["kind"] == "optimize":
        summary.update(_steps_rollup(steps))

    return summary
