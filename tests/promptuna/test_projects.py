"""Tests for promptuna.projects."""

from __future__ import annotations

from pathlib import Path

import pytest

from promptuna.projects import (
    ProjectValidationError,
    build_catalog,
    build_experiment,
    default_projects_root,
    get_projects_root,
    list_program_names,
    resolve_examples,
    resolve_metrics,
    resolve_program,
    resolve_project_dir,
    resolve_prompt_template,
    set_projects_root,
)

FIXTURES_ROOT = Path(__file__).resolve().parent.parent / "fixtures"
TEST_PROJECT = FIXTURES_ROOT / "test_project"


@pytest.fixture(autouse=True)
def reset_projects_root():
    yield
    set_projects_root(None)


@pytest.fixture
def fixtures_projects_root():
    set_projects_root(FIXTURES_ROOT)
    return FIXTURES_ROOT


def test_build_experiment_resolves_fixture_project(fixtures_projects_root):
    experiment, examples, metrics = build_experiment(
        project="test_project",
        program="echo",
        prompt="baseline",
        model="test:model",
        examples="dev",
        metrics=["exact_match"],
    )

    assert experiment.model == "test:model"
    assert experiment.prompt_template.strip() == "Answer: {{ question }}"
    assert len(examples) == 2
    assert metrics is not None
    assert [metric.name for metric in metrics] == ["exact_match"]


@pytest.mark.parametrize(
    ("project", "match"),
    [
        ("../escape", "invalid project name"),
        ("missing", "not found"),
    ],
)
def test_resolve_project_dir_rejects_invalid_names(
    fixtures_projects_root, project: str, match: str
):
    with pytest.raises(ProjectValidationError, match=match):
        resolve_project_dir(project)


def test_resolve_program_rejects_private_names(fixtures_projects_root):
    project_dir = resolve_project_dir("test_project")

    with pytest.raises(ProjectValidationError, match="invalid program name"):
        resolve_program(project_dir, "_hidden")


def test_resolve_metrics_rejects_private_names(fixtures_projects_root):
    project_dir = resolve_project_dir("test_project")

    with pytest.raises(ProjectValidationError, match="invalid metric name"):
        resolve_metrics(project_dir, ["_secret"])


def test_resolve_program_rejects_invalid_signature(tmp_path):
    project_dir = tmp_path / "bad_program"
    project_dir.mkdir()
    (project_dir / "programs.py").write_text(
        "def bad(**inputs):\n    return inputs\n",
        encoding="utf-8",
    )
    set_projects_root(tmp_path)

    with pytest.raises(ProjectValidationError, match="prompt_template"):
        resolve_program(project_dir, "bad")


def test_resolve_metrics_rejects_non_metric_instance(tmp_path):
    project_dir = tmp_path / "bad_metric"
    project_dir.mkdir()
    (project_dir / "metrics.py").write_text(
        "def not_a_metric():\n    pass\n",
        encoding="utf-8",
    )
    set_projects_root(tmp_path)

    with pytest.raises(ProjectValidationError, match="not a Metric instance"):
        resolve_metrics(project_dir, ["not_a_metric"])


def test_resolve_prompt_rejects_invalid_name(fixtures_projects_root):
    project_dir = resolve_project_dir("test_project")

    with pytest.raises(ProjectValidationError, match="invalid prompt name"):
        resolve_prompt_template(project_dir, "../outside")


def test_resolve_examples_rejects_missing_dataset(fixtures_projects_root):
    project_dir = resolve_project_dir("test_project")

    with pytest.raises(ProjectValidationError, match="not found"):
        resolve_examples(project_dir, "missing")


def test_resolve_examples_rejects_empty_dataset(tmp_path):
    project_dir = tmp_path / "empty_data"
    project_dir.mkdir()
    (project_dir / "data").mkdir()
    (project_dir / "data" / "dev.jsonl").write_text("", encoding="utf-8")
    set_projects_root(tmp_path)

    with pytest.raises(ProjectValidationError, match="is empty"):
        resolve_examples(project_dir, "dev")


def test_get_projects_root_uses_env_var(monkeypatch, fixtures_projects_root):
    monkeypatch.setenv("PROMPTUNA_PROJECTS_ROOT", str(FIXTURES_ROOT))

    assert get_projects_root() == FIXTURES_ROOT.resolve()


def test_set_projects_root_overrides_env_var(monkeypatch, tmp_path):
    other = tmp_path / "other"
    other.mkdir()
    monkeypatch.setenv("PROMPTUNA_PROJECTS_ROOT", str(FIXTURES_ROOT))
    set_projects_root(other)

    assert get_projects_root() == other.resolve()


def test_default_projects_root_points_at_samples():
    assert default_projects_root().name == "samples"


def test_build_experiment_without_metrics_returns_none(fixtures_projects_root):
    _experiment, examples, metrics = build_experiment(
        project="test_project",
        program="echo",
        prompt="baseline",
        model="test:model",
        examples="dev",
    )

    assert len(examples) == 2
    assert metrics is None


def test_build_catalog_lists_fixture_project_names(fixtures_projects_root):
    catalog = build_catalog()

    assert catalog.projects_root == FIXTURES_ROOT.resolve()
    assert [project.name for project in catalog.projects] == ["test_project"]
    entry = catalog.projects[0]
    assert entry.programs == ["echo"]
    assert entry.metrics == ["exact_match"]
    assert entry.prompts == ["baseline"]
    assert entry.datasets == ["dev"]


def test_build_catalog_skips_invalid_project_dir_names(tmp_path):
    (tmp_path / "Valid_Project").mkdir()
    valid = tmp_path / "valid_project"
    valid.mkdir()
    (valid / "prompts").mkdir()
    (valid / "prompts" / "baseline.jinja").write_text("x", encoding="utf-8")
    set_projects_root(tmp_path)

    catalog = build_catalog()

    assert [project.name for project in catalog.projects] == ["valid_project"]
    assert catalog.projects[0].prompts == ["baseline"]


def test_list_program_names_skips_public_non_programs(tmp_path):
    """A public fan-out helper in ``programs.py`` must not be offered as a program."""
    project_dir = tmp_path / "with_helper"
    project_dir.mkdir()
    (project_dir / "programs.py").write_text(
        "def real(prompt_template: str, model: str, **inputs):\n    return inputs\n\n\n"
        "def fanout(model: str, template: str):\n    return None\n",
        encoding="utf-8",
    )
    set_projects_root(tmp_path)

    assert list_program_names(project_dir) == ["real"]
