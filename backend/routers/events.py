"""REST endpoints for events data."""

import csv
import io
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Response

from ..config import get_trading_config, get_ui_config, load_events_config
from ..services.event_manager import event_manager
from ..ws.manager import manager

router = APIRouter(prefix="/api", tags=["events"])


def _load_bot_orders_rows(
    *,
    ticker: str | None,
    days: int,
) -> list[dict[str, Any]]:
    root = Path("backtest_output")
    rows: list[dict[str, Any]] = []
    ticker_filter = ticker.upper() if ticker else None
    cutoff_day = datetime.now(tz=timezone.utc).date() - timedelta(
        days=max(1, int(days)) - 1
    )
    pattern = re.compile(r"^bot_orders_(\d{4}-\d{2}-\d{2})\.csv$")

    candidates: list[tuple[datetime, Path]] = []
    for path in root.glob("bot_orders_*.csv"):
        m = pattern.match(path.name)
        if not m:
            continue
        try:
            day = datetime.strptime(m.group(1), "%Y-%m-%d").date()
        except ValueError:
            continue
        if day < cutoff_day:
            continue
        candidates.append((datetime.combine(day, datetime.min.time()), path))

    for _, path in sorted(candidates, key=lambda x: x[0]):
        try:
            with open(path, newline="") as f:
                for row in csv.DictReader(f):
                    row_ticker = str(row.get("ticker", "")).upper()
                    if ticker_filter and row_ticker != ticker_filter:
                        continue
                    rows.append(row)
        except FileNotFoundError:
            continue
    rows.sort(key=lambda r: str(r.get("placed_at_utc", "")))
    return rows


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


@router.get("/debug/streams")
async def debug_streams():
    """Diagnose price streamer health."""
    from datetime import datetime, timezone

    now = datetime.now(tz=timezone.utc)
    last_tick = event_manager._last_price_tick_at
    seconds_since_tick = (now - last_tick).total_seconds() if last_tick else None
    return {
        "binance_streamers": len(event_manager._binance_streamers),
        "chainlink_streamers": len(event_manager._chainlink_streamers),
        "binance_tasks": [
            {"index": i, "done": t.done(), "cancelled": t.cancelled()}
            for i, t in enumerate(event_manager._binance_stream_tasks)
        ],
        "chainlink_tasks": [
            {"index": i, "done": t.done(), "cancelled": t.cancelled()}
            for i, t in enumerate(event_manager._chainlink_stream_tasks)
        ],
        "last_price_tick_at": last_tick.isoformat() if last_tick else None,
        "seconds_since_last_tick": round(seconds_since_tick, 1)
        if seconds_since_tick is not None
        else None,
        "streamer_stalled": seconds_since_tick is not None and seconds_since_tick > 10,
    }


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
    await manager.broadcast(
        {
            "type": "quant_reload",
            "event_id": "",
            "data": result,
        }
    )
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


@router.get("/stats/paper/raw")
async def get_paper_trades_raw(limit: int = 500, ticker: str | None = None):
    """Return raw paper-mode decision rows."""
    path = Path("backtest_output/paper_trades.csv")
    rows: list[dict[str, Any]] = []
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


@router.get("/stats/bot-orders/raw")
async def get_bot_orders_raw(
    limit: int = 500,
    ticker: str | None = None,
    days: int = 7,
):
    """Return raw bot order rows from daily bot_orders_YYYY-MM-DD.csv logs."""
    ticker_filter = ticker.upper() if ticker else None
    rows = _load_bot_orders_rows(ticker=ticker, days=days)
    rows = rows[-max(1, int(limit)) :]
    return {
        "count": len(rows),
        "ticker_filter": ticker_filter,
        "days": max(1, int(days)),
        "rows": rows,
    }


