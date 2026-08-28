"""Typer entry point for the promptuna CLI."""

from __future__ import annotations

import json
from importlib.resources import files
from pathlib import Path
from typing import Annotated

import typer

from promptuna.evaluate import stream_evaluate
from promptuna.jobs import get_jobs_root, load_job
from promptuna.optimize import stream_optimize
from promptuna.projects import (
    ProjectValidationError,
    build_experiment,
    resolve_dataset_path,
    resolve_project_dir,
)
from promptuna.run import stream_run
from promptuna_cli._common import (
    OutputFormat,
    apply_projects_root,
    build_job_config,
    execute_job,
    handle_project_error,
    parse_metric_names,
    render_optimize_human,
    render_run_human,
)


def _root_help() -> str:
    return files("promptuna_cli").joinpath("SKILL.md").read_text(encoding="utf-8")


app = typer.Typer(
    name="promptuna",
    no_args_is_help=True,
    add_completion=False,
    help=_root_help(),
    rich_markup_mode="markdown",
)


@app.callback()
def main(
    projects_root: Annotated[
        Path | None,
        typer.Option(
            "--projects-root",
            help="Directory containing project folders (overrides PROMPTUNA_PROJECTS_ROOT).",
            dir_okay=True,
            file_okay=False,
            resolve_path=True,
        ),
    ] = None,
) -> None:
    """Configure workspace paths shared by every subcommand."""
    apply_projects_root(projects_root)


@app.command()
def run(
    project: Annotated[str, typer.Option("--project", "-p", help="Project directory name.")],
    program: Annotated[str, typer.Option("--program", help="Program function in programs.py.")],
    prompt: Annotated[str, typer.Option("--prompt", help="Prompt template name.")],
    examples: Annotated[str, typer.Option("--examples", help="Dataset name under data/.")],
    model: Annotated[str, typer.Option("--model", "-m", help="LM id for program execution.")],
    workers: Annotated[
        int,
        typer.Option("--workers", "-w", min=1, help="Parallel trial workers."),
    ] = 1,
    repeats: Annotated[
        int,
        typer.Option("--repeats", "-r", min=1, help="Program runs per example (replicates)."),
    ] = 1,
    output_format: Annotated[
        OutputFormat,
        typer.Option("--format", "-f", help="Output format for the finished job."),
    ] = "human",
) -> None:
    """Execute a program over a dataset."""
    try:
        experiment, example_rows, _ = build_experiment(
            project=project,
            program=program,
            prompt=prompt,
            model=model,
            examples=examples,
            repeats=repeats,
        )
        project_dir = resolve_project_dir(project)
        dataset_path = resolve_dataset_path(project_dir, examples)
        config = build_job_config(
            kind="run",
            project=project,
            program=program,
            prompt=prompt,
            examples=examples,
            dataset_path=dataset_path,
            model=model,
            workers=workers,
            repeats=repeats,
        )
    except ProjectValidationError as exc:
        handle_project_error(exc)

    execute_job(
        config=config,
        source=lambda: stream_run(experiment, example_rows, workers=workers),
        experiment=experiment,
        render_human=lambda items: render_run_human(experiment, items),
        output_format=output_format,
    )


