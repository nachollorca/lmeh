"""Resolve on-disk project layouts into live :class:`~promptuna.program.Experiment` objects."""

from __future__ import annotations

import importlib.util
import inspect
import os
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from promptuna.evaluate import LLMJudgeMetric, Metric, ProgrammaticMetric
from promptuna.load import load_jsonl
from promptuna.program import Example, Experiment, Program

_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_RESERVED_WORKSPACE_DIRS = frozenset({"jobs"})
_projects_root: Path | None = None


class ProjectValidationError(ValueError):
    """Raised when project resolution or validation fails."""


@dataclass(frozen=True)
class ProjectCatalog:
    """Name lists for one on-disk project."""

    name: str
    programs: list[str]
    metrics: list[str]
    prompts: list[str]
    datasets: list[str]


@dataclass(frozen=True)
class WorkspaceCatalog:
    """Name lists for every project under the active projects root."""

    projects_root: Path
    projects: list[ProjectCatalog]


def default_projects_root() -> Path:
    """Return the bundled ``samples/`` directory at the repository root."""
    return Path(__file__).resolve().parent.parent.parent / "samples"


def get_projects_root() -> Path:
    """Return the active projects root.

    Resolution order (highest priority first):

    1. :func:`set_projects_root` — programmatic override (typically tests)
    2. ``PROMPTUNA_PROJECTS_ROOT`` — environment variable
    3. :func:`default_projects_root` — bundled ``samples/`` in a dev checkout
    """
    if _projects_root is not None:
        return _projects_root

    env_root = os.environ.get("PROMPTUNA_PROJECTS_ROOT")
    if env_root:
        return Path(env_root).expanduser().resolve()

    return default_projects_root()


def set_projects_root(path: Path | None) -> None:
    """Override the projects root directory programmatically."""
    global _projects_root
    _projects_root = path


def _validate_name(name: str, *, kind: str) -> None:
    if not _NAME_RE.match(name):
        raise ProjectValidationError(f"invalid {kind} name: {name!r}")


def _resolve_under_root(root: Path, *parts: str) -> Path:
    resolved = (root.joinpath(*parts)).resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise ProjectValidationError("path escapes project directory")
    return resolved


def resolve_project_dir(project: str) -> Path:
    """Return ``<projects_root>/<project>/`` after validating the project name."""
    _validate_name(project, kind="project")
    root = get_projects_root().resolve()
    project_dir = _resolve_under_root(root, project)
    if not project_dir.is_dir():
        raise ProjectValidationError(f"project {project!r} not found")
    return project_dir


def _load_project_module(project_dir: Path, module_basename: str) -> Any:
    path = project_dir / f"{module_basename}.py"
    if not path.is_file():
        raise ProjectValidationError(f"{module_basename}.py not found in project")

    module_name = f"_promptuna_project_{project_dir.name}_{module_basename}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ProjectValidationError(f"could not load {module_basename}.py")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _resolve_named_callable(module: Any, name: str, *, kind: str) -> Callable[..., Any]:
    if name.startswith("_"):
        raise ProjectValidationError(f"invalid {kind} name: {name!r}")
    try:
        obj = getattr(module, name)
    except AttributeError as exc:
        raise ProjectValidationError(f"{kind} {name!r} not found") from exc
    if not callable(obj):
        raise ProjectValidationError(f"{kind} {name!r} is not callable")
    return obj


def _is_program(obj: Any) -> bool:
    """Whether ``obj`` has the :class:`~promptuna.program.Program` call signature."""
    try:
        params = inspect.signature(obj).parameters
    except (TypeError, ValueError):
        return False
    return "prompt_template" in params and "model" in params


def _validate_program(program: Callable[..., Any], name: str) -> Program:
    if not _is_program(program):
        raise ProjectValidationError(
            f"program {name!r} must accept prompt_template and model parameters"
        )
    return program  # type: ignore[return-value]


def _validate_metric(metric: Any, name: str) -> Metric:
    if not isinstance(metric, (ProgrammaticMetric, LLMJudgeMetric)):
        raise ProjectValidationError(f"metric {name!r} is not a Metric instance")
    return metric


def resolve_program(project_dir: Path, name: str) -> Program:
    """Import and validate a named program from ``programs.py``."""
    module = _load_project_module(project_dir, "programs")
    program = _resolve_named_callable(module, name, kind="program")
    return _validate_program(program, name)


def resolve_metrics(project_dir: Path, names: list[str]) -> list[Metric]:
    """Import and validate named metrics from ``metrics.py``."""
    module = _load_project_module(project_dir, "metrics")
    metrics: list[Metric] = []
    for name in names:
        if name.startswith("_"):
            raise ProjectValidationError(f"invalid metric name: {name!r}")
        try:
            metric = getattr(module, name)
        except AttributeError as exc:
            raise ProjectValidationError(f"metric {name!r} not found") from exc
        metrics.append(_validate_metric(metric, name))
    return metrics


