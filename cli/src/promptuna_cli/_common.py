"""Shared helpers for CLI job commands."""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any, Literal

import typer

from promptuna.evaluate import RunInfo, RunResults, Scoring
from promptuna.jobs import JobArchive, JobConfig, JobKind, get_jobs_root, load_job, stream_job
from promptuna.optimize import Step
from promptuna.program import Experiment
from promptuna.projects import ProjectValidationError, set_projects_root
from promptuna.report import render_history, render_run
from promptuna.run import FailedTrial, SuccessfulTrial

OutputFormat = Literal["human", "json"]


def apply_projects_root(projects_root: Path | None) -> None:
    """Apply a CLI override for the active projects root."""
    if projects_root is not None:
        set_projects_root(projects_root.expanduser().resolve())


def parse_metric_names(values: list[str]) -> list[str]:
    """Flatten ``--metric`` values, splitting on commas when present."""
    names: list[str] = []
    for value in values:
        for part in value.split(","):
            stripped = part.strip()
            if stripped:
                names.append(stripped)
    if not names:
        raise typer.BadParameter("at least one --metric is required")
    return names


def _collecting_source[T](
    source: Callable[[], Iterator[T]],
) -> tuple[Callable[[], Iterator[T]], list[T]]:
    collected: list[T] = []

    def wrapped() -> Iterator[T]:
        for item in source():
            collected.append(item)
            yield item

    return wrapped, collected


def execute_job(
    *,
    config: JobConfig,
    source: Callable[[], Iterator[Any]],
    experiment: Experiment,
    render_human: Callable[[list[Any]], str],
    output_format: OutputFormat,
) -> None:
    """Run one blocking job, persist it on disk, and print the result."""
    job_id = str(uuid.uuid4())
    archive = JobArchive.open(get_jobs_root(), job_id, config)
    source_fn, collected = _collecting_source(source)

    try:
        for _ in stream_job(archive, source_fn()):
            pass
    except Exception:
        _exit_on_failed_job(job_id)
        raise

    record = load_job(get_jobs_root(), job_id)
    if record.manifest["status"] == "error":
        _exit_on_failed_job(job_id)

    typer.echo(f"job_id: {job_id}", err=True)
    if output_format == "json":
        typer.echo(json.dumps(record.summary, indent=2, sort_keys=True))
        return

    typer.echo(render_human(collected))


def _exit_on_failed_job(job_id: str) -> None:
    record = load_job(get_jobs_root(), job_id)
    error = record.manifest.get("error") or "unknown error"
    typer.echo(f"job failed: {error}", err=True)
    raise typer.Exit(code=1)


def render_run_human(experiment: Experiment, items: list[Any]) -> str:
    """Render a run or evaluate job as markdown."""
    trials = [item for item in items if isinstance(item, (SuccessfulTrial, FailedTrial))]
    scorings = [item for item in items if isinstance(item, Scoring)]
    results = RunResults(
        experiment=experiment,
        run=RunInfo(),
        trials=trials,
        scorings=scorings,
    )
    error_format = None if not scorings else "inputs"
    return render_run(results, error_format=error_format)


def render_optimize_human(items: list[Any]) -> str:
    """Render an optimize job trajectory as markdown."""
    steps = [item for item in items if isinstance(item, Step)]
    return render_history(steps)


def handle_project_error(exc: ProjectValidationError) -> None:
    """Map project validation failures to a CLI exit."""
    typer.echo(str(exc), err=True)
    raise typer.Exit(code=2) from exc


def build_job_config(
    *,
    kind: JobKind,
    project: str,
    program: str,
    prompt: str,
    examples: str,
    dataset_path: Path,
    model: str,
    workers: int,
    repeats: int = 1,
    metrics: tuple[str, ...] | None = None,
    steps: int | None = None,
    proposer_model: str | None = None,
) -> JobConfig:
    """Build a :class:`JobConfig` for the active projects root."""
    from promptuna.projects import get_projects_root

    return JobConfig(
        kind=kind,
        projects_root=get_projects_root(),
        project=project,
        program=program,
        prompt=prompt,
        examples=examples,
        dataset_path=dataset_path,
        model=model,
        workers=workers,
        repeats=repeats,
        metrics=metrics,
        steps=steps,
        proposer_model=proposer_model,
    )
