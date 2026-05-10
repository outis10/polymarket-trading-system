"""REST endpoints for events data."""

import asyncio
import bisect
import csv
import io
import json
import os
import re
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Response

from ..config import get_trading_config, get_ui_config, load_events_config
from ..services.event_manager import event_manager
from ..services.volatility_monitor import volatility_monitor
from ..ws.manager import manager

router = APIRouter(prefix="/api", tags=["events"])


def _output_dir() -> Path:
    """Runtime output dir — reads from event_manager to respect OUTPUT_DIR env var."""
    return Path(event_manager._opportunity_tracker.base_dir)


def _normalize_paper_trade_row(r: dict) -> dict:
    """Map paper_trades.csv fields to bot_orders schema so the frontend can treat them uniformly."""
    pnl = r.get("pnl_simulated", "")
    try:
        won = "1" if float(pnl) > 0 else "0"
    except (ValueError, TypeError):
        won = ""
    status = r.get("status", "")
    resolution_status = "resolved" if status == "resolved" else "pending"
    try:
        edge_pct = (
            str(round(float(r["QuantumEdge"]) * 100, 4)) if r.get("QuantumEdge") else ""
        )
    except (ValueError, TypeError):
        edge_pct = ""
    try:
        edge_at_fill = (
            str(round(float(r["edge_at_fill_pct"]), 4))
            if r.get("edge_at_fill_pct")
            else ""
        )
    except (ValueError, TypeError):
        edge_at_fill = ""
    return {
        "placed_at_utc": r.get("decision_time", ""),
        "event_id": r.get("event_id", ""),
        "ticker": r.get("ticker", ""),
        "slot": r.get("slot", ""),
        "range": r.get("range", ""),
        "side": r.get("side_taken", ""),
        "event_end_utc_at_send": r.get("event_end_utc", ""),
        "token_id": "",
        "shares": r.get("shares_simulated", ""),
        "price": r.get("marketProb_at_decision", ""),
        "notional_usd": r.get("stake_usd", ""),
        "order_id": r.get("decision_id", ""),
        "quant_prob": r.get("prob_up", ""),
        "edge_pct": edge_pct,
        "price_source_at_send": r.get("price_source_at_decision", ""),
        "price_to_beat_at_send": r.get("price_to_beat_at_decision", ""),
        "current_price_at_send": r.get("current_price_at_decision", ""),
        "diff_vs_ptb_at_send": r.get("diff_vs_ptb_at_decision", ""),
        "best_bid_at_send": r.get("best_bid_at_decision", ""),
        "best_ask_at_send": r.get("best_ask_at_decision", ""),
        "mid_at_send": r.get("mid_at_decision", ""),
        "spread_at_send": r.get("spread_at_decision", ""),
        "spread_pct_at_send": r.get("spread_pct_at_decision", ""),
        "fill_price_real": r.get("fill_price_real", ""),
        "filled_at_utc": r.get("decision_time", ""),
        "fill_latency_ms": "",
        "slippage_pct": "",
        "filled_notional_usd_real": r.get("stake_usd", ""),
        "filled_shares_real": r.get("shares_simulated", ""),
        "fill_count": "",
        "fills_detail_json": "",
        "edge_at_fill_pct": edge_at_fill,
        "kelly_pct": "",
        "bankroll_usd": "",
        "percentile_at_signal": "",
        "close_price_at_resolution": r.get("close_price_at_resolution", ""),
        "event_outcome_real": r.get("event_outcome_real", ""),
        "won": won,
        "pnl_simulated": pnl,
        "resolution_status": resolution_status,
        "status": "placed",
    }


def _load_bot_orders_rows(
    *,
    ticker: str | None,
    days: int,
) -> list[dict[str, Any]]:
    root = _output_dir()
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
    changed_keys: set[str] = set()
    for key, value in incoming.items():
        if key == "mode":
            continue
        if key in event_manager._persisted_setting_keys:
            event_manager.settings[key] = value
            updated += 1
            changed_keys.add(key)

    event_manager.handle_runtime_settings_side_effects(changed_keys)
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
    """Hot-reload the merged PM 5m slot ranges CSV and runtime settings without restarting the backend."""
    event_manager._load_runtime_settings()
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


