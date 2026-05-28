"""
results_service — FastAPI per accedere ai dati già elaborati dalla pipeline.

Legge i file prodotti dalla pipeline in data/final/ (volume condiviso)
e li espone come API REST. Non esegue mai scritture: è read-only sul volume.

Endpoints:
  GET  /results                        — lista di tutti i (target, topic) disponibili
  GET  /results/{filename}             — record completi per un file
  GET  /results/{filename}/summary     — metadati e statistiche del file
  GET  /download/{filename}/json       — download file JSON
  GET  /download/{filename}/csv        — download file CSV
  GET  /healthz                        — health check
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path

# Configura il root logger prima di qualsiasi uso: i messaggi INFO applicativi
# sono visibili nei log di Docker (uvicorn configura solo i suoi logger).
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

log = logging.getLogger(__name__)

import os as _os
BASE_DIR  = Path(_os.getenv("DATA_DIR", "/app/data"))
FINAL_DIR = BASE_DIR / "final"

app = FastAPI(
    title="Results Service",
    description="Accesso ai risultati elaborati dalla pipeline WR-Analysis-Light.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost", "http://localhost:80", "http://127.0.0.1"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_json(path: Path) -> list | dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        log.error("Errore lettura %s: %s", path, e)
        raise HTTPException(status_code=500, detail=f"Errore lettura file: {e}")


# Allowlist per i filename: build_filename() produce solo CamelCase alfanumerico
# (es. "ZendayaEuphoria"). La regex whitelist esclude a priori separatori, '..',
# null byte e qualsiasi carattere non alfanumerico.
_FILENAME_RE = re.compile(r"^[A-Za-z0-9]{1,300}$")


def _safe_path(filename: str, suffix: str) -> Path:
    """
    Costruisce e valida un path all'interno di FINAL_DIR.

    Protezione a due livelli:
    1. Allowlist regex — accetta solo CamelCase alfanumerico, unico formato
       prodotto da build_filename(). Rifiuta separatori, '..' e caratteri speciali.
    2. Resolve + is_relative_to — risolve eventuali symlink e verifica che il
       path finale resti all'interno di FINAL_DIR (defense-in-depth; pattern
       riconosciuto dai tool di analisi statica come sanitizer CWE-022).
    """
    if not _FILENAME_RE.fullmatch(filename):
        raise HTTPException(status_code=400, detail="Nome file non valido.")
    # lgtm[py/path-injection] - filename è validato dall'allowlist _FILENAME_RE
    # (^[A-Za-z0-9]{1,300}$): nessun separatore o carattere di traversal possibile.
    # Il check is_relative_to() sotto garantisce ulteriore contenimento.
    path = (FINAL_DIR / f"{filename}{suffix}").resolve()
    if not path.is_relative_to(FINAL_DIR.resolve()):
        raise HTTPException(status_code=400, detail="Nome file non valido.")
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"File non trovato: {filename}{suffix}")
    return path


def _iter_result_files() -> list[Path]:
    if not FINAL_DIR.exists():
        return []
    return [
        f for f in FINAL_DIR.glob("*.json")
        if not f.name.endswith("_summary.json")
    ]


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/healthz", tags=["Infra"])
def healthz() -> dict:
    return {"status": "ok", "service": "results-service"}


@app.get("/results", tags=["Results"])
def list_results() -> list[dict]:
    """
    Lista tutti i (target, topic) disponibili in data/final/.
    Per ogni entry include n_records, sorgenti usate, data ultimo run.
    """
    output = []
    for json_path in _iter_result_files():
        try:
            filename     = json_path.stem
            summary_path = FINAL_DIR / f"{filename}_summary.json"
            summary      = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else {}
            csv_path     = FINAL_DIR / f"{filename}.csv"

            # Usa total_records dal summary per evitare di deserializzare l'intero file.
            # Fallback al conteggio diretto solo se il summary è assente.
            n_records = summary.get("total_records")
            if n_records is None:
                records   = json.loads(json_path.read_text(encoding="utf-8"))
                n_records = len(records)

            output.append({
                "filename":    filename,
                "target":      summary.get("target", ""),
                "topic":       summary.get("topic", ""),
                "n_records":   n_records,
                "last_run":    summary.get("execution_date", ""),
                "sources":     list(summary.get("sources", {}).keys()),
                "has_csv":     csv_path.exists(),
                "has_summary": summary_path.exists(),
            })
        except Exception as exc:
            log.warning("Saltato %s: %s", json_path.name, exc)
            continue

    return sorted(output, key=lambda x: x.get("last_run", ""), reverse=True)


@app.get("/results/{filename}", tags=["Results"])
def get_result_records(filename: str) -> list:
    """
    Ritorna i record completi per un dato (target, topic).
    `filename` è il nome del file senza estensione.
    """
    path = _safe_path(filename, ".json")
    return _load_json(path)


@app.get("/results/{filename}/summary", tags=["Results"])
def get_result_summary(filename: str) -> dict:
    """Ritorna i metadati e le statistiche di un risultato."""
    path = _safe_path(filename, "_summary.json")
    return _load_json(path)


@app.get("/download/{filename}/json", tags=["Download"])
def download_json(filename: str) -> FileResponse:
    """Download del file JSON grezzo."""
    path = _safe_path(filename, ".json")
    return FileResponse(
        path,
        media_type="application/json",
        filename=path.name,
    )


@app.get("/download/{filename}/csv", tags=["Download"])
def download_csv(filename: str) -> FileResponse:
    """Download del file CSV."""
    path = _safe_path(filename, ".csv")
    return FileResponse(
        path,
        media_type="text/csv; charset=utf-8",
        filename=path.name,
    )
