#!/usr/bin/env python3
"""
Aggregate subminute frame data into 5-minute slot buckets and price-move ranges,
segmented by time window (day_type + time_frame) defined in config/time_windows.csv.

Output schema:
  day_type, time_frame, slot, inf_range, sup_range, prob_up, prob_down,
  count_of_klines_inside_range
"""

from __future__ import annotations

import argparse
import csv as csv_mod
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Time-window helpers
# ---------------------------------------------------------------------------

def load_time_windows(csv_path: str | Path) -> list[dict]:
    """Load and validate time_windows.csv.

    Returns a list of dicts with keys:
      day_type, time_frame, start_hour (float), end_hour (float), zone (str)

    Validations:
    - Required columns present.
    - All rows must share the same timezone.
    - Per day_type: ranges cover [0, 24) without gaps or overlaps.
    """
    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(f"time_windows.csv not found at {path}")

    required_cols = {"day_type", "time_frame", "start_hour", "end_hour", "zone"}
    rows: list[dict] = []
    with open(path, newline="") as f:
        reader = csv_mod.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError("time_windows.csv is empty or missing header")
        missing = required_cols - set(reader.fieldnames)
        if missing:
            raise ValueError(f"time_windows.csv missing columns: {missing}")
        for row in reader:
            rows.append(
                {
                    "day_type": row["day_type"].strip(),
                    "time_frame": row["time_frame"].strip(),
                    "start_hour": float(row["start_hour"]),
                    "end_hour": float(row["end_hour"]),
                    "zone": row["zone"].strip(),
                }
            )

    if not rows:
        raise ValueError("time_windows.csv has no data rows")

    # All rows must share a single timezone.
    zones = {r["zone"] for r in rows}
    if len(zones) > 1:
        raise ValueError(
            f"time_windows.csv must use a single timezone across all rows, found: {zones}"
        )

    # Validate coverage per day_type: no gaps, no overlaps, full [0, 24].
    for day_type in ("workday", "weekend"):
        day_rows = sorted(
            [r for r in rows if r["day_type"] == day_type],
            key=lambda r: r["start_hour"],
        )
        if not day_rows:
            raise ValueError(f"time_windows.csv has no rows for day_type='{day_type}'")
        if day_rows[0]["start_hour"] != 0:
            raise ValueError(
                f"time_windows.csv day_type='{day_type}': first window must start at 0, "
                f"got {day_rows[0]['start_hour']}"
            )
        if day_rows[-1]["end_hour"] != 24:
            raise ValueError(
                f"time_windows.csv day_type='{day_type}': last window must end at 24, "
                f"got {day_rows[-1]['end_hour']}"
            )
        for i in range(1, len(day_rows)):
            prev_end = day_rows[i - 1]["end_hour"]
            curr_start = day_rows[i]["start_hour"]
            if prev_end != curr_start:
                raise ValueError(
                    f"time_windows.csv day_type='{day_type}': gap or overlap between "
                    f"window {i - 1} (end={prev_end}) and window {i} (start={curr_start})"
                )

    return rows


