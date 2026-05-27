"""
scheduler_service — Gestione run periodici via APScheduler + SQLite.

Permette di creare schedule per eseguire la pipeline automaticamente
(ogni ora / giorno / settimana / mese). Ogni schedule, quando scatta,
chiama pipeline-service via HTTP per avviare il job.

Il look-back window (date_from) viene calcolato dinamicamente
al momento del fire, non alla creazione dello schedule.

Endpoints:
  POST   /schedules            — crea uno schedule
  GET    /schedules            — lista schedule
  GET    /schedules/{id}       — dettaglio singolo schedule
  PATCH  /schedules/{id}       — abilita / disabilita
  DELETE /schedules/{id}       — elimina
  GET    /healthz              — health check
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Literal

import httpx
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

log = logging.getLogger(__name__)

PIPELINE_SERVICE_URL = os.getenv("PIPELINE_SERVICE_URL", "http://pipeline-service:8001")
DATA_DIR = Path(os.getenv("DATA_DIR", "/app/data"))
DB_PATH  = DATA_DIR / "scheduler.db"

# ── Database ──────────────────────────────────────────────────────────────────

@contextmanager
def _db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _init_db() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with _db() as conn:
        # WAL mode: consente letture concorrenti durante scritture APScheduler
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS schedules (
                id                TEXT PRIMARY KEY,
                target            TEXT NOT NULL,
                topic             TEXT NOT NULL,
                frequency         TEXT NOT NULL,
                cron_expression   TEXT NOT NULL,
                pipeline_config   TEXT NOT NULL,
                date_window_days  INTEGER NOT NULL DEFAULT 7,
                enabled           INTEGER NOT NULL DEFAULT 1,
                created_at        TEXT NOT NULL,
                last_run          TEXT,
                last_run_id       TEXT
            )
        """)


# ── APScheduler ───────────────────────────────────────────────────────────────

# La directory deve esistere prima che SQLAlchemy crei il file SQLite.
# In Docker il volume è già montato, ma questa riga copre ambienti non-Docker.
DATA_DIR.mkdir(parents=True, exist_ok=True)
_jobstore = SQLAlchemyJobStore(url=f"sqlite:///{DB_PATH}")
scheduler = BackgroundScheduler(
    jobstores={"default": _jobstore},
    job_defaults={"coalesce": True, "max_instances": 1},
)


def _fire_pipeline(schedule_id: str, base_config: dict, date_window_days: int) -> None:
    """
    Callback di APScheduler. Computa date_from dinamicamente
    (look-back di `date_window_days` giorni dalla data corrente)
    e chiama pipeline-service.
    """
    config = dict(base_config)
    config["date_from"] = (date.today() - timedelta(days=date_window_days)).isoformat()

    log.info("[scheduler] Avvio run per schedule %s — config: %s", schedule_id, config)
    try:
        with httpx.Client(timeout=60) as client:
            resp = client.post(f"{PIPELINE_SERVICE_URL}/run", json=config)
            resp.raise_for_status()
            run_id = resp.json().get("run_id", "")

        with _db() as conn:
            conn.execute(
                "UPDATE schedules SET last_run=?, last_run_id=? WHERE id=?",
                (datetime.utcnow().isoformat(), run_id, schedule_id),
            )
        log.info("[scheduler] Run avviato: run_id=%s", run_id)
    except Exception as exc:
        log.error("[scheduler] Errore schedule %s: %s", schedule_id, exc)


# ── Cron helpers ──────────────────────────────────────────────────────────────

