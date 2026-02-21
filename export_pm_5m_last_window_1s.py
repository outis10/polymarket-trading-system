#!/usr/bin/env python3
"""
Export 1-second Binance klines for the final seconds of Polymarket 5m events.

Default behavior:
- discovers PM events via Gamma (using existing event_discovery module),
- filters to 5m events,
- downloads only the last N seconds before each event end,
- writes a single merged CSV compatible with existing OHLCV base fields.

Examples:
  python3 export_pm_5m_last_window_1s.py \
    --lookahead-days 14 \
    --window-seconds 180 \
    --output backtest_output/pm_5m_last180s_1s.csv

  python3 export_pm_5m_last_window_1s.py \
    --tickers BTC,ETH,SOL,XRP \
    --window-seconds 120 \
    --output backtest_output/pm_5m_last120s_1s.csv
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import time
from pathlib import Path
from typing import Any

import requests

from backend.services.event_discovery import discover_live_events

BINANCE_KLINES_URL = "https://api.binance.com/api/v3/klines"
MAX_LIMIT = 1000


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export 1s klines for final window of PM 5m events."
    )
    parser.add_argument(
        "--tickers",
        default="BTC,ETH,SOL,XRP",
        help="Comma-separated crypto tickers (not USDT pairs), e.g. BTC,ETH,SOL,XRP",
    )
    parser.add_argument(
        "--lookahead-days",
        type=int,
        default=14,
        help="How many days ahead to discover events from Gamma.",
    )
    parser.add_argument(
        "--window-seconds",
        type=int,
        default=180,
        help="Seconds before event end to export in 1s candles.",
    )
    parser.add_argument(
        "--max-events",
        type=int,
        default=200,
        help="Max number of events to discover.",
    )
    parser.add_argument(
        "--sleep-ms",
        type=int,
        default=120,
        help="Sleep between Binance requests.",
    )
    parser.add_argument(
        "--output",
        default="backtest_output/pm_5m_last180s_1s.csv",
        help="Merged CSV output path.",
    )
    parser.add_argument(
        "--include-live-only",
        action="store_true",
        help="If set, only currently active events are included.",
    )
    return parser.parse_args()


def parse_iso_utc(value: str) -> dt.datetime | None:
    if not value:
        return None
    try:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(
            dt.timezone.utc
        )
    except Exception:
        return None


def fetch_1s_klines_window(
    symbol: str, start_ms: int, end_ms: int, sleep_ms: int
) -> list[list[Any]]:
    rows: list[list[Any]] = []
    cursor = start_ms

    while cursor < end_ms:
        params = {
            "symbol": symbol.upper(),
            "interval": "1s",
            "startTime": cursor,
            "endTime": end_ms,
            "limit": MAX_LIMIT,
        }
        resp = requests.get(BINANCE_KLINES_URL, params=params, timeout=15)
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break

        rows.extend(batch)
        last_open_time = int(batch[-1][0])
        cursor = last_open_time + 1000  # advance by one second candle

        if len(batch) < MAX_LIMIT:
            break
        time.sleep(max(0, sleep_ms) / 1000.0)

    # Dedup by open_time while preserving latest row
    dedup: dict[int, list[Any]] = {}
    for row in rows:
        dedup[int(row[0])] = row
    return [dedup[k] for k in sorted(dedup.keys()) if start_ms <= k < end_ms]


def discover_5m_events(
    tickers: list[str], lookahead_days: int, max_events: int, include_live_only: bool
) -> list[dict[str, Any]]:
    cfg = {
        "enabled": True,
        "symbols": tickers,
        "lookahead_days": lookahead_days,
        "max_events": max_events,
        "require_15m": False,
        "allowed_timeframes": [5],
        "only_live_now": bool(include_live_only),
        "min_minutes": 3,
        "max_minutes": 7,
    }
    events = discover_live_events(cfg)
    return [e for e in events if int(e.get("timeframe_minutes", 0) or 0) == 5]


def write_output(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    headers = [
        "condition_id",
        "event_name",
        "ticker",
        "binance_symbol",
        "event_start_utc",
        "event_end_utc",
        "window_seconds",
        "open_time",
        "open_time_utc",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "close_time",
        "quote_asset_volume",
        "number_of_trades",
        "taker_buy_base_volume",
        "taker_buy_quote_volume",
        "seconds_to_end",
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    args = parse_args()
    tickers = [x.strip().upper() for x in args.tickers.split(",") if x.strip()]
    if not tickers:
        raise ValueError("No tickers provided.")
    if args.window_seconds <= 0:
        raise ValueError("--window-seconds must be > 0")

    events = discover_5m_events(
        tickers=tickers,
        lookahead_days=args.lookahead_days,
        max_events=args.max_events,
        include_live_only=args.include_live_only,
    )
    if not events:
        print("No 5m events discovered.")
        return

    out_rows: list[dict[str, Any]] = []
    exported_events = 0

    for event in events:
        symbol = str(event.get("binance_symbol", "")).upper().strip()
        if not symbol:
            continue
        end_dt = parse_iso_utc(str(event.get("event_end_time", "")))
        start_dt = parse_iso_utc(str(event.get("event_start_time", "")))
        if not end_dt:
            continue

        end_ms = int(end_dt.timestamp() * 1000)
        start_ms = end_ms - int(args.window_seconds * 1000)
        if start_dt:
            start_ms = max(start_ms, int(start_dt.timestamp() * 1000))
        if start_ms >= end_ms:
            continue

        klines = fetch_1s_klines_window(
            symbol=symbol,
            start_ms=start_ms,
            end_ms=end_ms,
            sleep_ms=args.sleep_ms,
        )
        if not klines:
            continue

        exported_events += 1
        ticker = symbol.replace("USDT", "")
        for k in klines:
            open_time = int(k[0])
            open_utc = dt.datetime.fromtimestamp(
                open_time / 1000, tz=dt.timezone.utc
            ).isoformat()
            seconds_to_end = max(0.0, (end_ms - open_time) / 1000.0)
            out_rows.append(
                {
                    "condition_id": str(event.get("condition_id", "")),
                    "event_name": str(event.get("name", "")),
                    "ticker": ticker,
                    "binance_symbol": symbol,
                    "event_start_utc": start_dt.isoformat() if start_dt else "",
                    "event_end_utc": end_dt.isoformat(),
                    "window_seconds": args.window_seconds,
                    "open_time": open_time,
                    "open_time_utc": open_utc,
                    "open": k[1],
                    "high": k[2],
                    "low": k[3],
                    "close": k[4],
                    "volume": k[5],
                    "close_time": k[6],
                    "quote_asset_volume": k[7],
                    "number_of_trades": k[8],
                    "taker_buy_base_volume": k[9],
                    "taker_buy_quote_volume": k[10],
                    "seconds_to_end": f"{seconds_to_end:.3f}",
                }
            )

    out_path = Path(args.output)
    write_output(out_path, out_rows)
    print(f"Exported {len(out_rows)} rows from {exported_events} events to {out_path}")


if __name__ == "__main__":
    main()