def classify_window(
    dt_utc: "pd.Timestamp", windows: list[dict], tz: ZoneInfo
) -> tuple[str, str]:
    """Return (day_type, time_frame) for a UTC timestamp using the loaded windows."""
    dt_local = dt_utc.astimezone(tz)
    weekday = dt_local.weekday()  # 0=Mon … 6=Sun
    day_type = "weekend" if weekday >= 5 else "workday"
    # Fractional hour in local time (e.g. 13:30 → 13.5)
    local_hour = dt_local.hour + dt_local.minute / 60 + dt_local.second / 3600
    for row in windows:
        if row["day_type"] != day_type:
            continue
        # end_hour==24 is treated as the open upper bound for the day
        end = row["end_hour"]
        if row["start_hour"] <= local_hour < end or (end == 24 and local_hour >= row["start_hour"]):
            return day_type, row["time_frame"]
    # Fallback (should never happen if windows cover [0,24])
    return day_type, windows[-1]["time_frame"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Aggregate subminute XLSX data by slot-in-5m and price ranges."
    )
    parser.add_argument("--input", required=True, help="Input XLSX path.")
    parser.add_argument("--sheet", default="10sec", help="Sheet name to use.")
    parser.add_argument(
        "--output",
        default="backtest_output/pm_5m_slot_ranges.csv",
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
        help="Minimum count_of_klines_inside_range for filtered output.",
    )
    parser.add_argument(
        "--output-filtered",
        default="",
        help="Optional output CSV path for filtered rows (min-count applied).",
    )
    parser.add_argument(
        "--slot-seconds",
        type=int,
        default=10,
        help="Slot size in seconds (default: 10).",
    )
    parser.add_argument(
        "--prob-source",
        choices=["event_outcome", "rolling_columns"],
        default="event_outcome",
        help=(
            "How to compute prob_up/prob_down: "
            "'event_outcome' uses final result of each 5m block (recommended), "
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
        "--exclude-last-slot",
        action="store_true",
        help="Exclude final slot of 5m block from output (actionable pre-close).",
    )
    parser.add_argument(
        "--time-windows",
        default="config/time_windows.csv",
        help="Path to time_windows.csv defining day_type/time_frame buckets.",
    )
    return parser.parse_args()


def validate_columns(df: pd.DataFrame, prob_source: str) -> None:
    required = ["open_time_utc", "open", "close"]
    if prob_source == "rolling_columns":
        required.extend(["prob_up", "prob_down"])
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")


def build_ranges(price_move: pd.Series, step: float) -> tuple[pd.Series, pd.Series]:
    inf = np.floor(price_move / step) * step
    sup = inf + step
    return pd.Series(inf, index=price_move.index), pd.Series(
        sup, index=price_move.index
    )


def main() -> None:
    args = parse_args()
    step = float(args.range_step)
    slot_seconds = int(args.slot_seconds)
    if step <= 0:
        raise ValueError("--range-step must be > 0")
    if args.min_count < 1:
        raise ValueError("--min-count must be >= 1")
    if args.prior_alpha <= 0 or args.prior_beta <= 0:
        raise ValueError("--prior-alpha and --prior-beta must be > 0")
    if slot_seconds <= 0 or 300 % slot_seconds != 0:
        raise ValueError("--slot-seconds must be > 0 and divide 300 (5m) exactly.")

    # Load time-window definitions from CSV.
    windows = load_time_windows(args.time_windows)
    tz = ZoneInfo(windows[0]["zone"])
    print(f"Time windows loaded from {args.time_windows} (zone={windows[0]['zone']})")

    input_path = Path(args.input)
    if input_path.suffix.lower() == ".csv":
        df = pd.read_csv(input_path)
    else:
        df = pd.read_excel(input_path, sheet_name=args.sheet)
    validate_columns(df, prob_source=args.prob_source)

    df["open_time_utc"] = pd.to_datetime(df["open_time_utc"], errors="coerce", utc=True)
    df = (
        df.dropna(subset=["open_time_utc"])
        .sort_values("open_time_utc")
        .reset_index(drop=True)
    )

    numeric_cols = ["open", "close"]
    if args.prob_source == "rolling_columns":
        numeric_cols.extend(["prob_up", "prob_down"])
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=numeric_cols).reset_index(drop=True)

    if "ts_5m_block" in df.columns:
        maybe_block = pd.to_numeric(df["ts_5m_block"], errors="coerce")
        if maybe_block.notna().all():
            df["_block_key"] = maybe_block.astype("int64")
            df["_block_start"] = pd.to_datetime(df["_block_key"], unit="s", utc=True)
        else:
            df["_block_start"] = df["open_time_utc"].dt.floor("5min")
            df["_block_key"] = (df["_block_start"].astype("int64") // 1_000_000).astype(
                "int64"
            )
    else:
        df["_block_start"] = df["open_time_utc"].dt.floor("5min")
        df["_block_key"] = (df["_block_start"].astype("int64") // 1_000_000).astype(
            "int64"
        )

    # Classify each row's 5m block into (day_type, time_frame) using _block_start UTC.
    # We compute per unique block_key to avoid redundant conversions.
    block_start_series = df.groupby("_block_key", sort=False)["_block_start"].first()
    block_window: dict[int, tuple[str, str]] = {
        int(key): classify_window(ts, windows, tz)
        for key, ts in block_start_series.items()
    }
    df["day_type"] = df["_block_key"].map(lambda k: block_window[int(k)][0])
    df["time_frame"] = df["_block_key"].map(lambda k: block_window[int(k)][1])

    seconds_in_block = (df["open_time_utc"] - df["_block_start"]).dt.total_seconds()
    df["slot"] = (seconds_in_block // slot_seconds).astype(int) + 1
    max_slot = 300 // slot_seconds
    df = df[(df["slot"] >= 1) & (df["slot"] <= max_slot)].copy()

    # Keep full 5m data for event outcome labels (includes final slot).
    df_all = df
    slot_stats = df_all.groupby("_block_key", sort=False)["slot"].agg(
        count="size", nunique="nunique", min="min", max="max"
    )
    invalid_blocks = slot_stats[
        (slot_stats["count"] != max_slot)
        | (slot_stats["nunique"] != max_slot)
        | (slot_stats["min"] != 1)
        | (slot_stats["max"] != max_slot)
    ]
    if not invalid_blocks.empty:
        # Real-time exports can include the currently open 5m block at the end.
        # Drop only that trailing incomplete block; keep strict validation otherwise.
        last_block_key = int(df_all["_block_key"].max())
        trailing_incomplete = invalid_blocks[
            (invalid_blocks.index == last_block_key)
            & (
                (invalid_blocks["count"] < max_slot)
                | (invalid_blocks["nunique"] < max_slot)
                | (invalid_blocks["max"] < max_slot)
            )
        ]
        if not trailing_incomplete.empty:
            df_all = df_all[df_all["_block_key"] != last_block_key].copy()
            slot_stats = df_all.groupby("_block_key", sort=False)["slot"].agg(
                count="size", nunique="nunique", min="min", max="max"
            )
            invalid_blocks = slot_stats[
                (slot_stats["count"] != max_slot)
                | (slot_stats["nunique"] != max_slot)
                | (slot_stats["min"] != 1)
                | (slot_stats["max"] != max_slot)
            ]
    if not invalid_blocks.empty:
        sample_keys = invalid_blocks.index.astype(str).tolist()[:5]
        raise ValueError(
            "Detected invalid 5m blocks before aggregation: "
            f"expected unique slots 1..{max_slot} in every block, got mismatches in "
            f"{len(invalid_blocks)} block(s). Sample block keys: {sample_keys}"
        )

    ref_price_all = df_all.groupby("_block_key", sort=False)["open"].transform("first")
    final_close_all = df_all.groupby("_block_key", sort=False)["close"].transform(
        "last"
    )

    if args.exclude_last_slot:
        df = df_all[df_all["slot"] != max_slot].copy()
    else:
        df = df_all.copy()

    df["ref_price"] = df.groupby("_block_key", sort=False)["open"].transform("first")
    df["price_move"] = df["close"] - df["ref_price"]
    df["inf_range"], df["sup_range"] = build_ranges(df["price_move"], step=step)

    if args.prob_source == "event_outcome":
        final_close_event = final_close_all.loc[df.index]
        ref_price_event = ref_price_all.loc[df.index]
        df["prob_up_event"] = np.where(
            final_close_event > ref_price_event,
            1.0,
            np.where(final_close_event < ref_price_event, 0.0, 0.5),
        )
        df["prob_down_event"] = 1.0 - df["prob_up_event"]
        prob_up_col = "prob_up_event"
        prob_down_col = "prob_down_event"
    else:
        prob_up_col = "prob_up"
        prob_down_col = "prob_down"

    grouped = (
        df.groupby(["day_type", "time_frame", "slot", "inf_range", "sup_range"], as_index=False)
        .agg(
            prob_up=(prob_up_col, "mean"),
            prob_down=(prob_down_col, "mean"),
            count_of_klines_inside_range=("price_move", "count"),
        )
        .sort_values(
            ["day_type", "time_frame", "slot", "inf_range"],
            ascending=[True, True, True, True],
        )
        .reset_index(drop=True)
    )
    grouped["slot"] = grouped["slot"].astype(int)
    grouped["count_of_klines_inside_range"] = grouped[
        "count_of_klines_inside_range"
    ].astype(int)

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

    filtered = grouped[grouped["count_of_klines_inside_range"] >= args.min_count].copy()
    if args.output_filtered:
        filtered_output = Path(args.output_filtered)
    else:
        filtered_output = output.with_name(
            f"{output.stem}_mincount_{args.min_count}.csv"
        )
    filtered_output.parent.mkdir(parents=True, exist_ok=True)
    filtered.to_csv(filtered_output, index=False)

    print(f"Rows exported: {len(grouped)}")
    print(f"Output: {output}")
    print(f"Filtered rows exported (min_count>={args.min_count}): {len(filtered)}")
    print(f"Filtered output: {filtered_output}")


if __name__ == "__main__":
    main()
