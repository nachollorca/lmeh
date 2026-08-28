Evaluate and optimize **programs** — Python functions that call an LM once inside a deterministic scaffold (input shaping, template rendering, output parsing).

Use `promptuna <command> --help` for flags and options.

## Project layout

Each project is a subdirectory of the **projects root**:

```
<project_name>/
├── programs.py       # program functions (--program = function name)
├── metrics.py        # ProgrammaticMetric / LLMJudgeMetric (--metric = variable name)
├── prompts/
│   └── <name>.jinja  # Jinja2 templates (--prompt = stem)
└── data/
    └── <name>.jsonl  # datasets (--examples = stem; rows: inputs + optional reference)
```

## Projects root

Resolution order (highest priority first):

1. `--projects-root` (CLI flag)
2. `PROMPTUNA_PROJECTS_ROOT` environment variable
3. Default: `samples/` in a development checkout

## Replication

LM calls are stochastic. `--repeats n` runs every example *n* times (one `Trial` per replicate) so aggregates average out noise; it applies to the whole dataset. Judge-side replication is per metric (`LLMJudgeMetric(repeats=n)` in `metrics.py`).

## Job output

`run`, `evaluate`, and `optimize` stream progress, then print results:

- **stdout** — markdown report (`--format json` prints `summary.json` instead)
- **stderr** — `job_id: <uuid>` when the job finishes
- **on disk** — `<projects_root>/jobs/<job_id>/` (`summary.json`, manifest, streamed events)

`report <job_id>` always prints `summary.json` to stdout.
