"""Internal control service used by localhost-only control API and Telegram bot."""

from __future__ import annotations

import asyncio
import csv
import json
import logging
import os
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..services.event_manager import event_manager
from ..services.polymarket import get_client
from ..ws.manager import manager

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", _PROJECT_ROOT / "backtest_output"))
_AUDIT_LOG_PATH = _OUTPUT_DIR / "control_audit.jsonl"
_RESTART_REQUEST_PATH = _OUTPUT_DIR / "control_restart_requests.jsonl"
_CONTROL_LOG_FILE = os.environ.get("CONTROL_LOG_FILE", "").strip()
_DEFAULT_LOG_PATH = Path(_CONTROL_LOG_FILE).expanduser() if _CONTROL_LOG_FILE else None
_HEALTH_STALE_SECONDS = int(os.environ.get("CONTROL_HEALTH_STALE_SECONDS", "15"))
_ENGINE_INSTANCE_ID = (
    os.environ.get("ENGINE_INSTANCE_ID", "default").strip() or "default"
)
_ENGINE_WALLET_LABEL = os.environ.get("ENGINE_WALLET_LABEL", "").strip()


def _instance_metadata() -> dict[str, Any]:
    return {
        "instance_id": _ENGINE_INSTANCE_ID,
        "wallet_label": _ENGINE_WALLET_LABEL or _ENGINE_INSTANCE_ID,
        "app_env": os.environ.get("APP_ENV", "dev"),
    }


def _now_utc() -> datetime:
    return datetime.now(tz=timezone.utc)


def _safe_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=True, sort_keys=True) + "\n")


def _tail_lines(path: Path, lines: int) -> list[str]:
    if not path or not path.exists() or lines <= 0:
        return []
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        return list(deque((line.rstrip("\n") for line in fh), maxlen=lines))


def _today_bot_orders_path() -> Path:
    return _OUTPUT_DIR / f"bot_orders_{_now_utc().strftime('%Y-%m-%d')}.csv"


