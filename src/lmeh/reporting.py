"""Utilities to report experiment results."""

from lmeh.datatypes import RunResults


def markdown_report(results: RunResults) -> str:
    """Synthethises the results of an experiment to a Markdown string."""
    lines: list[str] = []
    lines.append(f"# Run report: `{results.experiment.name}`")
    lines.append("")
    lines.append("Summary of one experiment run across the dataset.")
    lines.append("")

    # Metadata
    lines.append("## Experiment")
    lines.append("")
    lines.append(f"- **Model**: `{results.experiment.config.model}`")
    lines.append(f"- **Run timestamp**: {results.run.timestamp.isoformat()}")
    if results.run.version is not None:
        lines.append(f"- **Version**: `{results.run.version}`")
    lines.append("")

    # Quality
    lines.append("## Quality")
    lines.append("")
    lines.append(
        "Mean normalized score across every successful scoring (higher is better, in `[0, 1]`)."
    )
    lines.append("")
    lines.append(f"- **Mean normalized score**: {results.mean_normalized:.4f}")
    lines.append("")

    per_metric = results.per_metric()
    if per_metric:
        lines.append("### Per-metric mean normalized score")
        lines.append("")
        lines.append("| Metric | Mean normalized |")
        lines.append("| --- | --- |")
        for name in sorted(per_metric):
            lines.append(f"| `{name}` | {per_metric[name]:.4f} |")
        lines.append("")

    # Reliability
    lines.append("## Reliability")
    lines.append("")
    lines.append(
        "Trial failures count against the run (the target is under "
        "evaluation); scorer failures are excluded from quality aggregates."
    )
    lines.append("")
    lines.append(
        f"- **Trials**: {len(results.successful_trials)} successful / {len(results.trials)} total"
    )
    lines.append(f"- **Trial failure rate**: {results.failure_rate:.2%}")
    lines.append(
        f"- **Scorings**: {len(results.successful_scorings)} successful / "
        f"{len(results.scorings)} total"
    )
    lines.append(f"- **Scoring failure rate**: {results.scoring_failure_rate:.2%}")
    lines.append("")

    # Telemetry
    lines.append("## Telemetry")
    lines.append("")
    lines.append("Averages across successful trials only.")
    lines.append("")
    lines.append(f"- **Mean latency**: {results.mean_latency:.3f} s")
    lines.append(f"- **Mean output tokens**: {results.mean_output_tokens:.1f}")
    lines.append(f"- **Total output tokens**: {results.total_output_tokens}")

    return "\n".join(lines)