def resolve_prompt_template(project_dir: Path, prompt: str) -> str:
    """Read ``prompts/<prompt>.jinja`` from the project."""
    _validate_name(prompt, kind="prompt")
    path = _resolve_under_root(project_dir, "prompts", f"{prompt}.jinja")
    if not path.is_file():
        raise ProjectValidationError(f"prompt {prompt!r} not found")
    return path.read_text(encoding="utf-8")


def resolve_dataset_path(project_dir: Path, examples: str) -> Path:
    """Return ``data/<examples>.jsonl`` after validating the dataset name."""
    _validate_name(examples, kind="examples")
    path = _resolve_under_root(project_dir, "data", f"{examples}.jsonl")
    if not path.is_file():
        raise ProjectValidationError(f"dataset {examples!r} not found")
    return path


def resolve_examples(project_dir: Path, examples: str) -> list[Example]:
    """Load ``data/<examples>.jsonl`` via :func:`promptuna.load.load_jsonl`."""
    path = resolve_dataset_path(project_dir, examples)
    loaded = load_jsonl(path)
    if not loaded:
        raise ProjectValidationError(f"dataset {examples!r} is empty")
    return loaded


def list_project_names() -> list[str]:
    """Return valid project directory names under the active projects root."""
    root = get_projects_root().resolve()
    if not root.is_dir():
        return []
    return sorted(
        path.name
        for path in root.iterdir()
        if path.is_dir() and _NAME_RE.match(path.name) and path.name not in _RESERVED_WORKSPACE_DIRS
    )


def list_program_names(project_dir: Path) -> list[str]:
    """Return public program function names from ``programs.py``.

    Only functions with the :class:`~promptuna.program.Program` signature are
    listed: a ``programs.py`` may also define public helpers that fan the
    program out, and discovery must never offer a name
    :func:`resolve_program` would reject.
    """
    if not (project_dir / "programs.py").is_file():
        return []
    module = _load_project_module(project_dir, "programs")
    return sorted(
        name
        for name, obj in inspect.getmembers(module, inspect.isfunction)
        if not name.startswith("_") and inspect.getmodule(obj) is module and _is_program(obj)
    )


def list_metric_names(project_dir: Path) -> list[str]:
    """Return public metric variable names from ``metrics.py``."""
    if not (project_dir / "metrics.py").is_file():
        return []
    module = _load_project_module(project_dir, "metrics")
    return sorted(
        name
        for name, obj in inspect.getmembers(module)
        if not name.startswith("_") and isinstance(obj, (ProgrammaticMetric, LLMJudgeMetric))
    )


def list_prompt_names(project_dir: Path) -> list[str]:
    """Return prompt template names from ``prompts/*.jinja``."""
    prompts_dir = project_dir / "prompts"
    if not prompts_dir.is_dir():
        return []
    return sorted(path.stem for path in prompts_dir.glob("*.jinja") if _NAME_RE.match(path.stem))


def list_dataset_names(project_dir: Path) -> list[str]:
    """Return dataset names from ``data/*.jsonl``."""
    data_dir = project_dir / "data"
    if not data_dir.is_dir():
        return []
    return sorted(path.stem for path in data_dir.glob("*.jsonl") if _NAME_RE.match(path.stem))


def build_catalog() -> WorkspaceCatalog:
    """List project and artifact names under the active projects root."""
    root = get_projects_root().resolve()
    projects = [
        ProjectCatalog(
            name=name,
            programs=list_program_names(root / name),
            metrics=list_metric_names(root / name),
            prompts=list_prompt_names(root / name),
            datasets=list_dataset_names(root / name),
        )
        for name in list_project_names()
    ]
    return WorkspaceCatalog(projects_root=root, projects=projects)


def build_experiment(
    *,
    project: str,
    program: str,
    prompt: str,
    model: str,
    examples: str,
    metrics: list[str] | None = None,
    repeats: int = 1,
) -> tuple[Experiment, list[Example], list[Metric] | None]:
    """Validate project selections and build an :class:`Experiment` plus dataset."""
    project_dir = resolve_project_dir(project)
    resolved_program = resolve_program(project_dir, program)
    prompt_template = resolve_prompt_template(project_dir, prompt)
    example_rows = resolve_examples(project_dir, examples)
    resolved_metrics = resolve_metrics(project_dir, metrics) if metrics is not None else None

    experiment = Experiment(
        program=resolved_program,
        prompt_template=prompt_template,
        model=model,
        repeats=repeats,
    )
    return experiment, example_rows, resolved_metrics
