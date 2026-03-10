#!/usr/bin/env python3
"""
Export all resolved bot orders across daily CSV files into a single file.
Output: backtest_output/trades_resolved.csv

Usage:
    python3 scripts/export_trades.py [--output PATH]
"""
import argparse
import glob
import os
import pandas as pd

BACKTEST_DIR = os.path.join(os.path.dirname(__file__), "..", "backtest_output")
DEFAULT_OUTPUT = os.path.join(BACKTEST_DIR, "trades_resolved.csv")


def main():
    parser = argparse.ArgumentParser(description="Export resolved bot orders")
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help="Output CSV path")
    args = parser.parse_args()

    pattern = os.path.join(BACKTEST_DIR, "bot_orders_*.csv")
    files = sorted(glob.glob(pattern))
    if not files:
        print("No bot_orders_*.csv files found in", BACKTEST_DIR)
        return

    dfs = []
    for f in files:
        try:
            df = pd.read_csv(f, low_memory=False)
            df["_source_file"] = os.path.basename(f)
            dfs.append(df)
        except Exception as e:
            print(f"  Warning: could not read {f}: {e}")

    if not dfs:
        print("No data loaded.")
        return

    combined = pd.concat(dfs, ignore_index=True)
    resolved = combined[combined["resolution_status"] == "resolved"].copy()
    resolved = resolved.sort_values("placed_at_utc").reset_index(drop=True)

    resolved.to_csv(args.output, index=False)
    print(f"Exported {len(resolved)} resolved trades → {args.output}")
    print(f"  Date range: {resolved['placed_at_utc'].min()[:10]} to {resolved['placed_at_utc'].max()[:10]}")
    won = resolved["won"].sum() if "won" in resolved.columns else "n/a"
    total_pnl = resolved["pnl_simulated"].sum() if "pnl_simulated" in resolved.columns else "n/a"
    print(f"  Won: {won}/{len(resolved)}  |  PnL total: ${total_pnl:.2f}" if isinstance(total_pnl, float) else f"  Won: {won}/{len(resolved)}")


if __name__ == "__main__":
    main()
