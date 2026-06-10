#!/usr/bin/env bash
# Start all bot instances in background with separate log files.
# Usage: ./scripts/start_all.sh [--stop]

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOGS_DIR="$PROJECT_ROOT/logs"
mkdir -p "$LOGS_DIR"

PID_FILE="$LOGS_DIR/instances.pid"

stop_all() {
    if [[ ! -f "$PID_FILE" ]]; then
        echo "No PID file found at $PID_FILE — nothing to stop."
        return
    fi
    echo "Stopping instances..."
    while IFS='|' read -r name pid; do
        if kill -0 "$pid" 2>/dev/null; then
            kill "$pid"
            echo "  Stopped $name (pid $pid)"
        else
            echo "  $name (pid $pid) was already stopped"
        fi
    done < "$PID_FILE"
    rm -f "$PID_FILE"
    echo "Done."
}

if [[ "${1:-}" == "--stop" ]]; then
    stop_all
    exit 0
fi

if [[ -f "$PID_FILE" ]]; then
    echo "WARNING: PID file already exists ($PID_FILE). Run with --stop first."
    exit 1
fi

declare -a INSTANCES=(
    "v1|.env|8000"
    "v2|.env.v2|8011"
)

echo "Starting instances..."
> "$PID_FILE"

for entry in "${INSTANCES[@]}"; do
    IFS='|' read -r name env_file port <<< "$entry"
    log="$LOGS_DIR/backend_${name}.log"
    env_path="$PROJECT_ROOT/$env_file"

    if [[ ! -f "$env_path" ]]; then
        echo "  SKIP $name — $env_path not found"
        continue
    fi

    ENV_FILE="$env_path" python -m uvicorn backend.main:app \
        --port "$port" \
        --log-level info \
        >> "$log" 2>&1 &
    pid=$!
    echo "${name}|${pid}" >> "$PID_FILE"
    echo "  Started $name (pid $pid, port $port) → $log"
done

echo ""
echo "All instances started. Logs in $LOGS_DIR/"
echo "To stop: ./scripts/start_all.sh --stop"
echo "To tail V1: tail -f $LOGS_DIR/backend_v1.log"
echo "To tail V2: tail -f $LOGS_DIR/backend_v2.log"
