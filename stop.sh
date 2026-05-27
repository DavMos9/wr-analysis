#!/usr/bin/env zsh
# stop.sh — Ferma tutti i servizi avviati da start.sh.

SCRIPT_DIR="${0:A:h}"
PIDS_FILE="$SCRIPT_DIR/.pids"

if [[ ! -f "$PIDS_FILE" ]]; then
  echo "ℹ️  Nessun servizio risulta avviato (.pids non trovato)."
  exit 0
fi

echo "🛑 Arresto servizi wr-analysis..."

while IFS= read -r pid; do
  if kill -0 "$pid" 2>/dev/null; then
    kill "$pid" && echo "  ✓ PID $pid terminato"
  else
    echo "  ℹ️  PID $pid già terminato"
  fi
done < "$PIDS_FILE"

rm -f "$PIDS_FILE"
echo "✅ Stop completato."
