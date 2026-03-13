#!/usr/bin/env python3
"""
Polymarket quant pipeline — multi-event, multi-ticker.

Runs the full 1s → resample → slot-aggregate pipeline for any combination
of event durations and symbols, then merges all outputs into a single CSV.

Usage:
  python3 run_pm_pipeline.py --lookback-days 7
  python3 run_pm_pipeline.py --event-minutes 5,15,60,240 --lookback-days 30
  python3 run_pm_pipeline.py --event-minutes 5 --symbols BTCUSDT,ETHUSDT

Output:
  backtest_output/merged_pm_slot_ranges_4cryptos.csv
  Columns: event_type, ticker, day_type, time_frame, slot,
           inf_range, sup_range, prob_up, prob_down,
           count_of_klines_inside_range
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

DEFAULT_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]

# Default slot granularity per event duration — keeps ~30 slots per event.
# Override per-run with --slot-seconds (applies to all event types uniformly).
DEFAULT_SLOT_SECONDS: dict[int, int] = {
    5: 10,
    15: 30,
    60: 120,
    240: 480,
}

# Price range step (absolute USD) per (event_minutes, ticker).
# Calibrated to ~3x the median price move for that duration.
EVENT_RANGE_STEPS: dict[tuple[int, str], float] = {
    (5,   "BTC"): 10.0,   (5,   "ETH"): 0.20,  (5,   "SOL"): 0.20,  (5,   "XRP"): 0.02,
    (15,  "BTC"): 30.0,   (15,  "ETH"): 0.50,  (15,  "SOL"): 0.50,  (15,  "XRP"): 0.05,
    (60,  "BTC"): 100.0,  (60,  "ETH"): 2.00,  (60,  "SOL"): 2.00,  (60,  "XRP"): 0.20,
    (240, "BTC"): 400.0,  (240, "ETH"): 8.00,  (240, "SOL"): 8.00,  (240, "XRP"): 0.80,
}


def run_cmd(cmd: list[str]) -> None:
    print(f"$ {' '.join(cmd)}")
    subprocess.run(cmd, check=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run 1s→slot→aggregate pipeline for multiple events and symbols."
    )
    parser.add_argument(
        "--symbols",
        default=",".join(DEFAULT_SYMBOLS),
        help="Comma-separated symbols. Default: BTCUSDT,ETHUSDT,SOLUSDT,XRPUSDT",
    )
    parser.add_argument(
        "--event-minutes",
        default="5",
        help="Comma-separated event durations in minutes. Default: 5. "
             "E.g. '5,15,60,240' for all supported types.",
    )
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=7,
        help="Lookback window in days for Binance export.",
    )
    parser.add_argument(
        "--min-count",
        type=int,
        default=20,
        help="Minimum samples per slot/range bucket.",
    )
    parser.add_argument(
        "--output-dir",
        default="backtest_output",
        help="Output directory.",
    )
    parser.add_argument(
        "--skip-download",
        action="store_true",
        help="Skip Binance download — reuse existing 1s CSV files.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    event_minutes_list = [
        int(x.strip()) for x in args.event_minutes.split(",") if x.strip()
    ]

    for em in event_minutes_list:
        if em not in DEFAULT_SLOT_SECONDS:
            supported = list(DEFAULT_SLOT_SECONDS.keys())
            raise ValueError(
                f"--event-minutes {em} not supported. "
                f"Add it to DEFAULT_SLOT_SECONDS and EVENT_RANGE_STEPS. "
                f"Currently supported: {supported}"
            )

    end_day = datetime.now(tz=timezone.utc).date() + timedelta(days=1)
    start_day = end_day - timedelta(days=max(1, args.lookback_days))
    start_str = start_day.isoformat()
    end_str = end_day.isoformat()

    print("=" * 60)
    print(f"  Polymarket Quant Pipeline — {datetime.now(timezone.utc):%Y-%m-%d %H:%M UTC}")
    print(f"  Symbols : {', '.join(symbols)}")
    print(f"  Events  : {', '.join(f'{m}m' for m in event_minutes_list)}")
    print(f"  Lookback: {args.lookback_days} days  |  Min-count: {args.min_count}")
    print("=" * 60)

    merged_frames: list[pd.DataFrame] = []

    for symbol in symbols:
        ticker = symbol.replace("USDT", "").upper()
        csv_1s = output_dir / f"{ticker.lower()}_1s_{args.lookback_days}d.csv"

        # Step 1: Download 1s klines — once per symbol
        if not args.skip_download:
            run_cmd([
                sys.executable, "export_binance_klines.py",
                "--symbol", symbol,
                "--interval", "1s",
                "--start", start_str,
                "--end", end_str,
                "--output", str(csv_1s),
            ])
        elif not csv_1s.exists():
            raise FileNotFoundError(
                f"--skip-download set but 1s CSV not found: {csv_1s}"
            )
        else:
            print(f"[skip-download] Reusing {csv_1s}")

        # Step 2+3: Resample + aggregate for each event duration
        for event_min in event_minutes_list:
            slot_sec = DEFAULT_SLOT_SECONDS[event_min]
            range_step = EVENT_RANGE_STEPS.get((event_min, ticker), 10.0)
            event_label = f"{event_min}m"

            print(f"\n--- {symbol} | {event_label} | slot={slot_sec}s | step={range_step} ---")

            csv_resampled = output_dir / f"{ticker.lower()}_subminute_{event_label}.csv"
            csv_ranges = output_dir / f"{ticker.lower()}_pm_{event_label}_slot_ranges.csv"
            csv_filtered = (
                output_dir
                / f"{ticker.lower()}_pm_{event_label}_slot_ranges_mincount_{args.min_count}.csv"
            )

            # Resample 1s → slot_sec granularity
            run_cmd([
                sys.executable, "resample_klines_to_excel_subminute.py",
                "--input", str(csv_1s),
                "--output", str(csv_resampled),
                "--intervals", f"{slot_sec}s",
            ])

            # Aggregate slots + price ranges
            run_cmd([
                sys.executable, "aggregate_pm_slot_ranges.py",
                "--input", str(csv_resampled),
                "--sheet", f"{slot_sec}sec",
                "--output", str(csv_ranges),
                "--range-step", str(range_step),
                "--min-count", str(args.min_count),
                "--output-filtered", str(csv_filtered),
                "--slot-seconds", str(slot_sec),
                "--event-minutes", str(event_min),
                "--prob-source", "event_outcome",
                "--bayes-smoothing",
                "--prior-alpha", "1",
                "--prior-beta", "1",
            ])

            df = pd.read_csv(csv_filtered)
            df["ticker"] = ticker
            df["event_type"] = event_label
            merged_frames.append(df)

    merged = (
        pd.concat(merged_frames, ignore_index=True) if merged_frames else pd.DataFrame()
    )

    # Reorder columns: event_type + ticker first for readability
    if not merged.empty and "event_type" in merged.columns:
        cols = ["event_type", "ticker"] + [
            c for c in merged.columns if c not in ("event_type", "ticker")
        ]
        merged = merged[cols]

    merged_out = output_dir / "merged_pm_slot_ranges_4cryptos.csv"
    merged.to_csv(merged_out, index=False)

    print("\n" + "=" * 60)
    print("  DONE")
    print(f"  Symbols   : {', '.join(symbols)}")
    print(f"  Events    : {', '.join(f'{m}m' for m in event_minutes_list)}")
    print(f"  Range     : {start_str} → {end_str} (UTC)")
    print(f"  Total rows: {len(merged)}")
    print(f"  Output    : {merged_out}")
    print("=" * 60)


if __name__ == "__main__":
    main()
