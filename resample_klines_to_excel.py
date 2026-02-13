#!/usr/bin/env python3
"""
Resample 1m Binance klines CSV into multi-timeframe candles and export to Excel.

Example:
  python resample_klines_to_excel.py \
    --input btcusdt_1m_3m.csv \
    --output btcusdt_multiframe.xlsx \
    --intervals 2m,3m,5m,15m
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Resample klines CSV to Excel.")
    parser.add_argument("--input", required=True, help="Input CSV path (1m klines).")
    parser.add_argument("--output", required=True, help="Output Excel path (.xlsx).")
    parser.add_argument(
        "--intervals",
        default="2m,3m,5m,15m",
        help="Comma-separated intervals, e.g. 2m,3m,5m,15m,30m,1h",
    )
    parser.add_argument(
        "--prob-window",
        type=int,
        default=20,
        help="Rolling window (rows) to estimate prob_up/prob_down.",
    )
    return parser.parse_args()


def normalize_intervals(raw: str) -> list[str]:
    values = [v.strip().lower() for v in raw.split(",") if v.strip()]
    if not values:
        raise ValueError("At least one interval is required.")
    return values


def to_pandas_freq(interval: str) -> str:
    interval = interval.lower().strip()
    if interval.endswith("m"):
        return f"{int(interval[:-1])}min"
    if interval.endswith("h"):
        return f"{int(interval[:-1])}h"
    raise ValueError(f"Unsupported interval '{interval}'. Use Xm or Xh.")


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

    df["open_time_utc"] = pd.to_datetime(df["open_time_utc"], utc=True)
    numeric_cols = [c for c in required if c != "open_time_utc"]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=["open_time_utc", "open", "high", "low", "close"])
    df = df.sort_values("open_time_utc").set_index("open_time_utc")
    return df


def add_quant_features(
    out: pd.DataFrame, interval: str, prob_window: int
) -> pd.DataFrame:
    """Add quantitative-analysis columns."""
    minutes = interval.lower().replace("m", "")
    roi_col = f"roi_{minutes}m" if minutes.isdigit() else "roi_interval"

    out["roi_x_minute"] = (out["close"] - out["open"]) / out["open"]
    out[roi_col] = out["roi_x_minute"]
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

    # 15m block metadata for cross-timeframe grouping
    out["15m_block_ts"] = out["open_time_utc"].dt.floor("15min")
    out["ts_15m_block"] = (out["15m_block_ts"].astype("int64") // 1_000_000).astype(
        "int64"
    )

    return out


def resample_ohlcv(df: pd.DataFrame, interval: str, prob_window: int) -> pd.DataFrame:
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
    ]

    out = out.reset_index(drop=True)
    out = add_quant_features(out, interval=interval, prob_window=prob_window)
    return out


def main() -> None:
    args = parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output)
    intervals = normalize_intervals(args.intervals)

    base = load_base_csv(input_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    summary_rows: list[dict[str, float | int | str]] = []

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        for interval in intervals:
            rs = resample_ohlcv(base, interval, prob_window=args.prob_window)
            sheet = interval.replace("m", "min").replace("h", "hour")
            rs.to_excel(writer, sheet_name=sheet[:31], index=False)

            summary_rows.append(
                {
                    "interval": interval,
                    "rows": int(len(rs)),
                    "start_utc": rs["open_time_utc"].min() if len(rs) else None,
                    "end_utc": rs["open_time_utc"].max() if len(rs) else None,
                    "mean_roi": float(rs["roi_x_minute"].mean()) if len(rs) else 0.0,
                    "std_roi": float(rs["roi_x_minute"].std()) if len(rs) else 0.0,
                    "mean_volatility": float(rs["volatility"].mean())
                    if len(rs)
                    else 0.0,
                    "std_volatility": float(rs["volatility"].std()) if len(rs) else 0.0,
                    "pct_up": float((rs["direction"] == "up").mean())
                    if len(rs)
                    else 0.0,
                    "pct_down": float((rs["direction"] == "down").mean())
                    if len(rs)
                    else 0.0,
                    "pct_flat": float((rs["direction"] == "flat").mean())
                    if len(rs)
                    else 0.0,
                    "final_prob_up": float(rs["prob_up"].iloc[-1]) if len(rs) else 0.0,
                    "final_prob_down": float(rs["prob_down"].iloc[-1])
                    if len(rs)
                    else 0.0,
                }
            )

        summary_df = pd.DataFrame(summary_rows)
        summary_df.to_excel(writer, sheet_name="features_summary", index=False)

    print(f"Excel created: {output_path}")
    print(f"Intervals: {', '.join(intervals)}")


if __name__ == "__main__":
    main()