class ControlService:
    """Thin control facade over EventManager and existing backend services."""

    async def get_instance_info(self) -> dict[str, Any]:
        return _instance_metadata()

    async def get_status(self) -> dict[str, Any]:
        now = _now_utc()
        last_tick = event_manager._last_price_tick_at
        seconds_since_tick = (
            round((now - last_tick).total_seconds(), 2) if last_tick else None
        )
        return {
            **_instance_metadata(),
            "engine_running": bool(event_manager._running),
            "engine_mode": event_manager.mode,
            "trading_mode": "paper"
            if bool(event_manager.settings.get("bot_paper_mode", False))
            else "live",
            "execution_enabled": bool(
                event_manager.settings.get("execution_enabled", False)
            ),
            "events_count": len(event_manager.events),
            "monitored_tickers": list(
                event_manager.settings.get("monitored_tickers", [])
            ),
            "last_price_tick_at": last_tick.isoformat() if last_tick else None,
            "seconds_since_last_tick": seconds_since_tick,
            "streamer_stalled": (
                seconds_since_tick is not None
                and seconds_since_tick > _HEALTH_STALE_SECONDS
            ),
            "updated_at_utc": now.isoformat(),
        }

    async def get_health(self) -> dict[str, Any]:
        status = await self.get_status()
        checks = {
            "engine_running": bool(status["engine_running"]),
            "has_events": status["events_count"] > 0,
            "price_stream_recent": not bool(status["streamer_stalled"]),
        }
        if not checks["engine_running"]:
            health = "down"
        elif all(checks.values()):
            health = "ok"
        else:
            health = "degraded"
        status["health"] = health
        status["checks"] = checks
        return status

    async def get_pnl_today(self) -> dict[str, Any]:
        rows: list[dict[str, Any]] = []
        using_paper = bool(event_manager.settings.get("bot_paper_mode", False)) or (
            event_manager.mode == "demo"
        )
        source = "paper_trades" if using_paper else "bot_orders"
        path = (
            _OUTPUT_DIR / "paper_trades.csv"
            if using_paper
            else _today_bot_orders_path()
        )
        if path.exists():
            with path.open(newline="", encoding="utf-8") as fh:
                loaded_rows = list(csv.DictReader(fh))
            if using_paper:
                today = _now_utc().date().isoformat()
                rows = [
                    row
                    for row in loaded_rows
                    if str(row.get("decision_time", "")).startswith(today)
                ]
            else:
                rows = loaded_rows

        pnl_values = [_safe_float(row.get("pnl_simulated")) for row in rows]
        resolved_rows = [
            row
            for row, pnl in zip(rows, pnl_values)
            if pnl is not None and row is not None
        ]
        resolved_pnls = [pnl for pnl in pnl_values if pnl is not None]
        wins = sum(1 for pnl in resolved_pnls if pnl > 0)
        losses = sum(1 for pnl in resolved_pnls if pnl < 0)
        return {
            **_instance_metadata(),
            "source": source,
            "rows": len(rows),
            "resolved_rows": len(resolved_rows),
            "wins": wins,
            "losses": losses,
            "net_pnl_usd": round(sum(resolved_pnls), 4),
            "path": str(path),
            "updated_at_utc": _now_utc().isoformat(),
        }

    async def get_positions(self) -> dict[str, Any]:
        positions: list[dict[str, Any]] = []
        total_cost = 0.0
        total_value = 0.0
        for event_id, event in event_manager.events.items():
            tracked = event_manager.get_tracked_positions(event_id)
            if not tracked:
                continue
            for outcome_key, pos in tracked.items():
                current_price = float(
                    event.get("yes_price", pos.get("avg_price", 0.0))
                    if outcome_key == "up"
                    else event.get("no_price", pos.get("avg_price", 0.0))
                )
                qty = float(pos.get("shares", 0.0) or 0.0)
                avg_price = float(pos.get("avg_price", 0.0) or 0.0)
                cost = round(qty * avg_price, 4)
                value = round(qty * current_price, 4)
                total_cost += cost
                total_value += value
                positions.append(
                    {
                        "event_id": event_id,
                        "name": event.get("name", event_id),
                        "ticker": event.get("ticker", ""),
                        "outcome": outcome_key,
                        "shares": round(qty, 4),
                        "avg_price": round(avg_price, 4),
                        "current_price": round(current_price, 4),
                        "cost_usd": cost,
                        "value_usd": value,
                        "pnl_usd": round(value - cost, 4),
                        "placed_at_utc": pos.get("placed_at_utc", ""),
                    }
                )
        positions.sort(key=lambda row: row["value_usd"], reverse=True)
        return {
            **_instance_metadata(),
            "positions": positions,
            "count": len(positions),
            "total_cost_usd": round(total_cost, 4),
            "total_value_usd": round(total_value, 4),
            "total_pnl_usd": round(total_value - total_cost, 4),
        }

    async def get_orders(self) -> dict[str, Any]:
        if event_manager.mode == "demo":
            return {
                **_instance_metadata(),
                "orders": [],
                "count": 0,
                "message": "demo mode",
            }
        client = get_client()
        if not client:
            return {
                **_instance_metadata(),
                "orders": [],
                "count": 0,
                "message": "Polymarket client unavailable",
            }
        orders = await asyncio.to_thread(client.get_open_orders)
        if not isinstance(orders, list):
            orders = list(orders or [])
        return {**_instance_metadata(), "orders": orders, "count": len(orders)}

    async def pause(self, actor: dict[str, Any] | None = None) -> dict[str, Any]:
        return await self._set_execution_enabled(False, actor=actor)

    async def resume(self, actor: dict[str, Any] | None = None) -> dict[str, Any]:
        return await self._set_execution_enabled(True, actor=actor)

    async def set_trading_mode(
        self, target_mode: str, actor: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        normalized = str(target_mode).strip().lower()
        if normalized not in {"paper", "live"}:
            raise ValueError("mode must be 'paper' or 'live'")
        if normalized == "live" and event_manager.mode != "live":
            raise RuntimeError(
                "Engine feed mode is not 'live'; refusing to enable live execution"
            )
        event_manager.settings["bot_paper_mode"] = normalized == "paper"
        event_manager.persist_runtime_settings()
        await manager.broadcast(
            {"type": "settings_update", "event_id": "", "data": event_manager.settings}
        )
        payload = {
            **_instance_metadata(),
            "ok": True,
            "trading_mode": normalized,
            "engine_mode": event_manager.mode,
            "execution_enabled": bool(
                event_manager.settings.get("execution_enabled", False)
            ),
            "updated_at_utc": _now_utc().isoformat(),
        }
        self.audit("mode", actor=actor, ok=True, result=payload)
        return payload

    async def request_restart(
        self, actor: dict[str, Any] | None = None, reason: str = "remote_request"
    ) -> dict[str, Any]:
        payload = {
            **_instance_metadata(),
            "requested_at_utc": _now_utc().isoformat(),
            "reason": reason,
            "pid": os.getpid(),
            "actor": actor or {},
            "supported": False,
            "message": "Restart hook recorded. An external supervisor is still required.",
        }
        _append_jsonl(_RESTART_REQUEST_PATH, payload)
        self.audit("restart", actor=actor, ok=True, result=payload)
        return payload

    async def get_logs(self, lines: int = 50) -> dict[str, Any]:
        lines = max(1, min(int(lines), 200))
        log_path = _DEFAULT_LOG_PATH if _DEFAULT_LOG_PATH else _AUDIT_LOG_PATH
        content = _tail_lines(log_path, lines)
        return {
            **_instance_metadata(),
            "path": str(log_path),
            "lines": content,
            "count": len(content),
        }

    async def _set_execution_enabled(
        self, enabled: bool, actor: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        event_manager.settings["execution_enabled"] = enabled
        event_manager.persist_runtime_settings()
        await manager.broadcast(
            {"type": "settings_update", "event_id": "", "data": event_manager.settings}
        )
        payload = {
            **_instance_metadata(),
            "ok": True,
            "execution_enabled": enabled,
            "trading_mode": "paper"
            if bool(event_manager.settings.get("bot_paper_mode", False))
            else "live",
            "updated_at_utc": _now_utc().isoformat(),
        }
        self.audit(
            "resume" if enabled else "pause", actor=actor, ok=True, result=payload
        )
        return payload

    def audit(
        self,
        action: str,
        *,
        actor: dict[str, Any] | None,
        ok: bool,
        result: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        payload = {
            "timestamp_utc": _now_utc().isoformat(),
            "action": action,
            "ok": ok,
            "actor": actor or {},
            "result": result or {},
            "error": error or "",
        }
        try:
            _append_jsonl(_AUDIT_LOG_PATH, payload)
        except Exception as exc:
            logger.warning("Could not append control audit log: %s", exc)


control_service = ControlService()
