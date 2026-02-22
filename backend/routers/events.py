"""REST endpoints for events data."""

import csv
from typing import Any

from fastapi import APIRouter, HTTPException

from ..config import get_trading_config, get_ui_config, load_events_config
from ..services.event_manager import event_manager
from ..ws.manager import manager

router = APIRouter(prefix="/api", tags=["events"])


@router.get("/events")
async def get_events():
    """Get all current events with their data."""
    return {"events": event_manager.events, "settings": event_manager.settings}


@router.get("/events/{event_id}")
async def get_event(event_id: str):
    """Get a single event by ID."""
    event = event_manager.events.get(event_id)
    if not event:
        raise HTTPException(status_code=404, detail=f"Event '{event_id}' not found")
    return event


@router.get("/config")
async def get_config():
    """Get application configuration (trading + UI)."""
    config = load_events_config()
    return {
        "trading": get_trading_config(config),
        "ui": get_ui_config(config),
    }


@router.post("/settings")
async def save_settings(payload: dict[str, Any]):
    """Persist runtime settings via REST (useful fallback when WS is unstable)."""
    incoming = payload.get("settings", payload)
    if not isinstance(incoming, dict):
        raise HTTPException(status_code=400, detail="Invalid settings payload")

    updated = 0
    for key, value in incoming.items():
        if key == "mode":
            continue
        if key in event_manager._persisted_setting_keys:
            event_manager.settings[key] = value
            updated += 1

    event_manager.persist_runtime_settings()
    await manager.broadcast(
        {
            "type": "settings_update",
            "event_id": "",
            "data": event_manager.settings,
        }
    )
    return {"ok": True, "updated_keys": updated, "settings": event_manager.settings}


@router.get("/pm-ranges/{ticker}")
async def get_pm_ranges(ticker: str):
    """Return the quantitative PM probability table for a given ticker."""
    ticker_upper = ticker.strip().upper()
    data = event_manager._pm_ranges.get(ticker_upper)
    if data is None:
        raise HTTPException(
            status_code=404,
            detail=f"No PM ranges data for ticker '{ticker_upper}'. Available: {list(event_manager._pm_ranges.keys())}",
        )
    result = {}
    for minute, ranges in data.items():
        result[str(minute)] = [
            {
                "inf_range": r[0],
                "sup_range": r[1],
                "prob_up": r[2],
                "prob_down": r[3],
                "count": r[4],
            }
            for r in ranges
        ]
    return {"ticker": ticker_upper, "ranges": result}


@router.post("/events/refresh-live")
async def refresh_live_events(force: bool = True):
    """Force refresh of live-discovered events and broadcast to all clients."""
    result = await event_manager.refresh_live_events(force=force)

    if not result.get("ok"):
        reason = result.get("reason", "refresh_failed")
        if reason == "mode_not_live":
            raise HTTPException(
                status_code=409,
                detail="Live refresh is only available when mode is 'live'",
            )
        if reason == "live_discovery_disabled":
            raise HTTPException(
                status_code=409,
                detail="live_discovery.enabled is false in config/events.yaml",
            )
        raise HTTPException(status_code=500, detail=f"Live refresh failed: {reason}")

    return result


@router.post("/quant/reload")
async def reload_quant_ranges():
    """Hot-reload the merged PM 5m slot ranges CSV without restarting the backend."""
    result = event_manager.reload_quant_ranges()
    await manager.broadcast({
        "type": "quant_reload",
        "event_id": "",
        "data": result,
    })
    return result


@router.get("/stats/opportunities")
async def get_opportunity_stats(days: int = 7, ticker: str | None = None):
    """Return per-ticker opportunity outcomes summary."""
    summary = event_manager._opportunity_tracker.summarize_outcomes(
        days=days,
        ticker=ticker,
    )
    return {
        "days": max(1, int(days)),
        "ticker_filter": ticker.upper() if ticker else None,
        "summary": summary,
    }


@router.get("/stats/opportunities/raw")
async def get_opportunity_outcomes_raw(limit: int = 200, ticker: str | None = None):
    """Return raw recent opportunity outcomes rows."""
    path = event_manager._opportunity_tracker.outcomes_path
    rows: list[dict] = []
    try:
        with open(path, newline="") as f:
            for row in csv.DictReader(f):
                row_ticker = str(row.get("ticker", "")).upper()
                if ticker and row_ticker != ticker.upper():
                    continue
                rows.append(row)
    except FileNotFoundError:
        rows = []
    rows = rows[-max(1, int(limit)) :]
    return {
        "count": len(rows),
        "ticker_filter": ticker.upper() if ticker else None,
        "rows": rows,
    }


@router.get("/stats/opportunities/signals/raw")
async def get_opportunity_signals_raw(limit: int = 200, ticker: str | None = None):
    """Return raw recent registered opportunity signals rows."""
    path = event_manager._opportunity_tracker.signals_path
    rows: list[dict] = []
    try:
        with open(path, newline="") as f:
            for row in csv.DictReader(f):
                row_ticker = str(row.get("ticker", "")).upper()
                if ticker and row_ticker != ticker.upper():
                    continue
                rows.append(row)
    except FileNotFoundError:
        rows = []
    rows = rows[-max(1, int(limit)) :]
    return {
        "count": len(rows),
        "ticker_filter": ticker.upper() if ticker else None,
        "rows": rows,
    }


@router.get("/stats/opportunities/blocked/raw")
async def get_opportunity_blocked_raw(limit: int = 200, ticker: str | None = None):
    """Return raw recent blocked opportunity rows (not registered as signals)."""
    path = event_manager._opportunity_tracker.blocked_path
    rows: list[dict] = []
    try:
        with open(path, newline="") as f:
            for row in csv.DictReader(f):
                row_ticker = str(row.get("ticker", "")).upper()
                if ticker and row_ticker != ticker.upper():
                    continue
                rows.append(row)
    except FileNotFoundError:
        rows = []
    rows = rows[-max(1, int(limit)) :]
    return {
        "count": len(rows),
        "ticker_filter": ticker.upper() if ticker else None,
        "rows": rows,
    }