def _read_csv_rows(path, ticker: str | None, limit: int) -> list[dict]:
    """Read CSV file in a thread — keeps the event loop free."""
    max_rows = max(1, int(limit))
    rows: deque[dict] = deque(maxlen=max_rows)
    try:
        with open(path, newline="", encoding="utf-8", errors="replace") as f:
            sanitized = (line.replace("\x00", "") for line in f)
            for row in csv.DictReader(sanitized):
                if ticker and str(row.get("ticker", "")).upper() != ticker:
                    continue
                rows.append(row)
    except (FileNotFoundError, csv.Error):
        pass
    return list(rows)


def _read_jsonl_rows(path, ticker: str | None, limit: int) -> list[dict]:
    max_rows = max(1, int(limit))
    rows: deque[dict] = deque(maxlen=max_rows)
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for raw in f:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    row = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                row_ticker = str(row.get("ticker", "")).upper()
                row_asset = str(row.get("asset", "")).upper()
                if ticker and row_ticker != ticker and row_asset != ticker:
                    continue
                rows.append(row)
    except FileNotFoundError:
        pass
    return list(rows)


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _parse_float(value: Any) -> float | None:
    if value in ("", None):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _load_delay_model_rows(
    *,
    ticker: str | None,
    delay_seconds: float,
    max_lag_seconds: float,
) -> list[dict[str, Any]]:
    paper_path = _output_dir() / "paper_trades.csv"
    snapshot_path = _output_dir() / "orderbook_snapshots.jsonl"
    ticker_filter = ticker.upper() if ticker else None

    snapshots_by_key: dict[tuple[str, str], dict[str, list[Any]]] = {}
    try:
        with open(snapshot_path, encoding="utf-8", errors="replace") as f:
            for raw in f:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    row = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                event_id = str(row.get("event_id", "")).strip()
                book_side = str(row.get("book_side", "")).strip().lower()
                snap_ts = _parse_dt(row.get("timestamp_utc"))
                if not event_id or book_side not in ("yes", "no") or snap_ts is None:
                    continue
                key = (event_id, book_side)
                bucket = snapshots_by_key.setdefault(key, {"times": [], "rows": []})
                bucket["times"].append(snap_ts)
                bucket["rows"].append(row)
    except FileNotFoundError:
        return []

    result_rows: list[dict[str, Any]] = []
    try:
        with open(paper_path, newline="") as f:
            for row in csv.DictReader(f):
                row_ticker = str(row.get("ticker", "")).upper()
                if ticker_filter and row_ticker != ticker_filter:
                    continue

                decision_time = _parse_dt(row.get("decision_time"))
                if decision_time is None:
                    continue

                side_taken = str(row.get("side_taken", "")).lower()
                if side_taken == "up":
                    book_side = "yes"
                elif side_taken == "down":
                    book_side = "no"
                else:
                    continue

                event_id = str(row.get("event_id", "")).strip()
                target_time = decision_time + timedelta(seconds=delay_seconds)
                original_ask = _parse_float(row.get("best_ask_at_decision"))
                original_bid = _parse_float(row.get("best_bid_at_decision"))
                prob_up = _parse_float(row.get("prob_up"))
                if prob_up is None:
                    quant_prob_side = None
                else:
                    quant_prob_side = prob_up if side_taken == "up" else (1.0 - prob_up)
                original_edge_pct = (
                    (quant_prob_side - original_ask) * 100.0
                    if quant_prob_side is not None and original_ask is not None
                    else None
                )

                key = (event_id, book_side)
                bucket = snapshots_by_key.get(key)
                matched = False
                snapshot_row: dict[str, Any] | None = None
                snapshot_lag_ms: int | None = None
                delayed_best_bid = None
                delayed_best_ask = None
                delayed_spread = None
                delayed_edge_pct = None
                edge_decay_pct = None
                snapshot_reason = "no_snapshot"
                ask_depth_topn = None
                topn_depth_sufficient = None

                if bucket:
                    times: list[datetime] = bucket["times"]
                    rows_for_key: list[dict[str, Any]] = bucket["rows"]
                    idx = bisect.bisect_left(times, target_time)
                    if idx < len(times):
                        snapshot_row = rows_for_key[idx]
                        lag_ms = int((times[idx] - target_time).total_seconds() * 1000)
                        if lag_ms <= int(max_lag_seconds * 1000):
                            matched = True
                            snapshot_lag_ms = lag_ms
                            delayed_best_bid = _parse_float(snapshot_row.get("best_bid"))
                            delayed_best_ask = _parse_float(snapshot_row.get("best_ask"))
                            delayed_spread = _parse_float(snapshot_row.get("spread"))
                            ask_depth_topn = _parse_float(
                                snapshot_row.get("ask_depth_notional_topn")
                            )
                            stake_usd = _parse_float(row.get("stake_usd"))
                            if ask_depth_topn is not None and stake_usd is not None:
                                topn_depth_sufficient = stake_usd <= ask_depth_topn
                            if (
                                quant_prob_side is not None
                                and delayed_best_ask is not None
                            ):
                                delayed_edge_pct = (
                                    quant_prob_side - delayed_best_ask
                                ) * 100.0
                            if (
                                original_edge_pct is not None
                                and delayed_edge_pct is not None
                            ):
                                edge_decay_pct = delayed_edge_pct - original_edge_pct
                            snapshot_reason = "matched"
                        else:
                            snapshot_lag_ms = lag_ms
                            snapshot_reason = "snapshot_too_late"

                result_rows.append(
                    {
                        "decision_id": row.get("decision_id", ""),
                        "decision_time": row.get("decision_time", ""),
                        "target_time_utc": target_time.isoformat(),
                        "delay_seconds": delay_seconds,
                        "matched_snapshot": matched,
                        "snapshot_reason": snapshot_reason,
                        "snapshot_time_utc": snapshot_row.get("timestamp_utc", "")
                        if snapshot_row
                        else "",
                        "snapshot_source": snapshot_row.get("source", "")
                        if snapshot_row
                        else "",
                        "snapshot_lag_ms": snapshot_lag_ms,
                        "event_id": event_id,
                        "ticker": row.get("ticker", ""),
                        "timeframe": row.get("timeframe", ""),
                        "slot": row.get("slot", ""),
                        "range": row.get("range", ""),
                        "side_taken": side_taken,
                        "book_side": book_side,
                        "stake_usd": _parse_float(row.get("stake_usd")),
                        "shares_simulated": _parse_float(row.get("shares_simulated")),
                        "status": row.get("status", ""),
                        "pnl_simulated": _parse_float(row.get("pnl_simulated")),
                        "pnl_sim_adjusted": _parse_float(row.get("pnl_sim_adjusted")),
                        "prob_up": prob_up,
                        "quant_prob_side": quant_prob_side,
                        "decision_best_bid": original_bid,
                        "decision_best_ask": original_ask,
                        "delayed_best_bid": delayed_best_bid,
                        "delayed_best_ask": delayed_best_ask,
                        "delayed_spread": delayed_spread,
                        "original_edge_pct": original_edge_pct,
                        "delayed_edge_pct": delayed_edge_pct,
                        "edge_decay_pct": edge_decay_pct,
                        "edge_positive_after_delay": (
                            delayed_edge_pct is not None and delayed_edge_pct > 0
                        ),
                        "ask_depth_notional_topn": ask_depth_topn,
                        "depth_to_buy_5usd": _parse_float(
                            snapshot_row.get("depth_to_buy_5usd")
                        )
                        if snapshot_row
                        else None,
                        "topn_depth_sufficient": topn_depth_sufficient,
                    }
                )
    except FileNotFoundError:
        return []

    result_rows.sort(key=lambda r: r.get("decision_time", ""))
    return result_rows


