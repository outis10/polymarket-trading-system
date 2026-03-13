#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# update_quant.sh — Actualización diaria del análisis Quant
#
# Uso:
#   cd /home/narciso/dev/projects/polymarket-trading-system
#   bash scripts/update_quant.sh
#
# Opciones (variables de entorno):
#   LOOKBACK_DAYS   (default: 7)    días de historial Binance
#   MIN_COUNT       (default: 20)   mínimo de muestras por slot
#   EVENT_MINUTES   (default: "5")  duraciones de evento a procesar
#                   Ej: EVENT_MINUTES="5,15,60,240" para todos los tipos
#   SYMBOLS         (default: todos) Ej: SYMBOLS="BTCUSDT,ETHUSDT"
#   SKIP_DOWNLOAD   (default: "")   si no está vacío, reutiliza CSVs existentes
#   BACKEND_URL     (default: http://localhost:8000)
#   API_KEY         (default: "")
#
# Al terminar el pipeline, llama a /api/quant/reload para que el backend
# levante el nuevo CSV sin necesidad de reiniciar.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

LOOKBACK_DAYS="${LOOKBACK_DAYS:-7}"
MIN_COUNT="${MIN_COUNT:-20}"
EVENT_MINUTES="${EVENT_MINUTES:-5}"
SYMBOLS="${SYMBOLS:-}"
BACKEND_URL="${BACKEND_URL:-http://localhost:8000}"
API_KEY="${API_KEY:-}"
SKIP_DOWNLOAD="${SKIP_DOWNLOAD:-}"

echo "============================================================"
echo "  Polymarket Quant Update — $(date -u '+%Y-%m-%d %H:%M UTC')"
echo "  Lookback   : ${LOOKBACK_DAYS} days  |  Min-count: ${MIN_COUNT}"
echo "  Events     : ${EVENT_MINUTES}"
echo "============================================================"

cd "$PROJECT_DIR"

# Build optional args
EXTRA_ARGS=()
if [ -n "$SYMBOLS" ]; then
    EXTRA_ARGS+=("--symbols" "$SYMBOLS")
fi
if [ -n "$SKIP_DOWNLOAD" ]; then
    EXTRA_ARGS+=("--skip-download")
fi

# Run the pipeline
python3 run_pm_pipeline.py \
    --lookback-days "$LOOKBACK_DAYS" \
    --min-count "$MIN_COUNT" \
    --event-minutes "$EVENT_MINUTES" \
    "${EXTRA_ARGS[@]}"

echo ""
echo "Pipeline complete. Hot-reloading backend quant tables..."

# Hot-reload without restarting the backend
RELOAD_STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
    -X POST "${BACKEND_URL}/api/quant/reload" \
    ${API_KEY:+-H "X-API-Key: $API_KEY"})

if [ "$RELOAD_STATUS" = "200" ]; then
    echo "Backend reloaded successfully (HTTP 200)."
else
    echo "WARNING: Backend reload returned HTTP ${RELOAD_STATUS}."
    echo "  → Restart the backend manually to apply the new quant data."
fi

echo ""
echo "Done. New quant data is now active."
