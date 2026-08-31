"""Tests for promptuna.jobs."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from helpers import make_run_results, make_trial

from promptuna.evaluate import FailedScoring, Score, SuccessfulScoring
from promptuna.jobs import (
    JobArchive,
    JobConfig,
    fold_summary,
    get_jobs_root,
    list_job_ids,
    list_job_manifests,
    load_job,
    sha256_file,
    stream_job,
)
from promptuna.optimize import Proposal, Step, Thinking
from promptuna.program import Example
from promptuna.projects import set_projects_root
from promptuna.run import FailedTrial
from promptuna.serialize import serialize_error, serialize_event


@pytest.fixture
def workspace_root(tmp_path: Path):
    root = tmp_path / "workspace"
    root.mkdir()
    set_projects_root(root)
    yield root
    set_projects_root(None)


@pytest.fixture
def dataset_path(tmp_path: Path) -> Path:
    path = tmp_path / "dev.jsonl"
    path.write_text('{"inputs": {"question": "2+2?"}, "reference": "4"}\n', encoding="utf-8")
    return path


@pytest.fixture
def job_config(workspace_root: Path, dataset_path: Path) -> JobConfig:
    return JobConfig(
        kind="evaluate",
        projects_root=workspace_root,
        project="demo",
        program="echo",
        prompt="baseline",
        examples="dev",
        dataset_path=dataset_path,
        model="test:model",
        workers=1,
        metrics=("exact_match",),
    )


def test_sha256_file(dataset_path: Path):
    digest = sha256_file(dataset_path)
    assert len(digest) == 64


def test_get_jobs_root_uses_workspace(workspace_root: Path):
    assert get_jobs_root() == workspace_root / "jobs"


def test_job_archive_writes_manifest_events_and_summary(
    workspace_root: Path,
    job_config: JobConfig,
    example,
    exact_match_metric,
):
    archive = JobArchive.open(get_jobs_root(), "job-1", job_config)
    trial = make_trial(example, output="4")
    scoring = SuccessfulScoring(
        trial=trial,
        metric=exact_match_metric,
        score=Score(raw=1.0, normalized=1.0, reason="exact"),
    )

    archive.append_event(serialize_event(trial, job_id="job-1", seq=0, step_index=0))
    archive.append_event(serialize_event(scoring, job_id="job-1", seq=1, step_index=0))
    summary = archive.finalize("done")

    record = load_job(get_jobs_root(), "job-1")
    assert record.manifest["status"] == "done"
    assert record.manifest["job_id"] == "job-1"
    assert record.manifest["dataset_sha256"] == sha256_file(job_config.dataset_path)
    assert len(record.events) == 2
    assert record.summary == summary
    assert summary["trial_count"] == 1
    assert summary["scoring_count"] == 1
    assert summary["overall"]["mean"] == pytest.approx(1.0)


def test_fold_summary_counts_failures(example, exact_match_metric):
    trial = FailedTrial(example=example, error=ValueError("boom"), replicate=0)
    scoring = FailedScoring(
        trial=trial,
        metric=exact_match_metric,
        error=RuntimeError("judge crashed"),
    )
    events = [
        serialize_event(trial, job_id="job-1", seq=0, step_index=0),
        serialize_event(scoring, job_id="job-1", seq=1, step_index=0),
    ]
    manifest = {"job_id": "job-1", "kind": "evaluate"}

    summary = fold_summary(events, manifest)

    assert summary["failure_rate"] == 1.0
    assert summary["scoring_failure_rate"] == 1.0
    assert summary["overall"] is None


def test_fold_summary_pools_replicates_per_cell(example, exact_match_metric):
    """Replicates of one example form one cell: mean scores, sd becomes noise floor."""
    events = []
    for seq, (replicate, score) in enumerate([(0, 1.0), (1, 0.0)]):
        trial = make_trial(example, output="4" if replicate == 0 else "5", replicate=replicate)
        scoring = SuccessfulScoring(
            trial=trial,
            metric=exact_match_metric,
            score=Score(raw=score, normalized=score, reason="r"),
        )
        events.append(serialize_event(trial, job_id="job-1", seq=seq * 2, step_index=0))
        events.append(serialize_event(scoring, job_id="job-1", seq=seq * 2 + 1, step_index=0))

    summary = fold_summary(events, {"job_id": "job-1", "kind": "evaluate"})

    # One cell -> per_metric averages the replicates instead of counting them twice.
    assert summary["per_metric"]["exact_match"]["mean"] == pytest.approx(0.5)
    assert summary["per_metric"]["exact_match"]["n"] == 1
    # The disagreement shows up as the metric's noise floor, not as heterogeneity.
    assert summary["replicate_noise"]["exact_match"]["mean"] == pytest.approx(0.7071, abs=1e-4)
    # "4" vs "5" share nothing, so the replicates diverge completely.
    assert summary["telemetry"]["replicate_divergence"]["mean"] == pytest.approx(1.0)


def test_fold_summary_omits_divergence_without_replicates(example, exact_match_metric):
    trial = make_trial(example, output="4")
    events = [serialize_event(trial, job_id="job-1", seq=0, step_index=0)]

    summary = fold_summary(events, {"job_id": "job-1", "kind": "evaluate"})

    assert summary["telemetry"]["replicate_divergence"] is None


def test_fold_summary_includes_optimize_steps(experiment, examples, exact_match_metric):
    result = make_run_results(experiment, examples[:1], exact_match_metric, scores=[0.6])
    step = Step(
        prompt_template="Better: {{ question }}",
        result=result,
        thinking=Thinking(
            reinstate_goal="g",
            trajectory_summary="s",
            failure_analysis="f",
            what_works="w",
            what_hurts="h",
            improvement_hypothesis="i",
            edit_plan="e",
        ),
    )
    events = [serialize_event(step, job_id="job-1", seq=0, step_index=1)]
    manifest = {"job_id": "job-1", "kind": "optimize"}

    summary = fold_summary(events, manifest)

    assert len(summary["steps"]) == 1
    assert summary["best_step"]["prompt_template"] == "Better: {{ question }}"


def test_list_job_ids_orders_newest_first(workspace_root: Path, job_config: JobConfig):
    jobs_root = get_jobs_root()
    first = JobArchive.open(jobs_root, "older", job_config)
    first.finalize("done")
    second = JobArchive.open(jobs_root, "newer", job_config)
    second.finalize("done")

    assert list_job_ids(jobs_root) == ["newer", "older"]


def test_list_job_manifests_matches_job_ids(workspace_root: Path, job_config: JobConfig):
    jobs_root = get_jobs_root()
    archive = JobArchive.open(jobs_root, "job-1", job_config)
    archive.finalize("done")

    manifests = list_job_manifests(jobs_root)

    assert len(manifests) == 1
    assert manifests[0]["job_id"] == "job-1"


def test_archive_survives_reload(workspace_root: Path, job_config: JobConfig, example):
    archive = JobArchive.open(get_jobs_root(), "job-1", job_config)
    archive.append_event(serialize_event(make_trial(example), job_id="job-1", seq=0, step_index=0))
    archive.finalize("done")

    events_path = get_jobs_root() / "job-1" / "events.jsonl"
    lines = events_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["type"] == "trial"


def test_finalize_error_job(workspace_root: Path, job_config: JobConfig):
    archive = JobArchive.open(get_jobs_root(), "job-1", job_config)
    archive.append_event(serialize_error(job_id="job-1", seq=0, message="worker crashed"))
    summary = archive.finalize("error", error="worker crashed")

    record = load_job(get_jobs_root(), "job-1")
    assert record.manifest["status"] == "error"
    assert summary["status"] == "error"
    assert summary["error"] == "worker crashed"


def test_stream_job_persists_and_yields_envelopes(
    workspace_root: Path,
    job_config: JobConfig,
    example,
    exact_match_metric,
):
    archive = JobArchive.open(get_jobs_root(), "job-stream", job_config)
    trial = make_trial(example, output="4")
    scoring = SuccessfulScoring(
        trial=trial,
        metric=exact_match_metric,
        score=Score(raw=1.0, normalized=1.0, reason="exact"),
    )

    def source():
        yield trial
        yield scoring

    envelopes = list(stream_job(archive, source()))

    assert len(envelopes) == 2
    assert envelopes[0]["type"] == "trial"
    assert envelopes[1]["type"] == "scoring"

    record = load_job(get_jobs_root(), "job-stream")
    assert record.manifest["status"] == "done"
    assert record.events == envelopes
    assert record.summary is not None


def test_stream_job_records_errors(workspace_root: Path, job_config: JobConfig, example):
    archive = JobArchive.open(get_jobs_root(), "job-error", job_config)

    def source():
        yield make_trial(example, output="4")
        raise RuntimeError("worker crashed")

    with pytest.raises(RuntimeError, match="worker crashed"):
        list(stream_job(archive, source()))

    record = load_job(get_jobs_root(), "job-error")
    assert record.manifest["status"] == "error"
    assert record.manifest["error"] == "worker crashed"
    assert record.events[-1]["type"] == "error"
    assert "RuntimeError: worker crashed" in record.events[-1]["payload"]["stacktrace"]
    assert "Traceback" in record.manifest["error_stacktrace"]
    assert record.summary is not None
    assert record.summary["status"] == "error"
    assert "worker crashed" in record.summary["error_stacktrace"]


def test_stream_job_proposal_uses_step_index_without_advancing(
    workspace_root: Path,
    job_config: JobConfig,
):
    job_config = JobConfig(
        kind="optimize",
        projects_root=job_config.projects_root,
        project=job_config.project,
        program=job_config.program,
        prompt=job_config.prompt,
        examples=job_config.examples,
        dataset_path=job_config.dataset_path,
        model=job_config.model,
        workers=job_config.workers,
        metrics=job_config.metrics,
        steps=1,
        proposer_model="test:model",
    )
    archive = JobArchive.open(get_jobs_root(), "job-proposal", job_config)
    proposal = Proposal(thinking=None, prompt_template="Better: {{ question }}")

    def source():
        yield proposal
        yield make_trial(
            Example(inputs={"question": "2+2?"}, reference="4"),
            output="4",
        )

    envelopes = list(stream_job(archive, source()))

    assert envelopes[0]["type"] == "proposal"
    assert envelopes[0]["step_index"] == 0
    assert envelopes[1]["type"] == "trial"
    assert envelopes[1]["step_index"] == 0


def test_stream_job_advances_optimize_step_index(
    workspace_root: Path,
    job_config: JobConfig,
    experiment,
    examples,
    exact_match_metric,
):
    job_config = JobConfig(
        kind="optimize",
        projects_root=job_config.projects_root,
        project=job_config.project,
        program=job_config.program,
        prompt=job_config.prompt,
        examples=job_config.examples,
        dataset_path=job_config.dataset_path,
        model=job_config.model,
        workers=job_config.workers,
        metrics=job_config.metrics,
        steps=1,
        proposer_model="test:model",
    )
    archive = JobArchive.open(get_jobs_root(), "job-optimize", job_config)
    result = make_run_results(experiment, examples[:1], exact_match_metric, scores=[0.5])
    step = Step(
        prompt_template="Better: {{ question }}",
        result=result,
        thinking=Thinking(
            reinstate_goal="g",
            trajectory_summary="s",
            failure_analysis="f",
            what_works="w",
            what_hurts="h",
            improvement_hypothesis="i",
            edit_plan="e",
        ),
    )
    trial = make_trial(examples[0], output="4")

    def source():
        yield trial
        yield step

    envelopes = list(stream_job(archive, source()))

    assert envelopes[0]["step_index"] == 0
    assert envelopes[1]["type"] == "step"
    assert envelopes[1]["step_index"] == 0