FrequencyType = Literal["hourly", "daily", "weekly", "monthly"]
DayOfWeekType = Literal["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def _parse_cron_fields(cron_expr: str) -> dict:
    """
    Estrae hour e day_of_week dalla cron expression prodotta da _build_cron().
    Formato atteso: "minute hour dom month dow"
    Es: "0 8 * * mon" → {"hour": 8, "day_of_week": "mon"}
        "0 * * * *"   → {"hour": None, "day_of_week": None}
    """
    parts = cron_expr.split()
    hour_str = parts[1] if len(parts) > 1 else "*"
    dow_str  = parts[4] if len(parts) > 4 else "*"
    return {
        "hour":        int(hour_str) if hour_str != "*" else None,
        "day_of_week": dow_str       if dow_str  != "*" else None,
    }


def _build_cron(frequency: FrequencyType, hour: int, day_of_week: DayOfWeekType) -> str:
    mapping: dict[str, str] = {
        "hourly":  "0 * * * *",
        "daily":   f"0 {hour} * * *",
        "weekly":  f"0 {hour} * * {day_of_week}",
        "monthly": f"0 {hour} 1 * *",
    }
    return mapping[frequency]


# ── FastAPI app ───────────────────────────────────────────────────────────────

app = FastAPI(
    title="Scheduler Service",
    description="Gestione run periodici della pipeline WR-Analysis-Light.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _reconcile_jobs() -> None:
    """
    Al boot, sincronizza lo stato APScheduler con la tabella schedules.
    Copre il caso in cui il jobstore SQLite sia stato ricreato o svuotato
    (es. dopo un crash) mentre la tabella schedules è integra.
    """
    with _db() as conn:
        rows = conn.execute("SELECT * FROM schedules").fetchall()

    recovered = 0
    for row in rows:
        d   = dict(row)
        job = scheduler.get_job(d["id"])

        if d["enabled"]:
            if job is None:
                # Job assente dal jobstore: lo riaggiungiamo
                pipeline_config = json.loads(d["pipeline_config"])
                scheduler.add_job(
                    _fire_pipeline,
                    CronTrigger.from_crontab(d["cron_expression"]),
                    args=[d["id"], pipeline_config, d["date_window_days"]],
                    id=d["id"],
                    name=f"{d['target']} / {d['topic']}",
                    replace_existing=True,
                )
                recovered += 1
                log.warning("[scheduler] Ricreato job mancante %s (%s/%s)",
                            d["id"][:8], d["target"], d["topic"])
        else:
            # Schedule disabilitato: assicuriamoci che sia in pausa
            if job is not None and job.next_run_time is not None:
                try:
                    scheduler.pause_job(d["id"])
                except Exception:
                    pass

    log.info("[scheduler] Reconciliazione boot: %d job ripristinati.", recovered)


@app.on_event("startup")
def startup() -> None:
    _init_db()
    scheduler.start()
    _reconcile_jobs()
    log.info("Scheduler avviato.")


@app.on_event("shutdown")
def shutdown() -> None:
    scheduler.shutdown(wait=False)


# ── Schemi Pydantic ───────────────────────────────────────────────────────────

class ScheduleRequest(BaseModel):
    # Identificazione analisi
    target: str = Field(..., min_length=1)
    topic: str = Field(..., min_length=1)
    # Frequenza
    frequency: FrequencyType = Field(..., description="hourly | daily | weekly | monthly")
    hour: int = Field(default=8, ge=0, le=23, description="Ora di esecuzione (0-23)")
    day_of_week: DayOfWeekType = Field(default="mon", description="Giorno per frequency=weekly")
    # Finestra temporale
    date_window_days: int = Field(
        default=7, ge=1, le=365,
        description="Quanti giorni fa come date_from al momento del run (default: 7)"
    )
    # Parametri pipeline
    sources: list[str] = Field(default_factory=list, description="Fonti (vuoto = default)")
    max_results: int = Field(default=20, ge=1, le=100)
    news_language: str = Field(default="en")
    save_raw: bool = Field(default=True)


class SchedulePatch(BaseModel):
    enabled: bool


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/healthz", tags=["Infra"])
def healthz() -> dict:
    return {"status": "ok", "service": "scheduler-service"}


@app.post("/schedules", status_code=201, tags=["Schedules"])
def create_schedule(req: ScheduleRequest) -> dict:
    """Crea un nuovo schedule periodico."""
    schedule_id = str(uuid.uuid4())
    cron        = _build_cron(req.frequency, req.hour, req.day_of_week)
    now         = datetime.utcnow().isoformat()

    # Configurazione che verrà passata a pipeline-service a ogni fire
    pipeline_config = {
        "target":         req.target,
        "topic":          req.topic,
        "sources":        req.sources,
        "max_results":    req.max_results,
        "news_language":  req.news_language,
        "save_raw":       req.save_raw,
        # date_from viene iniettato dinamicamente in _fire_pipeline
    }

    scheduler.add_job(
        _fire_pipeline,
        CronTrigger.from_crontab(cron),
        args=[schedule_id, pipeline_config, req.date_window_days],
        id=schedule_id,
        name=f"{req.target} / {req.topic}",
        replace_existing=True,
    )

    job      = scheduler.get_job(schedule_id)
    next_run = job.next_run_time.isoformat() if job and job.next_run_time else None

    with _db() as conn:
        conn.execute(
            """INSERT INTO schedules
               (id, target, topic, frequency, cron_expression, pipeline_config,
                date_window_days, enabled, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)""",
            (schedule_id, req.target, req.topic, req.frequency, cron,
             json.dumps(pipeline_config), req.date_window_days, now),
        )

    log.info("Schedule %s creato: %s per '%s/%s'", schedule_id, cron, req.target, req.topic)
    return {
        "schedule_id": schedule_id,
        "cron":        cron,
        "next_run":    next_run,
    }


@app.get("/schedules", tags=["Schedules"])
def list_schedules() -> list[dict]:
    """Lista tutti gli schedule con il prossimo run previsto."""
    with _db() as conn:
        rows = conn.execute(
            "SELECT * FROM schedules ORDER BY created_at DESC"
        ).fetchall()

    result = []
    for row in rows:
        d        = dict(row)
        job      = scheduler.get_job(d["id"])
        d["next_run"] = job.next_run_time.isoformat() if job and job.next_run_time else None
        # Espone hour e day_of_week estratti dalla cron expression per il frontend
        d.update(_parse_cron_fields(d["cron_expression"]))
        result.append(d)
    return result


@app.get("/schedules/{schedule_id}", tags=["Schedules"])
def get_schedule(schedule_id: str) -> dict:
    """Dettaglio di uno schedule specifico."""
    with _db() as conn:
        row = conn.execute(
            "SELECT * FROM schedules WHERE id=?", (schedule_id,)
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Schedule non trovato.")

    d    = dict(row)
    job  = scheduler.get_job(schedule_id)
    d["next_run"] = job.next_run_time.isoformat() if job and job.next_run_time else None
    d.update(_parse_cron_fields(d["cron_expression"]))
    return d


@app.patch("/schedules/{schedule_id}", tags=["Schedules"])
def toggle_schedule(schedule_id: str, patch: SchedulePatch) -> dict:
    """Abilita o disabilita uno schedule senza eliminarlo."""
    with _db() as conn:
        row = conn.execute(
            "SELECT * FROM schedules WHERE id=?", (schedule_id,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Schedule non trovato.")
        conn.execute(
            "UPDATE schedules SET enabled=? WHERE id=?",
            (1 if patch.enabled else 0, schedule_id),
        )

    if patch.enabled:
        d               = dict(row)
        pipeline_config = json.loads(d["pipeline_config"])
        scheduler.add_job(
            _fire_pipeline,
            CronTrigger.from_crontab(d["cron_expression"]),
            args=[schedule_id, pipeline_config, d["date_window_days"]],
            id=schedule_id,
            name=f"{d['target']} / {d['topic']}",
            replace_existing=True,
        )
    else:
        try:
            scheduler.pause_job(schedule_id)
        except Exception:
            pass

    return {"schedule_id": schedule_id, "enabled": patch.enabled}


@app.delete("/schedules/{schedule_id}", status_code=204, tags=["Schedules"])
def delete_schedule(schedule_id: str) -> None:
    """Elimina uno schedule definitivamente."""
    with _db() as conn:
        row = conn.execute(
            "SELECT id FROM schedules WHERE id=?", (schedule_id,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Schedule non trovato.")
        conn.execute("DELETE FROM schedules WHERE id=?", (schedule_id,))

    try:
        scheduler.remove_job(schedule_id)
    except Exception:
        pass

    log.info("Schedule %s eliminato.", schedule_id)
