#!/usr/bin/env python3
"""
Export Binance klines to CSV (single or multi-symbol).

Examples:
  # Backward-compatible single symbol export
  python export_binance_klines.py --symbol BTCUSDT --interval 1m --months 3 --output btcusdt_1m_3m.csv

  # Multi-symbol export for the 4 tracked cryptos
  python export_binance_klines.py --four-cryptos --interval 1m --months 3 --output-dir backtest_output

  # Custom list
  python export_binance_klines.py --symbols BTCUSDT,ETHUSDT --interval 1s --start 2026-01-01 --end 2026-01-02 --output-dir backtest_output
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any

import requests

BINANCE_KLINES_URL = "https://api.binance.com/api/v3/klines"
MAX_LIMIT = 1000
DEFAULT_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export Binance klines to CSV")
    parser.add_argument("--symbol", default=None, help="Trading pair, e.g. BTCUSDT")
    parser.add_argument(
        "--symbols",
        default=None,
        help="Comma-separated symbols, e.g. BTCUSDT,ETHUSDT,SOLUSDT,XRPUSDT",
    )
    parser.add_argument(
        "--four-cryptos",
        action="store_true",
        help="Shortcut for BTCUSDT,ETHUSDT,SOLUSDT,XRPUSDT",
    )
    parser.add_argument(
        "--interval", default="1m", help="Binance interval, e.g. 1m, 5m, 1h"
    )
    parser.add_argument(
        "--months", type=int, default=0, help="Lookback months from now (UTC)"
    )
    parser.add_argument("--start", default=None, help="Start date (UTC) YYYY-MM-DD")
    parser.add_argument("--end", default=None, help="End date (UTC) YYYY-MM-DD")
    parser.add_argument(
        "--output",
        default=None,
        help="CSV output path (single-symbol mode).",
    )
    parser.add_argument(
        "--output-dir",
        default="backtest_output",
        help="Output directory for auto-generated filenames.",
    )
    parser.add_argument(
        "--output-template",
        default="{symbol_lower}_{interval}_{range_tag}.csv",
        help="Filename template for auto output. Placeholders: {symbol},{symbol_lower},{interval},{range_tag}",
    )
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


def interval_to_ms(interval: str) -> int:
    value = interval.strip().lower()
    if len(value) < 2:
        raise ValueError(f"Invalid interval '{interval}'")
    unit = value[-1]
    amount = int(value[:-1])
    if amount <= 0:
        raise ValueError(f"Invalid interval '{interval}'")
    unit_ms = {
        "s": 1_000,
        "m": 60_000,
        "h": 3_600_000,
        "d": 86_400_000,
        "w": 604_800_000,
    }
    if unit not in unit_ms:
        raise ValueError(f"Unsupported interval unit '{unit}' in '{interval}'")
    return amount * unit_ms[unit]


def resolve_symbols(args: argparse.Namespace) -> list[str]:
    ordered = OrderedDict()
    if args.four_cryptos:
        for s in DEFAULT_SYMBOLS:
            ordered[s] = True
    if args.symbols:
        for s in args.symbols.split(","):
            sym = s.strip().upper()
            if sym:
                ordered[sym] = True
    if args.symbol:
        ordered[args.symbol.strip().upper()] = True
    symbols = list(ordered.keys())
    if not symbols:
        raise ValueError("Provide --symbol, --symbols, or --four-cryptos")
    return symbols


def range_tag(args: argparse.Namespace) -> str:
    if args.months > 0 and not args.start:
        return f"{args.months}m"
    start_tag = args.start.replace("-", "") if args.start else "start"
    end_tag = args.end.replace("-", "") if args.end else "now"
    return f"{start_tag}_{end_tag}"


def resolve_output_path(
    args: argparse.Namespace, symbol: str, symbols_count: int
) -> Path:
    if args.output:
        if symbols_count > 1:
            raise ValueError("--output cannot be used with multiple symbols.")
        return Path(args.output)
    filename = args.output_template.format(
        symbol=symbol.upper(),
        symbol_lower=symbol.lower(),
        interval=args.interval.lower(),
        range_tag=range_tag(args),
    )
    return Path(args.output_dir) / filename


def fetch_klines_batches(
    symbol: str, interval: str, start_ms: int, end_ms: int, sleep_ms: int
):
    cursor = start_ms
    step_ms = interval_to_ms(interval)
    if step_ms <= 0:
        raise ValueError(f"Invalid interval step for '{interval}'")

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

        yield batch
        last_open_time = int(batch[-1][0])
        cursor = last_open_time + step_ms

        if len(batch) < MAX_LIMIT:
            break

        time.sleep(max(0, sleep_ms) / 1000.0)


def write_header(writer: csv.writer) -> None:
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


def write_csv(path: Path, rows: list[list[Any]]) -> tuple[int, str | None, str | None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        write_header(writer)
        count = 0
        first_utc: str | None = None
        last_utc: str | None = None
        last_open_time_written = -1
        for r in rows:
            open_time = int(r[0])
            if open_time <= last_open_time_written:
                continue
            last_open_time_written = open_time
            open_utc = dt.datetime.fromtimestamp(
                open_time / 1000, tz=dt.timezone.utc
            ).isoformat()
            if first_utc is None:
                first_utc = open_utc
            last_utc = open_utc
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
            count += 1
    return count, first_utc, last_utc


def export_symbol(
    symbol: str,
    interval: str,
    start_ms: int,
    end_ms: int,
    sleep_ms: int,
    output_path: Path,
) -> tuple[int, str | None, str | None]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    first_utc: str | None = None
    last_utc: str | None = None
    last_open_time_written = -1

    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        write_header(writer)
        for batch in fetch_klines_batches(symbol, interval, start_ms, end_ms, sleep_ms):
            for r in batch:
                open_time = int(r[0])
                if open_time >= end_ms:
                    continue
                if open_time <= last_open_time_written:
                    continue
                last_open_time_written = open_time
                open_utc = dt.datetime.fromtimestamp(
                    open_time / 1000, tz=dt.timezone.utc
                ).isoformat()
                if first_utc is None:
                    first_utc = open_utc
                last_utc = open_utc
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
                written += 1
    return written, first_utc, last_utc


def main() -> None:
    args = parse_args()
    symbols = resolve_symbols(args)
    start_ms, end_ms = resolve_timerange(args)
    total_rows = 0
    for symbol in symbols:
        output_path = resolve_output_path(args, symbol, len(symbols))
        rows_count, first, last = export_symbol(
            symbol=symbol,
            interval=args.interval,
            start_ms=start_ms,
            end_ms=end_ms,
            sleep_ms=args.sleep_ms,
            output_path=output_path,
        )
        total_rows += rows_count
        if rows_count > 0:
            print(f"[{symbol}] Exported {rows_count} rows -> {output_path}")
            print(f"[{symbol}] Range UTC: {first} -> {last}")
        else:
            print(f"[{symbol}] No data exported -> {output_path}")
    print(f"Done. Symbols: {len(symbols)} | Total rows: {total_rows}")


if __name__ == "__main__":
    main()