@app.command()
def evaluate(
    project: Annotated[str, typer.Option("--project", "-p", help="Project directory name.")],
    program: Annotated[str, typer.Option("--program", help="Program function in programs.py.")],
    prompt: Annotated[str, typer.Option("--prompt", help="Prompt template name.")],
    examples: Annotated[str, typer.Option("--examples", help="Dataset name under data/.")],
    model: Annotated[str, typer.Option("--model", "-m", help="LM id for program execution.")],
    metric: Annotated[
        list[str],
        typer.Option("--metric", "-M", help="Metric name from metrics.py (repeatable)."),
    ],
    workers: Annotated[
        int,
        typer.Option("--workers", "-w", min=1, help="Parallel trial workers."),
    ] = 1,
    repeats: Annotated[
        int,
        typer.Option("--repeats", "-r", min=1, help="Program runs per example (replicates)."),
    ] = 1,
    output_format: Annotated[
        OutputFormat,
        typer.Option("--format", "-f", help="Output format for the finished job."),
    ] = "human",
) -> None:
    """Execute a program and score it with one or more metrics."""
    metric_names = parse_metric_names(metric)
    try:
        experiment, example_rows, metrics = build_experiment(
            project=project,
            program=program,
            prompt=prompt,
            model=model,
            examples=examples,
            metrics=metric_names,
            repeats=repeats,
        )
        project_dir = resolve_project_dir(project)
        dataset_path = resolve_dataset_path(project_dir, examples)
        config = build_job_config(
            kind="evaluate",
            project=project,
            program=program,
            prompt=prompt,
            examples=examples,
            dataset_path=dataset_path,
            model=model,
            workers=workers,
            repeats=repeats,
            metrics=tuple(metric_names),
        )
    except ProjectValidationError as exc:
        handle_project_error(exc)

    assert metrics is not None

    def source():
        return stream_evaluate(experiment, example_rows, metrics, workers=workers)

    execute_job(
        config=config,
        source=source,
        experiment=experiment,
        render_human=lambda items: render_run_human(experiment, items),
        output_format=output_format,
    )


@app.command()
def optimize(
    project: Annotated[str, typer.Option("--project", "-p", help="Project directory name.")],
    program: Annotated[str, typer.Option("--program", help="Program function in programs.py.")],
    prompt: Annotated[str, typer.Option("--prompt", help="Prompt template name.")],
    examples: Annotated[str, typer.Option("--examples", help="Dataset name under data/.")],
    model: Annotated[str, typer.Option("--model", "-m", help="LM id for program execution.")],
    metric: Annotated[
        list[str],
        typer.Option("--metric", "-M", help="Metric name from metrics.py (repeatable)."),
    ],
    steps: Annotated[int, typer.Option("--steps", min=0, help="Proposer steps after baseline.")],
    proposer_model: Annotated[
        str,
        typer.Option("--proposer-model", help="LM id for prompt-template proposals."),
    ],
    workers: Annotated[
        int,
        typer.Option("--workers", "-w", min=1, help="Parallel trial workers."),
    ] = 1,
    repeats: Annotated[
        int,
        typer.Option("--repeats", "-r", min=1, help="Program runs per example (replicates)."),
    ] = 1,
    output_format: Annotated[
        OutputFormat,
        typer.Option("--format", "-f", help="Output format for the finished job."),
    ] = "human",
) -> None:
    """Search for a better prompt template."""
    metric_names = parse_metric_names(metric)
    try:
        experiment, example_rows, metrics = build_experiment(
            project=project,
            program=program,
            prompt=prompt,
            model=model,
            examples=examples,
            metrics=metric_names,
            repeats=repeats,
        )
        project_dir = resolve_project_dir(project)
        dataset_path = resolve_dataset_path(project_dir, examples)
        config = build_job_config(
            kind="optimize",
            project=project,
            program=program,
            prompt=prompt,
            examples=examples,
            dataset_path=dataset_path,
            model=model,
            workers=workers,
            repeats=repeats,
            metrics=tuple(metric_names),
            steps=steps,
            proposer_model=proposer_model,
        )
    except ProjectValidationError as exc:
        handle_project_error(exc)

    assert metrics is not None

    def source():
        return stream_optimize(
            experiment,
            example_rows,
            metrics,
            proposer_model=proposer_model,
            steps=steps,
            workers=workers,
        )

    execute_job(
        config=config,
        source=source,
        experiment=experiment,
        render_human=render_optimize_human,
        output_format=output_format,
    )


@app.command()
def report(
    job_id: Annotated[str, typer.Argument(help="Job id under <projects_root>/jobs/.")],
) -> None:
    """Print ``summary.json`` for a finished on-disk job."""
    try:
        record = load_job(get_jobs_root(), job_id)
    except FileNotFoundError:
        typer.echo(f"job {job_id!r} not found", err=True)
        raise typer.Exit(code=2) from None

    if record.summary is None:
        typer.echo(f"job {job_id!r} has no summary yet", err=True)
        raise typer.Exit(code=1)

    typer.echo(json.dumps(record.summary, indent=2, sort_keys=True))


def run_cli() -> None:
    """Console entry point."""
    app()


if __name__ == "__main__":
    run_cli()