@router.get("/stats/opportunities/raw")
async def get_opportunity_outcomes_raw(limit: int = 200, ticker: str | None = None):
    """Return raw recent opportunity outcomes rows."""
    t = ticker.upper() if ticker else None
    rows = await asyncio.to_thread(
        _read_csv_rows, event_manager._opportunity_tracker.outcomes_path, t, limit
    )
    return {"count": len(rows), "ticker_filter": t, "rows": rows}


@router.get("/stats/opportunities/signals/raw")
async def get_opportunity_signals_raw(limit: int = 200, ticker: str | None = None):
    """Return raw recent registered opportunity signals rows."""
    t = ticker.upper() if ticker else None
    rows = await asyncio.to_thread(
        _read_csv_rows, event_manager._opportunity_tracker.signals_path, t, limit
    )
    return {"count": len(rows), "ticker_filter": t, "rows": rows}


@router.get("/stats/opportunities/blocked/raw")
async def get_opportunity_blocked_raw(limit: int = 200, ticker: str | None = None):
    """Return raw recent blocked opportunity rows (not registered as signals)."""
    t = ticker.upper() if ticker else None
    rows = await asyncio.to_thread(
        _read_csv_rows, event_manager._opportunity_tracker.blocked_path, t, limit
    )
    return {"count": len(rows), "ticker_filter": t, "rows": rows}


