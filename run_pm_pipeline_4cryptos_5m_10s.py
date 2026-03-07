#!/usr/bin/env python3
"""
Run 5m-focused subminute pipeline for BTC/ETH/SOL/XRP:
1) Export Binance 1s klines (lookback in days)
2) Resample to subminute Excel (default 10s)
3) Aggregate 5m slot ranges from subminute sheet
4) Merge filtered outputs with ticker column

Outputs are written to backtest_output/ with ticker-prefixed filenames.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

DEFAULT_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]

# Per-ticker range step (absolute price units). Reflects typical 5-min price moves.
# Override with --range-step to set a global fallback for unlisted tickers.
TICKER_RANGE_STEPS: dict[str, float] = {
    "BTC": 10.0,   # BTC ~$85k, 5min moves $50–$500
    "ETH": 2.0,    # ETH ~$2k,  5min moves $5–$50
    "SOL": 0.5,    # SOL ~$150, 5min moves $0.3–$2
    "XRP": 0.02,   # XRP ~$2.5, 5min moves $0.01–$0.10
}


def run_cmd(cmd: list[str]) -> None:
    print(f"$ {' '.join(cmd)}")
    subprocess.run(cmd, check=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run 1s->10s->5m-slot pipeline for multiple symbols."
    )
    parser.add_argument(
        "--symbols",
        default=",".join(DEFAULT_SYMBOLS),
        help="Comma-separated symbols, e.g. BTCUSDT,ETHUSDT,SOLUSDT,XRPUSDT",
    )
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=7,
        help="Lookback window in days for Binance export.",
    )
    parser.add_argument(
        "--slot-seconds",
        type=int,
        default=10,
        help="Slot size in seconds used for resample + aggregation.",
    )
    parser.add_argument(
        "--range-step",
        type=float,
        default=None,
        help="Global range step fallback for tickers not in TICKER_RANGE_STEPS. "
             "Defaults to per-ticker values defined in TICKER_RANGE_STEPS.",
    )
    parser.add_argument(
        "--min-count",
        type=int,
        default=20,
        help="min-count for filtered aggregate output",
    )
    parser.add_argument(
        "--output-dir",
        default="backtest_output",
        help="Output directory",
    )
    parser.add_argument(
        "--skip-download",
        action="store_true",
        help="Skip Binance klines download (reuse existing CSV files).",
    )
    return parser.parse_args()


def interval_to_sheet(interval: str) -> str:
    value = interval.lower().strip()
    if value.endswith("s"):
        return f"{int(value[:-1])}sec"
    if value.endswith("m"):
        return f"{int(value[:-1])}min"
    if value.endswith("h"):
        return f"{int(value[:-1])}hour"
    return value


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    if not symbols:
        raise ValueError("No symbols provided.")

    if args.slot_seconds <= 0 or 300 % args.slot_seconds != 0:
        raise ValueError("--slot-seconds must be > 0 and divide 300.")

    end_day = datetime.now(tz=timezone.utc).date() + timedelta(days=1)
    start_day = end_day - timedelta(days=max(1, int(args.lookback_days)))
    start_str = start_day.isoformat()
    end_str = end_day.isoformat()

    interval = f"{int(args.slot_seconds)}s"
    sheet_name = interval_to_sheet(interval)
    merged_frames: list[pd.DataFrame] = []

    for symbol in symbols:
        ticker = symbol.replace("USDT", "").lower()
        csv_1s = output_dir / f"{ticker}_1s_{args.lookback_days}d.csv"
        xlsx_subminute = output_dir / f"{ticker}_subminute.csv"
        pm_ranges = output_dir / f"{ticker}_pm_5m_slot_ranges.csv"
        pm_ranges_filtered = (
            output_dir / f"{ticker}_pm_5m_slot_ranges_mincount_{args.min_count}.csv"
        )

        range_step = TICKER_RANGE_STEPS.get(ticker.upper(), args.range_step or 10.0)
        print(f"\n=== {symbol} ({ticker}) [range-step={range_step}] ===")

        if args.skip_download:
            if not csv_1s.exists():
                raise FileNotFoundError(
                    f"--skip-download set but CSV not found: {csv_1s}"
                )
            print(f"[skip-download] Reusing {csv_1s}")
        else:
            run_cmd(
                [
                    sys.executable,
                    "export_binance_klines.py",
                    "--symbol",
                    symbol,
                    "--interval",
                    "1s",
                    "--start",
                    start_str,
                    "--end",
                    end_str,
                    "--output",
                    str(csv_1s),
                ]
            )

        run_cmd(
            [
                sys.executable,
                "resample_klines_to_excel_subminute.py",
                "--input",
                str(csv_1s),
                "--output",
                str(xlsx_subminute),
                "--intervals",
                interval,
            ]
        )

        run_cmd(
            [
                sys.executable,
                "aggregate_pm_5m_slot_ranges.py",
                "--input",
                str(xlsx_subminute),
                "--sheet",
                sheet_name,
                "--output",
                str(pm_ranges),
                "--range-step",
                str(range_step),
                "--min-count",
                str(args.min_count),
                "--output-filtered",
                str(pm_ranges_filtered),
                "--slot-seconds",
                str(args.slot_seconds),
                "--prob-source",
                "event_outcome",
                "--bayes-smoothing",
                "--prior-alpha",
                "1",
                "--prior-beta",
                "1",
            ]
        )

        df = pd.read_csv(pm_ranges_filtered)
        df["ticker"] = ticker.upper()
        merged_frames.append(df)

    merged = (
        pd.concat(merged_frames, ignore_index=True) if merged_frames else pd.DataFrame()
    )
    merged_out = output_dir / "merged_pm_5m_slot_ranges_4cryptos.csv"
    merged.to_csv(merged_out, index=False)

    print("\n=== DONE ===")
    print(f"Symbols: {', '.join(symbols)}")
    print(f"Range: {start_str} -> {end_str} (UTC day bounds)")
    print(f"Slot seconds: {args.slot_seconds}")
    print(f"Merged rows: {len(merged)}")
    print(f"Merged output: {merged_out}")


if __name__ == "__main__":
    main()
