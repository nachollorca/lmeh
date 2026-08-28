"""FastAPI application: routes, CORS, and job orchestration."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from promptuna.jobs import JobConfig, JobKind
from promptuna.projects import (
    ProjectValidationError,
    build_catalog,
    build_experiment,
    get_projects_root,
    resolve_dataset_path,
    resolve_project_dir,
)
from promptuna_server import jobs
from promptuna_server.schemas import (
    CatalogResponse,
    EvaluateRequest,
    JobDetailResponse,
    JobListItemResponse,
    JobListResponse,
    JobStartResponse,
    OptimizeRequest,
    ProjectCatalogResponse,
    RunRequest,
)

app = FastAPI(title="promptuna-server")
api = APIRouter()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _validation_error(exc: ProjectValidationError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


def _job_config(
    request: RunRequest,
    *,
    kind: JobKind,
    metrics: list[str] | None = None,
    steps: int | None = None,
    proposer_model: str | None = None,
) -> JobConfig:
    project_dir = resolve_project_dir(request.project)
    dataset_path = resolve_dataset_path(project_dir, request.examples)
    return JobConfig(
        kind=kind,
        projects_root=get_projects_root(),
        project=request.project,
        program=request.program,
        prompt=request.prompt,
        examples=request.examples,
        dataset_path=dataset_path,
        model=request.model,
        workers=request.workers,
        repeats=request.repeats,
        metrics=tuple(metrics) if metrics is not None else None,
        steps=steps,
        proposer_model=proposer_model,
    )


@api.get("/health")
def health() -> dict[str, str]:
    """Liveness check."""
    return {"status": "ok"}


@api.get("/catalog", response_model=CatalogResponse)
def catalog() -> CatalogResponse:
    """List project and artifact names under the active projects root."""
    workspace = build_catalog()
    return CatalogResponse(
        projects_root=str(workspace.projects_root),
        projects=[
            ProjectCatalogResponse(
                name=entry.name,
                programs=entry.programs,
                metrics=entry.metrics,
                prompts=entry.prompts,
                datasets=entry.datasets,
            )
            for entry in workspace.projects
        ],
    )


def _manifest_to_list_item(manifest: dict) -> JobListItemResponse:
    return JobListItemResponse(
        job_id=manifest["job_id"],
        kind=manifest["kind"],
        status=manifest["status"],
        started_at=manifest["started_at"],
        finished_at=manifest.get("finished_at"),
        project=manifest["project"],
        program=manifest["program"],
        prompt=manifest["prompt"],
        examples=manifest["examples"],
        model=manifest["model"],
        workers=manifest["workers"],
        repeats=manifest.get("repeats", 1),
        metrics=manifest.get("metrics"),
        steps=manifest.get("steps"),
        proposer_model=manifest.get("proposer_model"),
        error=manifest.get("error"),
    )


@api.get("/jobs", response_model=JobListResponse)
def list_jobs() -> JobListResponse:
    """List persisted jobs under the active projects root."""
    manifests = jobs.list_jobs()
    return JobListResponse(jobs=[_manifest_to_list_item(manifest) for manifest in manifests])


@api.get("/jobs/{job_id}", response_model=JobDetailResponse)
def get_job(job_id: str) -> JobDetailResponse:
    """Return manifest, events, and optional summary for one job."""
    try:
        record = jobs.load_job_detail(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found") from exc

    return JobDetailResponse(
        manifest=record.manifest,
        events=record.events,
        summary=record.summary,
    )


@api.post("/run", response_model=JobStartResponse)
def start_run(request: RunRequest) -> JobStartResponse:
    """Start a run job; stream trials via ``GET /jobs/{job_id}/events``."""
    try:
        experiment, examples, _ = build_experiment(
            project=request.project,
            program=request.program,
            prompt=request.prompt,
            model=request.model,
            examples=request.examples,
            repeats=request.repeats,
        )
        config = _job_config(request, kind="run")
    except ProjectValidationError as exc:
        raise _validation_error(exc) from exc

    try:
        job_id = jobs.start_run_job(
            config=config,
            experiment=experiment,
            examples=examples,
            workers=request.workers,
        )
    except jobs.ConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    return JobStartResponse(job_id=job_id)


@api.post("/evaluate", response_model=JobStartResponse)
def start_evaluate(request: EvaluateRequest) -> JobStartResponse:
    """Start an evaluate job; stream trials and scorings via SSE."""
    try:
        experiment, examples, metrics = build_experiment(
            project=request.project,
            program=request.program,
            prompt=request.prompt,
            model=request.model,
            examples=request.examples,
            metrics=request.metrics,
            repeats=request.repeats,
        )
        config = _job_config(request, kind="evaluate", metrics=request.metrics)
    except ProjectValidationError as exc:
        raise _validation_error(exc) from exc

    assert metrics is not None
    try:
        job_id = jobs.start_evaluate_job(
            config=config,
            experiment=experiment,
            examples=examples,
            metrics=metrics,
            workers=request.workers,
        )
    except jobs.ConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    return JobStartResponse(job_id=job_id)


@api.post("/optimize", response_model=JobStartResponse)
def start_optimize(request: OptimizeRequest) -> JobStartResponse:
    """Start an optimize job; stream trials, scorings, and steps via SSE."""
    try:
        experiment, examples, metrics = build_experiment(
            project=request.project,
            program=request.program,
            prompt=request.prompt,
            model=request.model,
            examples=request.examples,
            metrics=request.metrics,
            repeats=request.repeats,
        )
        config = _job_config(
            request,
            kind="optimize",
            metrics=request.metrics,
            steps=request.steps,
            proposer_model=request.proposer_model,
        )
    except ProjectValidationError as exc:
        raise _validation_error(exc) from exc

    assert metrics is not None
    try:
        job_id = jobs.start_optimize_job(
            config=config,
            experiment=experiment,
            examples=examples,
            metrics=metrics,
            workers=request.workers,
            steps=request.steps,
            proposer_model=request.proposer_model,
        )
    except jobs.ConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    return JobStartResponse(job_id=job_id)


@api.get("/jobs/{job_id}/events")
async def job_events(job_id: str) -> StreamingResponse:
    """Server-sent events for one job until it completes or errors."""
    try:
        jobs.get_job(job_id)
    except jobs.JobNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found") from exc

    return StreamingResponse(
        jobs.stream_job_events(job_id),
        media_type="text/event-stream",
    )


app.include_router(api, prefix="/api")


def _mount_static_files(application: FastAPI) -> None:
    """Serve the built SvelteKit app when ``PROMPTUNA_STATIC_DIR`` is set."""
    static_dir = os.environ.get("PROMPTUNA_STATIC_DIR", "").strip()
    if not static_dir:
        return

    root = Path(static_dir)
    index_html = root / "index.html"
    if not index_html.is_file():
        return

    assets_dir = root / "_app"
    if assets_dir.is_dir():
        application.mount("/_app", StaticFiles(directory=assets_dir), name="frontend-assets")

    @application.get("/{path:path}", include_in_schema=False)
    async def serve_frontend(path: str) -> FileResponse:
        if path == "api" or path.startswith("api/"):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")

        if path:
            file_path = root / path
            if file_path.is_file():
                return FileResponse(file_path)

        return FileResponse(index_html)


_mount_static_files(app)
