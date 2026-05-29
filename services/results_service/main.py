from __future__ import annotations

import hashlib
import json
import logging
import re
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

log = logging.getLogger(__name__)

import os
BASE_DIR  = Path(os.getenv("DATA_DIR", "/app/data"))
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


def _load_json(path: Path) -> list | dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        log.error("Errore lettura %s: %s", path, e)
        raise HTTPException(status_code=500, detail=f"Errore lettura file: {e}")


# Allowlist: solo alfanumerico — unico formato prodotto da build_filename().
_FILENAME_RE = re.compile(r"^[A-Za-z0-9]{1,300}$")


def _safe_path(filename: str, suffix: str) -> Path:
    if not _FILENAME_RE.fullmatch(filename):
        raise HTTPException(status_code=400, detail="Nome file non valido.")
    # filename è usato solo per confronto, mai per costruire un path.
    # Il path restituito è derivato da FINAL_DIR.iterdir() (sorgente filesystem).
    wanted = filename + suffix
    if FINAL_DIR.exists():
        for candidate in FINAL_DIR.iterdir():
            if candidate.name == wanted:
                return candidate
    raise HTTPException(status_code=404, detail=f"File non trovato: {filename}{suffix}")


def _iter_result_files() -> list[Path]:
    if not FINAL_DIR.exists():
        return []
    return [f for f in FINAL_DIR.glob("*.json") if not f.name.endswith("_summary.json")]


@app.get("/healthz", tags=["Infra"])
def healthz() -> dict:
    return {"status": "ok", "service": "results-service"}


@app.get("/results", tags=["Results"])
def list_results() -> list[dict]:
    output = []
    for json_path in _iter_result_files():
        try:
            filename     = json_path.stem
            summary_path = FINAL_DIR / f"{filename}_summary.json"
            summary      = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else {}
            csv_path     = FINAL_DIR / f"{filename}.csv"

            n_records = summary.get("total_records")
            if n_records is None:
                n_records = len(json.loads(json_path.read_text(encoding="utf-8")))

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
    return _load_json(_safe_path(filename, ".json"))


@app.get("/results/{filename}/summary", tags=["Results"])
def get_result_summary(filename: str, request: Request) -> JSONResponse:
    path = _safe_path(filename, "_summary.json")
    content = path.read_bytes()
    etag = f'"{hashlib.md5(content).hexdigest()}"'
    if request.headers.get("if-none-match") == etag:
        return JSONResponse(status_code=304, content=None, headers={"ETag": etag})
    return JSONResponse(
        content=json.loads(content),
        headers={"ETag": etag, "Cache-Control": "max-age=3600"},
    )


@app.get("/download/{filename}/json", tags=["Download"])
def download_json(filename: str) -> FileResponse:
    path = _safe_path(filename, ".json")
    return FileResponse(path, media_type="application/json", filename=path.name)


@app.get("/download/{filename}/csv", tags=["Download"])
def download_csv(filename: str) -> FileResponse:
    path = _safe_path(filename, ".csv")
    return FileResponse(path, media_type="text/csv; charset=utf-8", filename=path.name)
