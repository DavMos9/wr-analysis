# wr-analysis-web

> Web layer for [wr-analysis-light](../wr-analysis-light) — a modular data pipeline for **Web Reputational Analysis**.

This project wraps the core Python pipeline in a set of RESTful microservices and exposes three interfaces:

- **React SPA** — launch pipeline runs, browse results, manage periodic schedules
- **Streamlit dashboard** — interactive time-series charts of sentiment and mention volume (backed by PostgreSQL)
- **REST API** — full programmatic access to all pipeline functionality

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                           nginx  :80                                         │
│         /           /api/pipeline/   /api/results/   /api/scheduler/        │
│                                                         /dashboard/          │
└───┬─────────────────────┬────────────────┬─────────────────┬────────────────┘
    │                     │                │                 │
    ▼                     ▼                ▼                 ▼
┌──────────┐   ┌──────────────────┐  ┌───────────────┐  ┌──────────────────┐
│ frontend │   │ pipeline-service │  │results-service│  │scheduler-service │
│ :3000    │   │ :8001            │  │ :8002         │  │ :8003            │
│          │   │                  │  │               │  │                  │
│ React    │   │ Async job runner │  │ Read-only     │  │ APScheduler +    │
│ Vite SPA │   │ wraps the core   │  │ results API   │  │ SQLite — fires   │
│          │   │ pipeline         │  │               │  │ periodic runs    │
└──────────┘   └────────┬─────────┘  └───────┬───────┘  └────────┬─────────┘
                        │                    │                    │
                        └────────────────────┴────────────────────┘
                                             │
                              ┌──────────────▼──────────┐
                              │     Docker volume        │
                              │     pipeline_data        │
                              │   data/final/  (JSON)    │
                              │   data/raw/    (raw)     │
                              │   scheduler.db           │
                              └─────────────────────────┘

                        ┌────────────────────────────────┐
                        │    dashboard (Streamlit) :8501  │
                        │  sentiment & volume charts      │
                        │  reads PostgreSQL (external)    │
                        └────────────────────────────────┘

                  ┌─────────────────────────────────────────┐
                  │         wr-analysis-light  (core)        │
                  │  mount: ../wr-analysis-light → /app/core │
                  │  collect → normalize → clean → dedup     │
                  │  → enrich → export                       │
                  └─────────────────────────────────────────┘
```

### Services

| Service | Port | Responsibility |
|---|---|---|
| `pipeline-service` | 8001 | Executes the `collect→normalize→clean→dedup→enrich→export` pipeline as async background jobs |
| `results-service` | 8002 | Read-only access to processed results in `data/final/` |
| `scheduler-service` | 8003 | Manages periodic pipeline runs (APScheduler + SQLite WAL) |
| `frontend` | 3000 | React + Vite SPA — run panel, results browser, schedule manager |
| `dashboard` | 8501 | Streamlit dashboard — time-series sentiment/volume charts from PostgreSQL |
| `nginx` | 80 | Reverse proxy — routes requests to the correct backend service |

---

## Prerequisites

| Requirement | Version |
|---|---|
| [Docker](https://docs.docker.com/get-docker/) | ≥ 24 |
| [Docker Compose](https://docs.docker.com/compose/) | ≥ 2.0 |
| [wr-analysis-light](../wr-analysis-light) | at `../wr-analysis-light` |
| PostgreSQL *(for dashboard)* | ≥ 14, external — see [Dashboard setup](#dashboard-postgresql-setup) |

The `wr-analysis-light` repository must be cloned as a **sibling directory** — the pipeline-service mounts it as a read-only bind-mount:

```
parent/
├── wr-analysis-light/    ← core pipeline (required)
└── wr-analysis-web/      ← this repo
```

---

## Quick Start

```bash
# 1. Clone this repository alongside wr-analysis-light
git clone <repo-url> wr-analysis-web
cd wr-analysis-web

# 2. Configure environment
cp .env.example .env
# Edit .env and fill in at minimum one API key to enable a data source

# 3. Build and start all services
docker compose up --build

# 4. Open the interface
open http://localhost
```

The React interface is available at `http://localhost`.  
The Streamlit dashboard is available at `http://localhost/dashboard/`.

