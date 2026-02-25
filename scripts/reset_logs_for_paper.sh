#!/usr/bin/env bash
set -euo pipefail

# Reset operational CSV logs before a fresh paper-mode run.
# Keeps pipeline datasets and runtime config untouched.
#
# Usage:
#   bash scripts/reset_logs_for_paper.sh
#   bash scripts/reset_logs_for_paper.sh --include-backend-log

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="${ROOT_DIR}/backtest_output"
INCLUDE_BACKEND_LOG="false"

for arg in "$@"; do
  case "$arg" in
    --include-backend-log)
      INCLUDE_BACKEND_LOG="true"
      ;;
    *)
      echo "Unknown arg: $arg"
      echo "Usage: bash scripts/reset_logs_for_paper.sh [--include-backend-log]"
      exit 1
      ;;
  esac
done

STAMP="$(date +%F_%H%M%S)"
ARCHIVE_DIR="${LOG_DIR}/archive_${STAMP}"
mkdir -p "${ARCHIVE_DIR}"

FILES_TO_ARCHIVE=(
  "paper_trades.csv"
  "opportunities_log.csv"
  "opportunity_outcomes.csv"
  "opportunity_blocked.csv"
  "order_blocked_log.csv"
)

TODAY_BOT_FILE="bot_orders_$(date +%F).csv"
if [[ -f "${LOG_DIR}/${TODAY_BOT_FILE}" ]]; then
  FILES_TO_ARCHIVE+=("${TODAY_BOT_FILE}")
fi

if [[ "${INCLUDE_BACKEND_LOG}" == "true" && -f "${ROOT_DIR}/backend.log" ]]; then
  FILES_TO_ARCHIVE+=("../backend.log")
fi

echo "Archive dir: ${ARCHIVE_DIR}"
for rel in "${FILES_TO_ARCHIVE[@]}"; do
  src="${LOG_DIR}/${rel}"
  if [[ "${rel}" == "../backend.log" ]]; then
    src="${ROOT_DIR}/backend.log"
  fi

  if [[ -f "${src}" ]]; then
    base="$(basename "${src}")"
    cp "${src}" "${ARCHIVE_DIR}/${base}"
    echo "Archived: ${src}"
  fi
done

# Remove current run logs (safe; files are recreated by backend when needed).
rm -f "${LOG_DIR}/paper_trades.csv"
rm -f "${LOG_DIR}/opportunities_log.csv"
rm -f "${LOG_DIR}/opportunity_outcomes.csv"
rm -f "${LOG_DIR}/opportunity_blocked.csv"
rm -f "${LOG_DIR}/order_blocked_log.csv"
rm -f "${LOG_DIR}/${TODAY_BOT_FILE}"

if [[ "${INCLUDE_BACKEND_LOG}" == "true" ]]; then
  : > "${ROOT_DIR}/backend.log"
  echo "Truncated: ${ROOT_DIR}/backend.log"
fi

echo
echo "Done."
echo "Cleaned operational logs for fresh paper-mode run."
echo "Left untouched:"
echo "- config/runtime_settings.json"
echo "- backtest_output/merged_pm_5m_slot_ranges_4cryptos.csv"
