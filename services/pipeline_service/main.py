"""
pipeline_service — FastAPI wrapper around the wr-analysis-light pipeline.

Espone la pipeline esistente come servizio REST asincrono.
I job vengono eseguiti in background (threading) e il client può
fare polling sullo stato tramite run_id.

Job store: SQLite persistente — i job sopravvivono ai restart del container.
Al boot, i job rimasti in stato 'running' o 'queued' vengono marcati 'failed'.

Endpoints:
  POST /run          — avvia un job asincrono, ritorna run_id
  GET  /run/{id}     — stato e progresso del job
  GET  /runs         — lista di tutti i job (persistente tra restart)
  GET  /sources      — elenco sorgenti disponibili
  GET  /healthz      — health check
"""
from __future__ import annotations

import logging
import os
import sqlite3
import sys
import threading
import uuid
from contextlib import asynccontextmanager, contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# ── Import pipeline core (montato a /app/core via bind-mount Docker) ──────────
sys.path.insert(0, "/app/core")

from collectors import build_registry          # noqa: E402
from exporters import CsvExporter, JsonExporter, SummaryExporter  # noqa: E402
from pipeline import PipelineRunner, PipelineConfig  # noqa: E402
from pipeline.date_filter import parse_date    # noqa: E402
from storage import RawStore                   # noqa: E402
from utils import configure_logging, now_timestamp, build_filename  # noqa: E402

configure_logging()
log = logging.getLogger(__name__)

BASE_DIR = Path(os.getenv("DATA_DIR", "/app/data"))   # volume condiviso tra tutti i servizi
JOBS_DB_PATH = BASE_DIR / "jobs.db"

REGISTRY = build_registry()
ALL_SOURCES = list(REGISTRY.keys())
OPT_IN_SOURCES = frozenset({"stackexchange", "hackernews"})
DEFAULT_SOURCES = [s for s in ALL_SOURCES if s not in OPT_IN_SOURCES]


# ── SQLite job store ──────────────────────────────────────────────────────────
# Persistente tra restart del container — a differenza dell'in-memory dict.
# WAL mode: consente letture concorrenti dai thread di background.

