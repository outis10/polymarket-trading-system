#!/usr/bin/env python3
"""
Export Binance klines to CSV.

Examples:
  python export_binance_klines.py --symbol BTCUSDT --interval 1m --months 3 --output btcusdt_1m_3m.csv
  python export_binance_klines.py --symbol ETHUSDT --interval 5m --start 2025-10-01 --end 2026-01-01 --output eth_5m_q4.csv
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import time
from pathlib import Path
from typing import Any

import requests

BINANCE_KLINES_URL = "https://api.binance.com/api/v3/klines"
MAX_LIMIT = 1000


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export Binance klines to CSV")
    parser.add_argument("--symbol", required=True, help="Trading pair, e.g. BTCUSDT")
    parser.add_argument(
        "--interval", default="1m", help="Binance interval, e.g. 1m, 5m, 1h"
    )
    parser.add_argument(
        "--months", type=int, default=0, help="Lookback months from now (UTC)"
    )
    parser.add_argument("--start", default=None, help="Start date (UTC) YYYY-MM-DD")
    parser.add_argument("--end", default=None, help="End date (UTC) YYYY-MM-DD")
    parser.add_argument("--output", required=True, help="CSV output path")
    parser.add_argument(
        "--sleep-ms", type=int, default=150, help="Sleep between requests"
    )
    return parser.parse_args()


def to_ms(date_str: str) -> int:
    d = dt.datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=dt.timezone.utc)
    return int(d.timestamp() * 1000)


def resolve_timerange(args: argparse.Namespace) -> tuple[int, int]:
    now = dt.datetime.now(dt.timezone.utc)
    end_ms = int(now.timestamp() * 1000)

    if args.end:
        end_ms = to_ms(args.end)

    if args.start:
        start_ms = to_ms(args.start)
    elif args.months > 0:
        start_dt = now - dt.timedelta(days=args.months * 30)
        start_ms = int(start_dt.timestamp() * 1000)
    else:
        raise ValueError("Provide --start or --months")

    if start_ms >= end_ms:
        raise ValueError("Start must be before end")
    return start_ms, end_ms


def fetch_klines(
    symbol: str, interval: str, start_ms: int, end_ms: int, sleep_ms: int
) -> list[list[Any]]:
    rows: list[list[Any]] = []
    cursor = start_ms

    while cursor < end_ms:
        params = {
            "symbol": symbol.upper(),
            "interval": interval,
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
        cursor = last_open_time + 1

        if len(batch) < MAX_LIMIT:
            break

        time.sleep(max(0, sleep_ms) / 1000.0)

    # De-duplicate by open time in case of overlap
    dedup: dict[int, list[Any]] = {}
    for r in rows:
        dedup[int(r[0])] = r
    return [dedup[k] for k in sorted(dedup.keys())]


def write_csv(path: Path, rows: list[list[Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
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
            ]
        )
        for r in rows:
            open_time = int(r[0])
            open_utc = dt.datetime.fromtimestamp(
                open_time / 1000, tz=dt.timezone.utc
            ).isoformat()
            writer.writerow(
                [
                    open_time,
                    open_utc,
                    r[1],
                    r[2],
                    r[3],
                    r[4],
                    r[5],
                    r[6],
                    r[7],
                    r[8],
                    r[9],
                    r[10],
                ]
            )


def main() -> None:
    args = parse_args()
    start_ms, end_ms = resolve_timerange(args)
    rows = fetch_klines(args.symbol, args.interval, start_ms, end_ms, args.sleep_ms)
    write_csv(Path(args.output), rows)

    if rows:
        first = dt.datetime.fromtimestamp(
            int(rows[0][0]) / 1000, tz=dt.timezone.utc
        ).isoformat()
        last = dt.datetime.fromtimestamp(
            int(rows[-1][0]) / 1000, tz=dt.timezone.utc
        ).isoformat()
        print(f"Exported {len(rows)} rows to {args.output}")
        print(f"Range UTC: {first} -> {last}")
    else:
        print(f"No data exported to {args.output}")


if __name__ == "__main__":
    main()
