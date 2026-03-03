#!/usr/bin/env python3
"""
Resample Binance klines CSV (including 1s) into multi-timeframe candles and export to Excel.

Examples:
  python3 resample_klines_to_excel_subminute.py \
    --input backtest_output/btcusdt_1s_7d.csv \
    --output backtest_output/btcusdt_subminute.xlsx \
    --intervals 10s,30s,1m,5m
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Resample klines CSV (supports seconds/minutes/hours) to Excel."
    )
    parser.add_argument("--input", required=True, help="Input CSV path.")
    parser.add_argument("--output", required=True, help="Output Excel path (.xlsx).")
    parser.add_argument(
        "--intervals",
        default="10s,30s,1m,5m",
        help="Comma-separated intervals, e.g. 10s,30s,1m,5m,15m,1h",
    )
    parser.add_argument(
        "--prob-window",
        type=int,
        default=20,
        help="Rolling window (rows) to estimate prob_up/prob_down.",
    )
    parser.add_argument(
        "--block-minutes",
        type=int,
        default=5,
        help="Block size in minutes for slot metadata (default: 5).",
    )
    return parser.parse_args()


def normalize_intervals(raw: str) -> list[str]:
    values = [v.strip().lower() for v in raw.split(",") if v.strip()]
    if not values:
        raise ValueError("At least one interval is required.")
    return values


def to_pandas_freq(interval: str) -> str:
    value = interval.lower().strip()
    if value.endswith("s"):
        return f"{int(value[:-1])}s"
    if value.endswith("m"):
        return f"{int(value[:-1])}min"
    if value.endswith("h"):
        return f"{int(value[:-1])}h"
    raise ValueError(f"Unsupported interval '{interval}'. Use Xs, Xm, or Xh.")


def interval_to_sheet(interval: str) -> str:
    value = interval.lower().strip()
    if value.endswith("s"):
        return f"{int(value[:-1])}sec"
    if value.endswith("m"):
        return f"{int(value[:-1])}min"
    if value.endswith("h"):
        return f"{int(value[:-1])}hour"
    return value


def load_base_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    required = [
        "open_time_utc",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "quote_asset_volume",
        "number_of_trades",
        "taker_buy_base_volume",
        "taker_buy_quote_volume",
    ]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    df["open_time_utc"] = pd.to_datetime(df["open_time_utc"], utc=True, errors="coerce")
    for col in required:
        if col != "open_time_utc":
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["open_time_utc", "open", "high", "low", "close"])
    df = df.sort_values("open_time_utc").set_index("open_time_utc")
    return df


def add_quant_features(
    out: pd.DataFrame,
    interval: str,
    prob_window: int,
    block_minutes: int,
) -> pd.DataFrame:
    out["roi_interval"] = (out["close"] - out["open"]) / out["open"]
    out["volatility"] = (out["high"] - out["low"]) / out["open"]
    out["log_return"] = np.log(out["close"] / out["close"].shift(1)).fillna(0.0)
    out["direction"] = np.where(
        out["close"] > out["open"],
        "up",
        np.where(out["close"] < out["open"], "down", "flat"),
    )
    out["up_move"] = (out["direction"] == "up").astype(int)
    out["down_move"] = (out["direction"] == "down").astype(int)

    window = max(1, int(prob_window))
    out["prob_up"] = out["up_move"].rolling(window=window, min_periods=1).mean()
    out["prob_down"] = 1.0 - out["prob_up"]

    block_freq = f"{int(block_minutes)}min"
    out["block_ts"] = out["open_time_utc"].dt.floor(block_freq)
    out["ts_5m_block"] = (out["block_ts"].astype("int64") // 1_000_000).astype("int64")

    slot_seconds = int(pd.to_timedelta(to_pandas_freq(interval)).total_seconds())
    seconds_in_block = (out["open_time_utc"] - out["block_ts"]).dt.total_seconds()
    out["slot_in_block"] = (seconds_in_block // slot_seconds).astype(int) + 1
    out["slot_seconds"] = slot_seconds
    return out


def resample_ohlcv(
    df: pd.DataFrame, interval: str, prob_window: int, block_minutes: int
) -> pd.DataFrame:
    freq = to_pandas_freq(interval)
    out = df.resample(freq).agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
        quote_asset_volume=("quote_asset_volume", "sum"),
        number_of_trades=("number_of_trades", "sum"),
        taker_buy_base_volume=("taker_buy_base_volume", "sum"),
        taker_buy_quote_volume=("taker_buy_quote_volume", "sum"),
    )

    out = out.dropna(subset=["open", "high", "low", "close"]).copy()
    out["open_time_utc"] = out.index.tz_convert("UTC").tz_localize(None)
    out["open_time"] = (out["open_time_utc"].astype("int64") // 1_000_000).astype(
        "int64"
    )
    interval_ms = int(pd.to_timedelta(freq).total_seconds() * 1000)
    out["close_time"] = out["open_time"] + interval_ms - 1

    out = out[
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
    ].reset_index(drop=True)

    out = add_quant_features(
        out,
        interval=interval,
        prob_window=prob_window,
        block_minutes=block_minutes,
    )
    return out


def main() -> None:
    args = parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output)
    intervals = normalize_intervals(args.intervals)
    is_csv_mode = output_path.suffix.lower() == ".csv"

    if is_csv_mode and len(intervals) > 1:
        raise ValueError(
            "CSV output mode supports only one interval at a time. "
            f"Got: {intervals}. Use a single interval or switch to .xlsx output."
        )

    base = load_base_csv(input_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if is_csv_mode:
        interval = intervals[0]
        rs = resample_ohlcv(
            base,
            interval=interval,
            prob_window=args.prob_window,
            block_minutes=args.block_minutes,
        )
        rs.to_csv(output_path, index=False)
        print(f"CSV created: {output_path}")
        print(f"Rows: {len(rs)}")
    else:
        with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
            for interval in intervals:
                rs = resample_ohlcv(
                    base,
                    interval=interval,
                    prob_window=args.prob_window,
                    block_minutes=args.block_minutes,
                )
                sheet = interval_to_sheet(interval)[:31]
                rs.to_excel(writer, sheet_name=sheet, index=False)

        print(f"Excel created: {output_path}")
        print(f"Intervals: {', '.join(intervals)}")


if __name__ == "__main__":
    main()
