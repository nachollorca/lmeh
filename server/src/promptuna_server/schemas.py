"""Pydantic request and response models for the HTTP API."""

from typing import Any

from pydantic import BaseModel, Field

from promptuna.jobs import JobKind, JobStatus


class JobStartResponse(BaseModel):
    """Response body returned when a job is accepted."""

    job_id: str


class ProjectCatalogResponse(BaseModel):
    """Name lists for one on-disk project."""

    name: str
    programs: list[str]
    metrics: list[str]
    prompts: list[str]
    datasets: list[str]


class CatalogResponse(BaseModel):
    """Workspace catalog for building job request selectors."""

    projects_root: str
    projects: list[ProjectCatalogResponse]


class RunRequest(BaseModel):
    """Start a run job over a project-local program and dataset."""

    project: str
    program: str
    prompt: str
    model: str
    examples: str
    workers: int = Field(default=1, ge=1)
    repeats: int = Field(default=1, ge=1)


class EvaluateRequest(RunRequest):
    """Start an evaluate job with one or more project-local metrics."""

    metrics: list[str] = Field(min_length=1)


class OptimizeRequest(EvaluateRequest):
    """Start an optimize job with a proposer budget."""

    steps: int = Field(ge=0)
    proposer_model: str


class JobListItemResponse(BaseModel):
    """Summary row for one on-disk job."""

    job_id: str
    kind: JobKind
    status: JobStatus
    started_at: str
    finished_at: str | None
    project: str
    program: str
    prompt: str
    examples: str
    model: str
    workers: int
    repeats: int = 1
    metrics: list[str] | None = None
    steps: int | None = None
    proposer_model: str | None = None
    error: str | None = None


class JobListResponse(BaseModel):
    """All jobs under the active projects root."""

    jobs: list[JobListItemResponse]


class JobDetailResponse(BaseModel):
    """Full replay payload for one job."""

    manifest: dict[str, Any]
    events: list[dict[str, Any]]
    summary: dict[str, Any] | None