@router.get("/stats/paper/raw")
async def get_paper_trades_raw(limit: int = 500, ticker: str | None = None):
    """Return raw paper-mode decision rows."""
    t = ticker.upper() if ticker else None
    rows = await asyncio.to_thread(
        _read_csv_rows, _output_dir() / "paper_trades.csv", t, limit
    )
    return {"count": len(rows), "ticker_filter": t, "rows": rows}


@router.get("/stats/chop/raw")
async def get_chop_history_raw(limit: int = 500, ticker: str | None = None):
    """Return raw chop-history rows."""
    t = ticker.upper() if ticker else None
    rows = await asyncio.to_thread(
        _read_csv_rows, _output_dir() / "chop_history.csv", t, limit
    )
    return {"count": len(rows), "ticker_filter": t, "rows": rows}


@router.get("/stats/decision-trace/raw")
async def get_decision_trace_raw(limit: int = 500, ticker: str | None = None):
    """Return raw append-only decision trace rows."""
    t = ticker.upper() if ticker else None
    rows = await asyncio.to_thread(
        _read_jsonl_rows, _output_dir() / "decision_trace.jsonl", t, limit
    )
    return {"count": len(rows), "ticker_filter": t, "rows": rows}


@router.get("/stats/delay-model/raw")
async def get_delay_model_raw(
    limit: int = 500,
    ticker: str | None = None,
    delay_seconds: float = 2.0,
    max_lag_seconds: float = 5.0,
):
    """Return raw paper-trade rows matched to the first order-book snapshot at decision_time+delay."""
    t = ticker.upper() if ticker else None
    rows = await asyncio.to_thread(
        _load_delay_model_rows,
        ticker=t,
        delay_seconds=max(0.0, float(delay_seconds)),
        max_lag_seconds=max(0.0, float(max_lag_seconds)),
    )
    rows = rows[-max(1, int(limit)) :]
    return {
        "count": len(rows),
        "ticker_filter": t,
        "delay_seconds": max(0.0, float(delay_seconds)),
        "max_lag_seconds": max(0.0, float(max_lag_seconds)),
        "rows": rows,
    }


@router.get("/stats/bot-orders/raw")
async def get_bot_orders_raw(
    limit: int = 500,
    ticker: str | None = None,
    days: int = 7,
):
    """Return raw bot order rows. In paper mode, serves paper_trades.csv instead."""
    ticker_filter = ticker.upper() if ticker else None
    is_paper = bool(event_manager.settings.get("bot_paper_mode", False))
    if is_paper:
        t = ticker_filter
        raw = await asyncio.to_thread(
            _read_csv_rows, _output_dir() / "paper_trades.csv", t, limit
        )
        rows = [_normalize_paper_trade_row(r) for r in raw]
    else:
        rows = await asyncio.to_thread(
            lambda: _load_bot_orders_rows(ticker=ticker, days=days)
        )
        rows = rows[-max(1, int(limit)) :]
    return {
        "count": len(rows),
        "ticker_filter": ticker_filter,
        "days": max(1, int(days)),
        "paper_mode": is_paper,
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
            "slot",
            "range",
            "side",
            "event_end_utc_at_send",
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
            "close_price_at_resolution",
            "event_outcome_real",
            "won",
            "pnl_simulated",
            "resolution_status",
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


@router.get("/stats/volatility-state")
async def get_volatility_state():
    """Current volatility monitor state for the analytics dashboard.

    Uses peek_alert() so the alert is NOT consumed here — the Telegram
    watchdog consumes it via the control API (/api/control/volatility-state).
    """
    return {
        "bot_mode": event_manager.settings.get("bot_mode", "NRM"),
        "execution_enabled": bool(
            event_manager.settings.get("execution_enabled", False)
        ),
        **volatility_monitor.get_state(),
        "pending_alert": volatility_monitor.peek_alert(),
    }
