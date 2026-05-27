#!/usr/bin/env zsh
# start.sh — Avvia tutti i servizi di wr-analysis in background.
# Uso: ./start.sh
# Log: logs/  |  PID: .pids

set -euo pipefail

SCRIPT_DIR="${0:A:h}"
cd "$SCRIPT_DIR"

DATA_DIR="$SCRIPT_DIR/data"
LOGS_DIR="$SCRIPT_DIR/logs"
PIDS_FILE="$SCRIPT_DIR/.pids"
CORE_DIR="$SCRIPT_DIR/../wr-analysis-light"
FRONTEND_DIR="$SCRIPT_DIR/services/frontend"

# ── Controllo: già in esecuzione? ─────────────────────────────────────────────
if [[ -f "$PIDS_FILE" ]]; then
  echo "⚠️  Sembra che i servizi siano già avviati (.pids esiste)."
  echo "   Esegui ./stop.sh prima di riavviare."
  exit 1
fi

# ── Prerequisiti ──────────────────────────────────────────────────────────────
if ! command -v python3 &>/dev/null; then
  echo "❌ python3 non trovato."; exit 1
fi
if ! command -v uvicorn &>/dev/null && ! python3 -m uvicorn --version &>/dev/null 2>&1; then
  echo "❌ uvicorn non trovato. Installa con: pip3 install uvicorn --break-system-packages"; exit 1
fi
if [[ ! -d "$CORE_DIR" ]]; then
  echo "❌ wr-analysis-light non trovato in $CORE_DIR"; exit 1
fi

mkdir -p "$DATA_DIR/final" "$DATA_DIR/raw" "$LOGS_DIR"

# ── Carica variabili d'ambiente dal .env ──────────────────────────────────────
if [[ -f "$SCRIPT_DIR/.env" ]]; then
  set -o allexport
  source "$SCRIPT_DIR/.env"
  set +o allexport
fi

export DATA_DIR
export PYTHONPATH="$CORE_DIR"
export PIPELINE_SERVICE_URL="http://localhost:8001"

echo "🚀 Avvio wr-analysis..."

# ── Pipeline Service :8001 ────────────────────────────────────────────────────
python3 -m uvicorn main:app --port 8001 \
  --app-dir "$SCRIPT_DIR/services/pipeline_service" \
  >> "$LOGS_DIR/pipeline.log" 2>&1 &
echo $! >> "$PIDS_FILE"
echo "  ✓ pipeline-service   → http://localhost:8001"

# ── Results Service :8002 ─────────────────────────────────────────────────────
python3 -m uvicorn main:app --port 8002 \
  --app-dir "$SCRIPT_DIR/services/results_service" \
  >> "$LOGS_DIR/results.log" 2>&1 &
echo $! >> "$PIDS_FILE"
echo "  ✓ results-service    → http://localhost:8002"

# ── Scheduler Service :8003 ───────────────────────────────────────────────────
python3 -m uvicorn main:app --port 8003 \
  --app-dir "$SCRIPT_DIR/services/scheduler_service" \
  >> "$LOGS_DIR/scheduler.log" 2>&1 &
echo $! >> "$PIDS_FILE"
echo "  ✓ scheduler-service  → http://localhost:8003"

# ── Frontend (Vite) :3000 ─────────────────────────────────────────────────────
# Installa le dipendenze se node_modules è assente o incompleto
if [[ ! -f "$FRONTEND_DIR/node_modules/.package-lock.json" ]]; then
  echo "  📦 Installazione dipendenze frontend..."
  (cd "$FRONTEND_DIR" && NODE_ENV=development npm install --include=dev --silent)
fi

(cd "$FRONTEND_DIR" && NODE_ENV=development npx vite --port 3000 \
  >> "$LOGS_DIR/frontend.log" 2>&1) &
echo $! >> "$PIDS_FILE"
echo "  ✓ frontend (Vite)    → http://localhost:3000"

echo ""
echo "✅ Tutti i servizi avviati. Dashboard: http://localhost:3000"
echo "   Log:  tail -f $LOGS_DIR/*.log"
echo "   Stop: ./stop.sh"
