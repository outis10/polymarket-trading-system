#!/usr/bin/env python3
"""
Run full PM data pipeline for BTC/ETH/SOL/XRP:
1) Export Binance 1m klines
2) Build multiframe Excel
3) Aggregate PM 15m ranges
4) Merge all outputs with ticker column

Outputs are written to backtest_output/ with ticker-prefixed filenames.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import pandas as pd

DEFAULT_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]


def run_cmd(cmd: list[str]) -> None:
    print(f"$ {' '.join(cmd)}")
    subprocess.run(cmd, check=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run extract->frames->aggregate pipeline for multiple symbols."
    )
    parser.add_argument(
        "--symbols",
        default=",".join(DEFAULT_SYMBOLS),
        help="Comma-separated symbols, e.g. BTCUSDT,ETHUSDT,SOLUSDT,XRPUSDT",
    )
    parser.add_argument(
        "--months",
        type=int,
        default=3,
        help="Lookback months for Binance export.",
    )
    parser.add_argument(
        "--range-step",
        type=float,
        default=10.0,
        help="Range step for aggregate_pm_15m_ranges.py",
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
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    if not symbols:
        raise ValueError("No symbols provided.")

    merged_frames: list[pd.DataFrame] = []

    for symbol in symbols:
        ticker = symbol.replace("USDT", "").lower()

        csv_1m = output_dir / f"{ticker}_1m_{args.months}m.csv"
        xlsx_frames = output_dir / f"{ticker}_multiframe.xlsx"
        pm_ranges = output_dir / f"{ticker}_pm_ranges.csv"
        pm_ranges_filtered = (
            output_dir / f"{ticker}_pm_ranges_mincount_{args.min_count}.csv"
        )

        print(f"\n=== {symbol} ({ticker}) ===")

        run_cmd(
            [
                sys.executable,
                "export_binance_klines.py",
                "--symbol",
                symbol,
                "--interval",
                "1m",
                "--months",
                str(args.months),
                "--output",
                str(csv_1m),
            ]
        )

        run_cmd(
            [
                sys.executable,
                "resample_klines_to_excel.py",
                "--input",
                str(csv_1m),
                "--output",
                str(xlsx_frames),
                "--intervals",
                "1m,2m,3m,5m,15m",
            ]
        )

        run_cmd(
            [
                sys.executable,
                "aggregate_pm_15m_ranges.py",
                "--input",
                str(xlsx_frames),
                "--sheet",
                "1min",
                "--output",
                str(pm_ranges),
                "--range-step",
                str(args.range_step),
                "--min-count",
                str(args.min_count),
                "--output-filtered",
                str(pm_ranges_filtered),
                "--prob-source",
                "event_outcome",
                "--bayes-smoothing",
                "--prior-alpha",
                "1",
                "--prior-beta",
                "1",
                "--exclude-minute-15",
            ]
        )

        df = pd.read_csv(pm_ranges_filtered)
        df["ticker"] = ticker.upper()
        merged_frames.append(df)

    merged = (
        pd.concat(merged_frames, ignore_index=True) if merged_frames else pd.DataFrame()
    )
    merged_out = output_dir / "merged_pm_ranges_4cryptos.csv"
    merged.to_csv(merged_out, index=False)

    print("\n=== DONE ===")
    print(f"Symbols: {', '.join(symbols)}")
    print(f"Merged rows: {len(merged)}")
    print(f"Merged output: {merged_out}")


if __name__ == "__main__":
    main()
