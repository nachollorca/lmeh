# promptuna-server

> Server surface for the [`promptuna`](https://pypi.org/project/promptuna/) evaluation harness. See the [main project README](https://github.com/nachollorca/promptuna#readme) for the full overview, library API, and usage surfaces.

HTTP + SSE transport for `promptuna` jobs (`run`, `evaluate`, `optimize`).

This package is **transport only**. It does not define evaluation logic — that lives in the core `promptuna` library. On-disk projects are resolved via [`promptuna.projects`](../src/promptuna/projects.py); user projects do not belong in this directory.

## Install (PyPI)

```bash
pip install promptuna-server
uvicorn promptuna_server.main:app --port 6969
```

Set `PROMPTUNA_PROJECTS_ROOT` to a directory of on-disk projects (see [`samples/README.md`](../samples/README.md) for layout). In a dev checkout, `just server` from the repo root is equivalent.

## Development

From the repository root:

```bash
just server
```

Uses bundled `samples/` by default. Override the projects root:

```bash
PROMPTUNA_PROJECTS_ROOT=/path/to/projects just server
```

The API listens on port **6969**. All routes are under the **`/api` prefix** (e.g. `GET /api/health`). Interactive OpenAPI docs: **http://127.0.0.1:6969/docs**.

For the browser UI in a separate dev server, see [`frontend/README.md`](../frontend/README.md).

## HTTP API

Authoritative definitions: [`main.py`](src/promptuna_server/main.py), [`schemas.py`](src/promptuna_server/schemas.py).

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/health` | Liveness (`{"status":"ok"}`) |
| `GET` | `/api/catalog` | Projects and artifact names for selectors |
| `POST` | `/api/run` | Start a run job → `{ "job_id": "…" }` |
| `POST` | `/api/evaluate` | Start an evaluate job |
| `POST` | `/api/optimize` | Start an optimize job |
| `GET` | `/api/jobs` | List persisted jobs (newest first) |
| `GET` | `/api/jobs/{job_id}` | Replay: `{ manifest, events, summary }` |
| `GET` | `/api/jobs/{job_id}/events` | SSE stream until the job completes |

### Constraints

- **One job at a time** in memory. A second `POST` while one is running returns **409** with `{"detail":"another job is already running"}`.
- **`model`** and **`proposer_model`** are free-text strings (`provider:model-id`); they are **not** in `/api/catalog`.
- **`repeats`** (default `1`) runs every example that many times to average out LM stochasticity; it applies to the whole dataset. Judge-side replication is not settable over HTTP — it lives on the metric in the project's `metrics.py`.
- **`summary`** in `GET /api/jobs/{job_id}` is `null` while `manifest.status === "running"`.

### Job persistence

Completed jobs are written under `<projects_root>/jobs/<job_id>/` as `manifest.json`, append-only `events.jsonl`, and a terminal `summary.json`.

### SSE events

Each streamed line is a JSON envelope (`src/promptuna/serialize.py`):

```json
{
  "seq": 0,
  "job_id": "uuid",
  "step_index": 0,
  "type": "trial | scoring | step | proposal | error",
  "payload": {}
}
```

For `run` and `evaluate`, `step_index` is always **0**. For `optimize`, trials, scorings, and proposals within one optimization step share the same `step_index`; it increments only after a `step` event.

### Clients and `PUBLIC_API_URL`

HTTP clients (including the SvelteKit frontend) set **`PUBLIC_API_URL` to the API origin only** — e.g. `http://127.0.0.1:6969` — and append `/api` to each path. In the Docker image the UI is same-origin and `PUBLIC_API_URL` is left empty so requests go to `/api/...` on port **8080**.

## Docker (UI + API in one container)

From the repository root:

```bash
just docker-build
just docker-run
```

Open **http://localhost:8080**. The image bundles `samples/`; mount your own projects and pass API keys:

```bash
just docker-run -v /path/to/projects:/projects -e PROMPTUNA_PROJECTS_ROOT=/projects
```

Uses **podman** when available, otherwise **docker**. Rebuild after code changes — the image is a snapshot at build time.

Released images are published to GitHub Container Registry on each version tag:

```bash
podman pull ghcr.io/nachollorca/promptuna:latest
podman run --rm -p 8080:8080 --env-file .env ghcr.io/nachollorca/promptuna:latest
```

Set the package visibility to public in GitHub (Packages → promptuna → Package settings) so users can pull without logging in.

A future `promptuna serve` command will wrap uvicorn and accept `--projects-root` explicitly.
