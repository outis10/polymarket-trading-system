#!/usr/bin/env python3
"""
Aggregate 1m frame data into 15-minute position buckets and price-move ranges.

Output schema matches:
  minute, inf_range, sup_range, prob_up, prob_down, count_of_klines_inside_range
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Aggregate XLSX 1m data by minute-in-15m and price ranges."
    )
    parser.add_argument("--input", required=True, help="Input XLSX path.")
    parser.add_argument("--sheet", default="1min", help="Sheet name to use.")
    parser.add_argument(
        "--output",
        default="sum_range_up_down_probabilities.csv",
        help="Output CSV path.",
    )
    parser.add_argument(
        "--range-step",
        type=float,
        default=10.0,
        help="Price range step size (absolute price units).",
    )
    parser.add_argument(
        "--min-count",
        type=int,
        default=1,
        help="Minimum count_of_klines_inside_range to keep in filtered output.",
    )
    parser.add_argument(
        "--output-filtered",
        default="",
        help="Optional output CSV path for filtered rows (min-count applied).",
    )
    parser.add_argument(
        "--prob-source",
        choices=["event_outcome", "rolling_columns"],
        default="event_outcome",
        help=(
            "How to compute prob_up/prob_down: "
            "'event_outcome' uses final result of each 15m block (recommended), "
            "'rolling_columns' averages existing prob_up/prob_down columns."
        ),
    )
    parser.add_argument(
        "--bayes-smoothing",
        action="store_true",
        help="Apply Bayesian smoothing to prob_up/prob_down using Beta prior.",
    )
    parser.add_argument(
        "--prior-alpha",
        type=float,
        default=1.0,
        help="Alpha parameter for Beta prior (used with --bayes-smoothing).",
    )
    parser.add_argument(
        "--prior-beta",
        type=float,
        default=1.0,
        help="Beta parameter for Beta prior (used with --bayes-smoothing).",
    )
    parser.add_argument(
        "--exclude-minute-15",
        action="store_true",
        help="Exclude minute 15 from output (useful for actionable pre-close signals).",
    )
    return parser.parse_args()


def validate_columns(df: pd.DataFrame, prob_source: str) -> None:
    required = ["open_time_utc", "open", "close"]
    if prob_source == "rolling_columns":
        required.extend(["prob_up", "prob_down"])
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")


def ensure_datetime(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["open_time_utc"] = pd.to_datetime(
        out["open_time_utc"], errors="coerce", utc=True
    )
    out = out.dropna(subset=["open_time_utc"])
    return out


def compute_block_key(df: pd.DataFrame) -> pd.Series:
    if "ts_15m_block" in df.columns:
        block_key = pd.to_numeric(df["ts_15m_block"], errors="coerce")
        if block_key.notna().all():
            return block_key
    return df["open_time_utc"].dt.floor("15min")


def compute_minute_in_15m(df: pd.DataFrame, block_key: pd.Series) -> pd.Series:
    return df.groupby(block_key, sort=False).cumcount() + 1


def build_ranges(price_move: pd.Series, step: float) -> tuple[pd.Series, pd.Series]:
    inf = np.floor(price_move / step) * step
    sup = inf + step
    return pd.Series(inf, index=price_move.index), pd.Series(
        sup, index=price_move.index
    )


def main() -> None:
    args = parse_args()
    step = float(args.range_step)
    if step <= 0:
        raise ValueError("--range-step must be > 0")
    if args.min_count < 1:
        raise ValueError("--min-count must be >= 1")
    if args.prior_alpha <= 0 or args.prior_beta <= 0:
        raise ValueError("--prior-alpha and --prior-beta must be > 0")

    df = pd.read_excel(args.input, sheet_name=args.sheet)
    validate_columns(df, prob_source=args.prob_source)

    df = ensure_datetime(df).sort_values("open_time_utc").reset_index(drop=True)
    numeric_cols = ["open", "close"]
    if args.prob_source == "rolling_columns":
        numeric_cols.extend(["prob_up", "prob_down"])
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=numeric_cols).reset_index(drop=True)

    df["_block_key"] = compute_block_key(df)
    df["minute"] = compute_minute_in_15m(df, block_key=df["_block_key"])
    df = df[(df["minute"] >= 1) & (df["minute"] <= 15)].copy()

    # Event-style reference: keep the first minute open as anchor for all 15 minutes.
    df["ref_price"] = df.groupby("_block_key", sort=False)["open"].transform("first")
    df["price_move"] = df["close"] - df["ref_price"]
    df["inf_range"], df["sup_range"] = build_ranges(df["price_move"], step=step)

    if args.prob_source == "event_outcome":
        final_close = df.groupby("_block_key", sort=False)["close"].transform("last")
        # If final_close == ref_price, treat as neutral (0.5/0.5).
        df["prob_up_event"] = np.where(
            final_close > df["ref_price"],
            1.0,
            np.where(final_close < df["ref_price"], 0.0, 0.5),
        )
        df["prob_down_event"] = 1.0 - df["prob_up_event"]
        prob_up_col = "prob_up_event"
        prob_down_col = "prob_down_event"
    else:
        prob_up_col = "prob_up"
        prob_down_col = "prob_down"

    grouped = (
        df.groupby(["minute", "inf_range", "sup_range"], as_index=False)
        .agg(
            prob_up=(prob_up_col, "mean"),
            prob_down=(prob_down_col, "mean"),
            count_of_klines_inside_range=("price_move", "count"),
        )
        .sort_values(["minute", "inf_range"], ascending=[True, True])
        .reset_index(drop=True)
    )

    grouped["minute"] = grouped["minute"].astype(int)
    grouped["count_of_klines_inside_range"] = grouped[
        "count_of_klines_inside_range"
    ].astype(int)

    if args.exclude_minute_15:
        grouped = grouped[grouped["minute"] != 15].copy()

    if args.bayes_smoothing:
        n = grouped["count_of_klines_inside_range"].astype(float)
        wins = grouped["prob_up"] * n
        grouped["prob_up"] = (wins + args.prior_alpha) / (
            n + args.prior_alpha + args.prior_beta
        )
        grouped["prob_down"] = 1.0 - grouped["prob_up"]

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    grouped.to_csv(output, index=False)

    print(f"Rows exported: {len(grouped)}")
    print(f"Output: {output}")

    filtered = grouped[grouped["count_of_klines_inside_range"] >= args.min_count].copy()
    if args.output_filtered:
        filtered_output = Path(args.output_filtered)
    else:
        filtered_output = output.with_name(
            f"{output.stem}_mincount_{args.min_count}.csv"
        )
    filtered_output.parent.mkdir(parents=True, exist_ok=True)
    filtered.to_csv(filtered_output, index=False)
    print(f"Filtered rows exported (min_count>={args.min_count}): {len(filtered)}")
    print(f"Filtered output: {filtered_output}")


if __name__ == "__main__":
    main()