> **First run** may take several minutes — the pipeline-service downloads the NLP sentiment model (~1.1 GB) from HuggingFace on startup.

---

## Dashboard PostgreSQL Setup

The Streamlit dashboard reads from an external PostgreSQL database containing pre-aggregated sentiment data in the `wr_sent_giorno` table. This is **independent** from the pipeline's `pipeline_data` volume.

The table schema expected:

```sql
CREATE TABLE wr_sent_giorno (
    giorno     DATE        NOT NULL,
    persona    TEXT        NOT NULL,
    argomento  TEXT        NOT NULL,
    categoria  TEXT,
    lingua     TEXT,
    sent_medio FLOAT,
    totale     INTEGER,
    PRIMARY KEY (giorno, persona, argomento, categoria, lingua)
);
```

Set the connection credentials in `.env`:

```dotenv
DB_HOST=your-postgres-host
DB_PORT=5432
DB_NAME=your-database
DB_USER=your-user
DB_PASSWORD=your-password
```

If the PostgreSQL credentials are missing or unreachable, **only the dashboard service** will fail; all other services start normally.

---

## Configuration

All configuration is done via the `.env` file. Copy `.env.example` to `.env` and fill in the required values.

### Pipeline API Keys

| Variable | Source | Notes |
|---|---|---|
| `YOUTUBE_API_KEY` | [Google Cloud Console](https://console.cloud.google.com/) | YouTube Data API v3 |
| `NEWS_API_KEY` | [newsapi.org](https://newsapi.org/) | Free tier: 100 req/day |
| `GUARDIAN_API_KEY` | [open-platform.theguardian.com](https://open-platform.theguardian.com/) | Free |
| `NYT_API_KEY` | [developer.nytimes.com](https://developer.nytimes.com/) | Free |
| `BRAVE_API_KEY` | [brave.com/search/api](https://brave.com/search/api/) | |
| `STACKEXCHANGE_API_KEY` | [stackapps.com](https://stackapps.com/) | Optional — increases rate limit |
| `BLUESKY_HANDLE` + `BLUESKY_APP_PASSWORD` | [bsky.app](https://bsky.app/) Settings → App Passwords | |
| `MASTODON_ACCESS_TOKEN` | Your Mastodon instance → Settings → Development | |
| `HF_TOKEN` | [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens) | Optional — for private models |

Sources that **do not require an API key**: `ansa`, `bbc`, `gdelt`, `gnews_it`, `hackernews`, `lemmy`, `mastodon` (anonymous), `reddit`, `wikipedia`, `wikitalk`.

### Available Sources

| Source ID | Type | Requires key |
|---|---|---|
| `ansa` | Italian newswire (RSS) | — |
| `bbc` | BBC News (RSS) | — |
| `brave` | Web search | `BRAVE_API_KEY` |
| `gdelt` | Global news events | — |
| `gnews_it` | Italian news aggregator | — |
| `guardian` | The Guardian | `GUARDIAN_API_KEY` |
| `hackernews` | Hacker News (opt-in) | — |
| `lemmy` | Lemmy federated forum | — |
| `mastodon` | Mastodon | `MASTODON_ACCESS_TOKEN` |
| `news` | NewsAPI | `NEWS_API_KEY` |
| `nyt` | New York Times | `NYT_API_KEY` |
| `reddit` | Reddit | — |
| `stackexchange` | Stack Exchange (opt-in) | `STACKEXCHANGE_API_KEY` |
| `wikipedia` | Wikipedia articles | — |
| `wikitalk` | Wikipedia talk pages | — |
| `youtube` | YouTube videos | `YOUTUBE_API_KEY` |
| `youtube_comments` | YouTube comments | `YOUTUBE_API_KEY` |

Sources marked **opt-in** (`hackernews`, `stackexchange`) are excluded from default runs and must be explicitly selected.

---

## Data Flow

```
POST /api/pipeline/run
  └─► pipeline-service (background thread)
        └─► wr-analysis-light PipelineRunner
              collect → normalize → clean → dedup → enrich
              └─► pipeline_data volume
                    data/final/{Target}{Topic}.json
                    data/final/{Target}{Topic}.csv
                    data/final/{Target}{Topic}_summary.json
                    data/raw/{source}_{timestamp}_raw.json    (if save_raw=true)

GET /api/results/results → results-service reads data/final/ (read-only)

Scheduled run → scheduler-service fires → POST /api/pipeline/run (same flow)
```

Results **accumulate across runs**: each new execution merges and deduplicates into the same `(target, topic)` file, so the dataset grows incrementally over time.

---

## API Reference

All endpoints are available through nginx at `http://localhost/api/{service}/`.

### Pipeline Service — `/api/pipeline/`

#### `POST /api/pipeline/run`
Start a new pipeline job. Returns immediately; poll `/run/{id}` for status.

**Request body:**
```json
{
  "target":        "Anthropic",
  "topic":         "AI safety",
  "date_from":     "2026-04-01",
  "date_to":       "2026-05-01",
  "sources":       ["reddit", "youtube", "guardian"],
  "max_results":   20,
  "news_language": "en",
  "save_raw":      true,
  "dry_run":       false
}
```

**Response `202`:**
```json
{ "run_id": "abc-123", "status": "queued", "created_at": "2026-05-23T10:00:00" }
```

#### `GET /api/pipeline/run/{run_id}`
Poll job status.

```json
{
  "run_id":      "abc-123",
  "status":      "done",
  "progress":    "Completato.",
  "n_added":     42,
  "n_total":     156,
  "target":      "Anthropic",
  "topic":       "AI safety",
  "filename":    "AnthropicAiSafety"
}
```

Status lifecycle: `queued` → `running` → `done` | `failed`

#### `GET /api/pipeline/runs`
List all jobs in memory since last service start.

#### `GET /api/pipeline/sources`
List all available sources with defaults and opt-in sources.

---

### Results Service — `/api/results/`

#### `GET /api/results/results`
List all `(target, topic)` datasets available in `data/final/`.

#### `GET /api/results/results/{filename}`
Return all records for a dataset as a JSON array.

#### `GET /api/results/results/{filename}/summary`
Return metadata and per-source statistics.

#### `GET /api/results/download/{filename}/json`
Download the full JSON file.

#### `GET /api/results/download/{filename}/csv`
Download the CSV file (columns: `source`, `date`, `target`, `topic`, `language`, `sentiment`, `url`, `retrieved_at`).

---

### Scheduler Service — `/api/scheduler/`

#### `POST /api/scheduler/schedules`
Create a periodic pipeline run.

```json
{
  "target":           "Anthropic",
  "topic":            "AI safety",
  "frequency":        "weekly",
  "hour":             8,
  "day_of_week":      "mon",
  "date_window_days": 7,
  "sources":          [],
  "max_results":      20,
  "news_language":    "en",
  "save_raw":         true
}
```

`frequency` values: `hourly` | `daily` | `weekly` | `monthly`  
`date_window_days`: lookback window — `date_from` is set to `today - N days` at fire time.

**Response `201`:**
```json
{ "schedule_id": "xyz-456", "cron": "0 8 * * mon", "next_run": "2026-06-02T08:00:00+00:00" }
```

#### `GET /api/scheduler/schedules`
List all schedules with `next_run` times.

#### `PATCH /api/scheduler/schedules/{id}`
Enable or disable a schedule without deleting it.

```json
{ "enabled": false }
```

#### `DELETE /api/scheduler/schedules/{id}`
Permanently remove a schedule.

---

## Project Structure

```
wr-analysis-web/
├── docker-compose.yml          # All services + shared pipeline_data volume
├── nginx.conf                  # Reverse proxy config
├── .env.example                # Template — copy to .env and fill in keys
│
├── services/
│   ├── pipeline_service/
│   │   ├── main.py             # FastAPI — async job runner (mounts core pipeline)
│   │   ├── requirements.txt
│   │   └── Dockerfile
│   │
│   ├── results_service/
│   │   ├── main.py             # FastAPI — read-only results API
│   │   ├── requirements.txt
│   │   └── Dockerfile
│   │
│   ├── scheduler_service/
│   │   ├── main.py             # FastAPI — APScheduler + SQLite WAL
│   │   ├── requirements.txt
│   │   └── Dockerfile
│   │
│   ├── frontend/
│   │   ├── src/
│   │   │   ├── App.jsx
│   │   │   ├── api/client.js   # Typed fetch wrappers for all services
│   │   │   ├── components/
│   │   │   │   ├── RunPanel.jsx        # Launch runs, live progress
│   │   │   │   ├── ResultsPanel.jsx    # Browse results, download
│   │   │   │   ├── SchedulePanel.jsx   # Create / toggle / delete schedules
│   │   │   │   └── SourceSelector.jsx  # Multi-select data sources
│   │   │   └── hooks/usePolling.js     # Generic interval-based polling hook
│   │   ├── package.json
│   │   ├── vite.config.js
│   │   └── Dockerfile
│   │
│   └── dashboard/
│       ├── requirements.txt    # Streamlit + psycopg2 + plotly
│       └── Dockerfile          # Mounts ../Grafici/wr_analysis as /app
│
└── data/                       # Created at runtime (gitignored)
    ├── final/                  # .json / .csv / _summary.json per (target, topic)
    ├── raw/                    # Raw collector payloads (if save_raw=true)
    └── scheduler.db            # APScheduler + custom schedules table (SQLite WAL)
```

> **Note:** `data/` is gitignored. The directory is created automatically by Docker on first run via the named volume `pipeline_data`.

---

## Local Development (without Docker)

To run individual services locally for faster iteration:

```bash
# Pipeline service
cd services/pipeline_service
pip install -r requirements.txt
PYTHONPATH=../../wr-analysis-light uvicorn main:app --port 8001 --reload

# Results service
cd services/results_service
pip install -r requirements.txt
DATA_DIR=/path/to/data uvicorn main:app --port 8002 --reload

# Scheduler service
cd services/scheduler_service
pip install -r requirements.txt
PIPELINE_SERVICE_URL=http://localhost:8001 uvicorn main:app --port 8003 --reload

# Frontend (Vite dev server with proxy)
cd services/frontend
npm install
npm run dev   # → http://localhost:3000
```

---

## Useful Commands

```bash
# Start everything (detached)
docker compose up -d

# Rebuild a single service after code changes
docker compose build pipeline-service && docker compose up -d pipeline-service

# Full rebuild from scratch
docker compose down && docker compose up --build

# View logs for a specific service
docker compose logs -f pipeline-service

# Check service health
docker compose ps

# Inspect processed data
docker compose exec results-service ls /app/data/final/

# Access SQLite database directly (scheduler)
docker compose exec scheduler-service python3 -c \
  "import sqlite3; conn=sqlite3.connect('/app/data/scheduler.db'); \
   [print(r) for r in conn.execute('SELECT id, target, topic, enabled FROM schedules').fetchall()]; conn.close()"
```

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `pipeline-service` shows `(unhealthy)` | Service crashed at startup | Check `docker compose logs pipeline-service` |
| 502 Bad Gateway on pipeline endpoints | Service not yet running | Wait ~30s after `up`; check `docker compose ps` |
| Source selector shows "0 / 0" | `pipeline-service` unreachable | Verify service is healthy |
| Schedules disappeared after restart | Partial restart without full `down` | Run `docker compose down && docker compose up -d` |
| Dashboard fails to load | PostgreSQL credentials missing/wrong | Check `DB_*` variables in `.env` |
| NLP sentiment is `null` for all records | `transformers`/`torch` not yet loaded, or text too short | First run downloads the model; text < 15 chars skips sentiment |
| `wr-analysis-light` bind-mount not found | Sibling directory missing or renamed | Ensure `../wr-analysis-light` exists relative to this repo |

---

## Dependencies

The core pipeline (`wr-analysis-light`) is mounted as a **read-only bind-mount** — no file is copied into the Docker image. This means:

- Changes to pipeline code are picked up without rebuilding the image
- The `wr-analysis-light` directory must be present on the host before `docker compose up`

---

## License

Same license as [wr-analysis-light](../wr-analysis-light).
