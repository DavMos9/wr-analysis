#!/usr/bin/env python3
"""
merge_from_light.py — Merge dei file di wr-analysis-light nel volume Docker.

Per ogni file (target, topic) presente in LIGHT_FINAL_DIR:
  1. Estrae il file corrispondente dal volume Docker (pipeline-service:/app/data/final/)
  2. Deduplica i record light contro quelli Docker (stessa logica del pipeline)
  3. Aggiunge solo i record nuovi al file Docker
  4. Rigenera summary e CSV con i dati aggiornati

Esegui dalla cartella wr-analysis:
    python3 merge_from_light.py

Requisiti:
  - Docker in esecuzione con i container avviati (docker compose up -d)
  - wr-analysis-light nella cartella sorella (../wr-analysis-light)
"""
from __future__ import annotations

import csv
import json
import logging
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ── Configurazione ────────────────────────────────────────────────────────────

SCRIPT_DIR     = Path(__file__).parent
LIGHT_DIR      = SCRIPT_DIR.parent / "wr-analysis-light"
LIGHT_FINAL    = LIGHT_DIR / "data" / "final"
CONTAINER_NAME = "pipeline-service"          # nome servizio in docker-compose.yml
CONTAINER_PATH = "/app/data/final"


# ── Deduplicazione (replica esatta della logica pipeline) ─────────────────────

def _norm_text(text: str) -> str:
    t = text.lower().strip()
    return re.sub(r"\s+", " ", t)

def _norm_title(title: str) -> str:
    t = re.sub(r"[^\w\s]", "", title.lower())
    return re.sub(r"\s+", " ", t).strip()

def _key(record: dict) -> str | None:
    text  = (record.get("text")  or "").strip()
    title = (record.get("title") or "").strip()
    if text:
        return _norm_text(text)
    if title:
        return f"__title__{_norm_title(title)}"
    return None

def deduplicate_against(new_records: list[dict], existing: list[dict]) -> list[dict]:
    """Restituisce solo i record di new_records non già presenti in existing."""
    seen = set()
    for r in existing:
        k = _key(r)
        if k:
            seen.add(k)
    result = []
    for r in new_records:
        k = _key(r)
        if k is None or k not in seen:
            seen.add(k) if k else None
            result.append(r)
    return result


# ── Summary ───────────────────────────────────────────────────────────────────

def build_summary(records: list[dict], target: str, topic: str) -> dict:
    dates   = [r["date"] for r in records if r.get("date")]
    sources = {}
    for r in records:
        src = r.get("source", "")
        sources[src] = sources.get(src, 0) + 1

    return {
        "target":         target,
        "topic":          topic,
        "execution_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "scan_timestamp": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        "total_records":  len(records),
        "date_range": {
            "from": min(dates) if dates else None,
            "to":   max(dates) if dates else None,
        },
        "sources": sources,
    }


# ── CSV ───────────────────────────────────────────────────────────────────────

CSV_FIELDS = ["source", "title", "text", "domain", "language",
              "sentiment", "date", "url", "target", "topic"]

def build_csv(records: list[dict], path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)


# ── Docker helpers ────────────────────────────────────────────────────────────

def _docker_compose(args: list[str]) -> subprocess.CompletedProcess:
    cmd = ["docker", "compose"] + args
    return subprocess.run(cmd, capture_output=True, text=True, cwd=SCRIPT_DIR)


def container_id() -> str:
    """Restituisce il container ID del pipeline-service in esecuzione."""
    result = _docker_compose(["ps", "-q", CONTAINER_NAME])
    cid = result.stdout.strip()
    if not cid:
        log.error("Container '%s' non trovato o non in esecuzione.", CONTAINER_NAME)
        log.error("Esegui: docker compose up -d")
        sys.exit(1)
    return cid


def docker_cp_from(container: str, src: str, dst: Path) -> None:
    result = subprocess.run(
        ["docker", "cp", f"{container}:{src}", str(dst)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"docker cp fallito: {result.stderr}")


def docker_cp_to(src: Path, container: str, dst: str) -> None:
    result = subprocess.run(
        ["docker", "cp", str(src), f"{container}:{dst}"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"docker cp fallito: {result.stderr}")


# ── Merge ─────────────────────────────────────────────────────────────────────

def merge_file(stem: str, cid: str, tmp: Path) -> None:
    """Mergia un singolo (target, topic) da light nel volume Docker."""
    light_json = LIGHT_FINAL / f"{stem}.json"
    if not light_json.exists():
        log.warning("File light non trovato, saltato: %s", light_json)
        return

    light_records: list[dict] = json.loads(light_json.read_text(encoding="utf-8"))
    log.info("[%s] Light: %d record", stem, len(light_records))

    # Estrai il file corrente dal volume Docker (potrebbe non esistere)
    docker_json = tmp / f"{stem}.json"
    try:
        docker_cp_from(cid, f"{CONTAINER_PATH}/{stem}.json", docker_json)
        docker_records: list[dict] = json.loads(docker_json.read_text(encoding="utf-8"))
        log.info("[%s] Docker: %d record esistenti", stem, len(docker_records))
    except Exception:
        log.info("[%s] Nessun file Docker esistente — copia diretta.", stem)
        docker_records = []

    # Deduplicazione: aggiungi solo i record light non presenti in Docker
    new_only = deduplicate_against(light_records, docker_records)
    log.info("[%s] Nuovi da aggiungere: %d", stem, len(new_only))

    if not new_only:
        log.info("[%s] Nessun record nuovo, saltato.", stem)
        return

    merged = docker_records + new_only

    # Ricava target e topic dai record (o dal summary light)
    light_summary_path = LIGHT_FINAL / f"{stem}_summary.json"
    if light_summary_path.exists():
        ls = json.loads(light_summary_path.read_text(encoding="utf-8"))
        target = ls.get("target", stem)
        topic  = ls.get("topic", "")
    else:
        target = merged[0].get("target", stem) if merged else stem
        topic  = merged[0].get("topic",  "")  if merged else ""

    # Scrivi JSON, summary, CSV nella cartella tmp
    merged_json    = tmp / f"{stem}.json"
    merged_summary = tmp / f"{stem}_summary.json"
    merged_csv     = tmp / f"{stem}.csv"

    merged_json.write_text(
        json.dumps(merged, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    merged_summary.write_text(
        json.dumps(build_summary(merged, target, topic), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    build_csv(merged, merged_csv)

    # Carica i file aggiornati nel volume Docker
    for local_file in [merged_json, merged_summary, merged_csv]:
        docker_cp_to(local_file, cid, f"{CONTAINER_PATH}/{local_file.name}")
        log.info("[%s] → Docker: %s", stem, local_file.name)

    log.info("[%s] ✓ Merge completato: %d → %d record (+%d)",
             stem, len(docker_records), len(merged), len(new_only))


def main() -> None:
    if not LIGHT_FINAL.exists():
        log.error("Cartella light non trovata: %s", LIGHT_FINAL)
        sys.exit(1)

    cid = container_id()
    log.info("Container pipeline-service: %s", cid[:12])

    stems = sorted({p.stem for p in LIGHT_FINAL.glob("*.json")
                    if not p.name.endswith("_summary.json")})

    if not stems:
        log.warning("Nessun file JSON trovato in %s", LIGHT_FINAL)
        sys.exit(0)

    log.info("File da mergiare: %s", stems)

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp = Path(tmp_dir)
        for stem in stems:
            merge_file(stem, cid, tmp)

    log.info("Merge completato per tutti i file.")


if __name__ == "__main__":
    main()
