#!/usr/bin/env python3
"""
Validate subminute resample output against source 1s klines and generate plots.

Example:
  python3 validate_resample_subminute.py \
    --base-csv backtest_output/btcusdt_1s_7d.csv \
    --resampled-xlsx backtest_output/btcusdt_subminute.xlsx \
    --sheet 10sec \
    --output-dir backtest_output/validation
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate 1s -> subminute resample with integrity checks + charts."
    )
    parser.add_argument("--base-csv", required=True, help="Source 1s CSV path.")
    parser.add_argument("--resampled-xlsx", required=True, help="Resampled XLSX path.")
    parser.add_argument("--sheet", default="10sec", help="Sheet name to validate.")
    parser.add_argument(
        "--start",
        default="",
        help="Optional start datetime (UTC) for focused validation window.",
    )
    parser.add_argument(
        "--end",
        default="",
        help="Optional end datetime (UTC) for focused validation window.",
    )
    parser.add_argument(
        "--tolerance",
        type=float,
        default=1e-8,
        help="Absolute tolerance for OHLCV numeric comparisons.",
    )
    parser.add_argument(
        "--output-dir",
        default="backtest_output/validation",
        help="Directory for report and charts.",
    )
    parser.add_argument(
        "--prefix",
        default="",
        help="Optional output file prefix (defaults to sheet name).",
    )
    return parser.parse_args()


def load_base_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    required = ["open_time_utc", "open", "high", "low", "close", "volume"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns in base CSV: {missing}")
    df["open_time_utc"] = pd.to_datetime(df["open_time_utc"], utc=True, errors="coerce")
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=required).sort_values("open_time_utc")
    return df.reset_index(drop=True)


def load_resampled_sheet(path: Path, sheet: str) -> pd.DataFrame:
    df = pd.read_excel(path, sheet_name=sheet)
    required = ["open_time_utc", "open", "high", "low", "close", "volume"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns in resampled sheet: {missing}")
    # Resample script stores naive UTC timestamps; localize to UTC for safe joins.
    ts = pd.to_datetime(df["open_time_utc"], errors="coerce")
    if getattr(ts.dt, "tz", None) is None:
        ts = ts.dt.tz_localize("UTC")
    else:
        ts = ts.dt.tz_convert("UTC")
    df["open_time_utc"] = ts
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=required).sort_values("open_time_utc")
    return df.reset_index(drop=True)


def infer_interval_seconds(resampled: pd.DataFrame) -> int:
    if len(resampled) < 2:
        raise ValueError("Need at least 2 rows in resampled data to infer interval.")
    diffs = (
        resampled["open_time_utc"].diff().dt.total_seconds().dropna().astype(int).values
    )
    if len(diffs) == 0:
        raise ValueError("Could not infer interval from timestamps.")
    values, counts = np.unique(diffs, return_counts=True)
    return int(values[np.argmax(counts)])


def clamp_window(
    df: pd.DataFrame, start: str, end: str, ts_col: str = "open_time_utc"
) -> pd.DataFrame:
    out = df
    if start:
        s = pd.to_datetime(start, utc=True, errors="coerce")
        if pd.isna(s):
            raise ValueError(f"Invalid --start datetime: {start}")
        out = out[out[ts_col] >= s]
    if end:
        e = pd.to_datetime(end, utc=True, errors="coerce")
        if pd.isna(e):
            raise ValueError(f"Invalid --end datetime: {end}")
        out = out[out[ts_col] <= e]
    return out.reset_index(drop=True)


def aggregate_base(base: pd.DataFrame, interval_seconds: int) -> pd.DataFrame:
    freq = f"{int(interval_seconds)}s"
    x = base.set_index("open_time_utc")
    agg = x.resample(freq).agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
    )
    agg = agg.dropna(subset=["open", "high", "low", "close"]).reset_index()
    return agg


def build_report(
    joined: pd.DataFrame, resampled: pd.DataFrame, interval_seconds: int, tol: float
) -> dict:
    report: dict[str, object] = {
        "interval_seconds_inferred": int(interval_seconds),
        "rows_resampled": int(len(resampled)),
        "rows_joined": int(len(joined)),
    }

    # Time alignment check
    diffs = resampled["open_time_utc"].diff().dt.total_seconds().dropna()
    misaligned_count = int((diffs != interval_seconds).sum()) if len(diffs) else 0
    report["time_alignment"] = {
        "ok": misaligned_count == 0,
        "misaligned_steps": misaligned_count,
    }

    checks = {}
    for col in ["open", "high", "low", "close", "volume"]:
        diff_col = f"diff_{col}"
        joined[diff_col] = (joined[f"{col}_rs"] - joined[f"{col}_agg"]).abs()
        max_abs = float(joined[diff_col].max()) if len(joined) else float("nan")
        fail = int((joined[diff_col] > tol).sum()) if len(joined) else 0
        checks[col] = {
            "max_abs_diff": max_abs,
            "rows_above_tolerance": fail,
            "ok": fail == 0,
        }

    # OHLC sanity checks on resampled output
    sanity_fail = int(
        (
            (resampled["high"] < resampled[["open", "close"]].max(axis=1))
            | (resampled["low"] > resampled[["open", "close"]].min(axis=1))
            | (resampled["low"] > resampled["high"])
        ).sum()
    )
    checks["ohlc_sanity"] = {
        "invalid_rows": sanity_fail,
        "ok": sanity_fail == 0,
    }

    report["checks"] = checks
    pass_flags = [v.get("ok", False) for v in checks.values()]
    pass_flags.append(report["time_alignment"]["ok"])  # type: ignore[index]
    report["overall_ok"] = bool(all(pass_flags))
    return report


def save_plots(
    joined: pd.DataFrame,
    output_dir: Path,
    output_prefix: str,
) -> tuple[Path, Path]:
    close_png = output_dir / f"{output_prefix}_close_overlay.png"
    vol_png = output_dir / f"{output_prefix}_volume_compare.png"

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 8), sharex=True)
    ax1.plot(joined["open_time_utc"], joined["close_agg"], label="close_agg_from_1s")
    ax1.plot(joined["open_time_utc"], joined["close_rs"], label="close_resampled_10s")
    ax1.set_ylabel("Price")
    ax1.set_title("Close Overlay Validation")
    ax1.legend(loc="best")
    ax1.grid(alpha=0.25)

    ax2.plot(
        joined["open_time_utc"],
        (joined["close_rs"] - joined["close_agg"]).abs(),
        color="#f85149",
        label="|close diff|",
    )
    ax2.set_ylabel("Abs Diff")
    ax2.set_xlabel("Time (UTC)")
    ax2.legend(loc="best")
    ax2.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(close_png, dpi=150)
    plt.close(fig)

    fig2, ax = plt.subplots(figsize=(14, 4.8))
    ax.plot(joined["open_time_utc"], joined["volume_agg"], label="volume_agg_from_1s")
    ax.plot(
        joined["open_time_utc"],
        joined["volume_rs"],
        label="volume_resampled_10s",
        alpha=0.8,
    )
    ax.set_title("Volume Consistency Validation")
    ax.set_ylabel("Volume")
    ax.set_xlabel("Time (UTC)")
    ax.legend(loc="best")
    ax.grid(alpha=0.25)
    fig2.tight_layout()
    fig2.savefig(vol_png, dpi=150)
    plt.close(fig2)

    return close_png, vol_png


def main() -> None:
    args = parse_args()
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    base = load_base_csv(Path(args.base_csv))
    rs = load_resampled_sheet(Path(args.resampled_xlsx), args.sheet)

    base = clamp_window(base, args.start, args.end)
    rs = clamp_window(rs, args.start, args.end)
    if base.empty or rs.empty:
        raise ValueError("No rows left after window filter. Check --start/--end.")

    interval_seconds = infer_interval_seconds(rs)
    agg = aggregate_base(base, interval_seconds=interval_seconds)

    joined = rs.merge(
        agg,
        on="open_time_utc",
        how="inner",
        suffixes=("_rs", "_agg"),
    )
    if joined.empty:
        raise ValueError("No overlap between resampled sheet and aggregated 1s data.")

    report = build_report(
        joined=joined.copy(),
        resampled=rs,
        interval_seconds=interval_seconds,
        tol=float(args.tolerance),
    )

    prefix = args.prefix.strip() or args.sheet.strip() or "validation"
    close_png, vol_png = save_plots(
        joined=joined, output_dir=out_dir, output_prefix=prefix
    )

    report_path = out_dir / f"{prefix}_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, sort_keys=True)

    print("Validation finished.")
    print(f"Overall OK: {report['overall_ok']}")
    print(f"Rows joined: {len(joined)}")
    print(f"Report: {report_path}")
    print(f"Close overlay chart: {close_png}")
    print(f"Volume chart: {vol_png}")


if __name__ == "__main__":
    main()