@contextmanager
def _jobs_db():
    conn = sqlite3.connect(str(JOBS_DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _init_jobs_db() -> None:
    BASE_DIR.mkdir(parents=True, exist_ok=True)
    with _jobs_db() as conn:
        # WAL mode impostato una sola volta — persiste sul file SQLite.
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                run_id      TEXT PRIMARY KEY,
                status      TEXT NOT NULL DEFAULT 'queued',
                progress    TEXT NOT NULL DEFAULT '',
                created_at  TEXT NOT NULL,
                started_at  TEXT,
                finished_at TEXT,
                n_added     INTEGER,
                n_total     INTEGER,
                error       TEXT,
                target      TEXT NOT NULL,
                topic       TEXT NOT NULL,
                filename    TEXT
            )
        """)
        # Marca come falliti i job interrotti da un precedente restart
        now = datetime.now(timezone.utc).isoformat()
        conn.execute("""
            UPDATE jobs
            SET status      = 'failed',
                finished_at = ?,
                progress    = 'Interrotto (container riavviato).',
                error       = 'Servizio riavviato durante l''esecuzione.'
            WHERE status IN ('running', 'queued')
        """, (now,))


def _job_get(run_id: str) -> dict[str, Any]:
    with _jobs_db() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE run_id=?", (run_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Job '{run_id}' non trovato.")
    return dict(row)


def _job_update(run_id: str, **kwargs: Any) -> None:
    if not kwargs:
        return
    sets = ", ".join(f"{k}=?" for k in kwargs)
    vals = list(kwargs.values()) + [run_id]
    with _jobs_db() as conn:
        conn.execute(f"UPDATE jobs SET {sets} WHERE run_id=?", vals)  # noqa: S608


# Traccia i thread attivi per attendere la fine pulita al shutdown.
# Rimane in-memory: serve solo alla logica di graceful shutdown.
_active_threads: dict[str, threading.Thread] = {}
_threads_lock   = threading.Lock()


# ── FastAPI app ───────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    _init_jobs_db()
    log.info("Pipeline service avviato. Job store: %s", JOBS_DB_PATH)
    yield
    with _threads_lock:
        active = list(_active_threads.values())
    if active:
        log.warning("Shutdown: %d job in esecuzione — attendo fino a 60s...", len(active))
        for t in active:
            t.join(timeout=60)
            if t.is_alive():
                log.error("Thread %s non terminato entro il timeout: possibile corruzione dati.", t.name)
    log.info("Pipeline service shutdown completato.")


app = FastAPI(
    title="Pipeline Service",
    description="Esegue la pipeline WR-Analysis-Light come job asincroni REST.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost", "http://localhost:80", "http://127.0.0.1"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Schemi Pydantic ───────────────────────────────────────────────────────────

class RunRequest(BaseModel):
    target: str = Field(..., min_length=1, max_length=200, description="Entità da analizzare")
    topic: str = Field(..., min_length=1, max_length=200, description="Topic di ricerca")
    date_from: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$", description="Data inizio (YYYY-MM-DD). Se None: nessun limite inferiore di data.")
    date_to: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$", description="Data fine (YYYY-MM-DD, default: oggi)")
    sources: list[str] = Field(default_factory=list, description="Fonti da interrogare (vuoto = default)")
    max_results: int = Field(default=20, ge=1, le=100, description="Risultati massimi per fonte")
    news_language: str = Field(default="en", pattern=r"^[a-z]{2}(-[A-Z]{2})?$", description="Codice ISO 639-1 (es. 'en', 'it', 'zh-CN')")
    save_raw: bool = Field(default=True, description="Salva payload grezzi in data/raw/")
    dry_run: bool = Field(default=False, description="max_results=1 per fonte (test API)")


class RunResponse(BaseModel):
    run_id: str
    status: str
    created_at: str


class JobStatusResponse(BaseModel):
    run_id: str
    status: str           # queued | running | done | failed
    progress: str
    created_at: str
    started_at: str | None
    finished_at: str | None
    n_added: int | None
    n_total: int | None
    error: str | None
    target: str
    topic: str
    filename: str | None


# ── Logica di background ──────────────────────────────────────────────────────

def _build_query(target: str, topic: str) -> str:
    target_words = set(target.lower().split())
    if any(w in topic.lower() for w in target_words):
        return topic
    return f"{target} {topic}"


def _run_pipeline_background(run_id: str, req: RunRequest) -> None:
    """Eseguita in un thread separato. Aggiorna il job store durante l'esecuzione."""
    _job_update(run_id,
                status="running",
                started_at=datetime.now(timezone.utc).isoformat(),
                progress="Avvio pipeline...")
    try:
        ts         = now_timestamp()
        run_date   = date.today().strftime("%Y-%m-%d")
        query      = _build_query(req.target, req.topic)
        date_until = req.date_to or run_date
        filename   = build_filename(req.target, req.topic)

        # Gli exporter di wr-analysis-light appendono "data/final" al base_dir:
        # passare BASE_DIR.parent fa sì che scrivano in BASE_DIR/final/,
        # allineato con il path atteso da results-service.
        _exporter_root   = BASE_DIR.parent
        json_exporter    = JsonExporter(_exporter_root)
        csv_exporter     = CsvExporter(_exporter_root)
        summary_exporter = SummaryExporter(_exporter_root)

        # Evita di re-interrogare fonti statiche già presenti nel file finale
        existing_path    = BASE_DIR / "final" / (filename + ".json")
        existing_records = json_exporter.load_records(existing_path)
        existing_sources = {r.source for r in existing_records}
        static_sources   = {sid for sid, c in REGISTRY.items() if getattr(c, "is_static", False)}
        skip_sources     = static_sources & existing_sources

        active_sources = req.sources if req.sources else DEFAULT_SOURCES
        active_sources = [s for s in active_sources if s not in skip_sources]

        if not active_sources:
            _job_update(run_id,
                        status="done",
                        finished_at=datetime.now(timezone.utc).isoformat(),
                        progress="Nessuna fonte attiva (tutte già presenti).",
                        n_added=0,
                        n_total=len(existing_records),
                        filename=filename)
            return

        _job_update(run_id, progress=f"Raccolta da {len(active_sources)} fonti in parallelo...")

        config = PipelineConfig(
            target=req.target,
            topic=req.topic,
            query=query,
            sources=active_sources,
            max_results=req.max_results,
            save_raw=req.save_raw,
            date_from=req.date_from,
            date_until=date_until,
            collector_kwargs={"news": {"language": req.news_language}},
            dry_run=req.dry_run,
        )

        runner = PipelineRunner(
            registry=REGISTRY,
            raw_store=RawStore(_exporter_root) if req.save_raw else None,
        )

        _job_update(run_id, progress="Pipeline in esecuzione: collect → normalize → clean → dedup → enrich...")
        new_records = runner.run(config, timestamp=ts, run_date=run_date)

        _job_update(run_id, progress="Esportazione dati (JSON / CSV / summary)...")
        final_records, n_added = json_exporter.export(
            new_records, req.target, req.topic, existing=existing_records
        )
        csv_exporter.export(final_records, req.target, req.topic, scan_timestamp=ts)
        summary_exporter.export(final_records, req.target, req.topic, run_date, ts)

        _job_update(run_id,
                    status="done",
                    finished_at=datetime.now(timezone.utc).isoformat(),
                    progress="Completato.",
                    n_added=n_added,
                    n_total=len(final_records),
                    filename=filename)
        log.info("Job %s completato: +%d record, totale %d.", run_id, n_added, len(final_records))

    except Exception as exc:
        log.exception("Job %s fallito.", run_id)
        _job_update(run_id,
                    status="failed",
                    finished_at=datetime.now(timezone.utc).isoformat(),
                    progress="Fallito.",
                    error=str(exc))
    finally:
        with _threads_lock:
            _active_threads.pop(run_id, None)


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/healthz", tags=["Infra"])
def healthz() -> dict:
    return {"status": "ok", "service": "pipeline-service"}


@app.get("/sources", tags=["Config"])
def list_sources() -> dict:
    """Restituisce le sorgenti disponibili e i default."""
    return {
        "all": ALL_SOURCES,
        "defaults": DEFAULT_SOURCES,
        "opt_in": sorted(OPT_IN_SOURCES),
    }


@app.post("/run", response_model=RunResponse, status_code=202, tags=["Jobs"])
def create_run(req: RunRequest) -> RunResponse:
    """
    Avvia un job di pipeline in background.
    Ritorna immediatamente un run_id per il polling.
    """
    try:
        if req.date_from:
            parse_date(req.date_from)
        if req.date_to:
            parse_date(req.date_to)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    if req.sources:
        invalid = [s for s in req.sources if s not in ALL_SOURCES]
        if invalid:
            raise HTTPException(status_code=422, detail=f"Sorgenti non valide: {invalid}")

    run_id = str(uuid.uuid4())
    now    = datetime.now(timezone.utc).isoformat()

    with _jobs_db() as conn:
        conn.execute("""
            INSERT INTO jobs (run_id, status, progress, created_at, target, topic)
            VALUES (?, 'queued', 'In coda...', ?, ?, ?)
        """, (run_id, now, req.target, req.topic))

    thread = threading.Thread(
        target=_run_pipeline_background,
        args=(run_id, req),
        daemon=True,
        name=f"pipeline-{run_id[:8]}",
    )
    with _threads_lock:
        _active_threads[run_id] = thread
        thread.start()
    log.info("Job %s creato per target='%s', topic='%s'.", run_id, req.target, req.topic)

    return RunResponse(run_id=run_id, status="queued", created_at=now)


@app.get("/run/{run_id}", response_model=JobStatusResponse, tags=["Jobs"])
def get_run_status(run_id: str) -> JobStatusResponse:
    """Restituisce lo stato corrente di un job."""
    return JobStatusResponse(**_job_get(run_id))


@app.get("/runs", tags=["Jobs"])
def list_runs(
    limit: int = Query(default=50, ge=1, le=500, description="Numero massimo di job da restituire"),
    offset: int = Query(default=0, ge=0, description="Offset per la paginazione"),
) -> list:
    """Lista job ordinati per data discendente (persistente tra restart). Paginata: limit/offset."""
    with _jobs_db() as conn:
        rows = conn.execute(
            "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
    return [dict(r) for r in rows]