@router.get("/stats/bot-orders/export.csv")
async def export_bot_orders_csv(
    ticker: str | None = None,
    days: int = 7,
):
    """Export bot order rows as CSV."""
    rows = _load_bot_orders_rows(ticker=ticker, days=days)
    if rows:
        fieldnames = list(rows[0].keys())
    else:
        fieldnames = [
            "placed_at_utc",
            "event_id",
            "ticker",
            "side",
            "token_id",
            "shares",
            "price",
            "notional_usd",
            "order_id",
            "quant_prob",
            "edge_pct",
            "price_source_at_send",
            "price_to_beat_at_send",
            "current_price_at_send",
            "diff_vs_ptb_at_send",
            "best_bid_at_send",
            "best_ask_at_send",
            "mid_at_send",
            "spread_at_send",
            "spread_pct_at_send",
            "fill_price_real",
            "edge_at_fill_pct",
            "kelly_pct",
            "bankroll_usd",
            "percentile_at_signal",
            "status",
        ]
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        writer.writerow({k: row.get(k, "") for k in fieldnames})

    date_tag = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
    ticker_tag = ticker.upper() if ticker else "ALL"
    filename = f"bot_orders_export_{ticker_tag}_{date_tag}.csv"
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/stats/pipeline/ev-curve")
async def get_pipeline_ev_curve(
    ticker: str | None = None,
    min_count: int = 20,
):
    """Return an in-sample EV curve derived only from the merged pipeline CSV."""
    path = Path("backtest_output/merged_pm_5m_slot_ranges_4cryptos.csv")
    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Pipeline CSV not found: {path}",
        )

    ticker_filter = ticker.upper() if ticker else None
    rows: list[dict[str, Any]] = []
    total_samples = 0
    weighted_ev_sum = 0.0

    try:
        with open(path, newline="") as f:
            for row in csv.DictReader(f):
                row_ticker = str(row.get("ticker", "")).upper()
                if ticker_filter and row_ticker != ticker_filter:
                    continue

                try:
                    count = int(float(row.get("count_of_klines_inside_range", 0)))
                    slot = int(float(row.get("slot", 0)))
                    inf_range = float(row.get("inf_range", 0.0))
                    sup_range = float(row.get("sup_range", 0.0))
                    prob_up = float(row.get("prob_up", 0.5))
                    prob_down = float(row.get("prob_down", 0.5))
                except (TypeError, ValueError):
                    continue

                if count < max(1, int(min_count)):
                    continue
                if slot <= 0:
                    continue

                p_side = max(prob_up, prob_down)
                # EV per $1 risked assuming fair 50c entry for chosen side.
                ev_per_trade = (2.0 * p_side) - 1.0
                weighted_ev = ev_per_trade * count

                total_samples += count
                weighted_ev_sum += weighted_ev
                rows.append(
                    {
                        "ticker": row_ticker or "UNKNOWN",
                        "slot": slot,
                        "inf_range": inf_range,
                        "sup_range": sup_range,
                        "count": count,
                        "ev_per_trade_pct": ev_per_trade * 100.0,
                        "weighted_ev": weighted_ev,
                    }
                )
    except FileNotFoundError:
        rows = []

    rows.sort(
        key=lambda x: (
            int(x["slot"]),
            float(x["inf_range"]),
            str(x["ticker"]),
        )
    )

    cumulative_ev = 0.0
    peak_ev = 0.0
    points: list[dict[str, Any]] = []
    max_drawdown_pct = 0.0
    for idx, row in enumerate(rows, start=1):
        cumulative_ev += float(row["weighted_ev"])
        peak_ev = max(peak_ev, cumulative_ev)
        drawdown_pct = (
            ((cumulative_ev - peak_ev) / peak_ev * 100.0) if peak_ev > 0 else 0.0
        )
        max_drawdown_pct = min(max_drawdown_pct, drawdown_pct)
        points.append(
            {
                "idx": idx,
                "ticker": row["ticker"],
                "slot": row["slot"],
                "inf_range": row["inf_range"],
                "sup_range": row["sup_range"],
                "count": row["count"],
                "ev_per_trade_pct": row["ev_per_trade_pct"],
                "cumulative_ev": cumulative_ev,
                "drawdown_pct": drawdown_pct,
            }
        )

    avg_ev_per_trade_pct = (
        (weighted_ev_sum / total_samples) * 100.0 if total_samples > 0 else 0.0
    )
    return {
        "source": str(path),
        "ticker_filter": ticker_filter,
        "min_count": max(1, int(min_count)),
        "points_count": len(points),
        "total_samples": total_samples,
        "avg_ev_per_trade_pct": avg_ev_per_trade_pct,
        "final_cumulative_ev": cumulative_ev,
        "max_drawdown_pct": max_drawdown_pct,
        "points": points,
    }
