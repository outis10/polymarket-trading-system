#!/usr/bin/env python3
"""
Plot Binance price series and overlay Polymarket event-close markers.

Usage examples:

1) Using exported PM windows (recommended, no network):
  python3 plot_price_with_pm_closes.py \
    --input backtest_output/btcusdt_1s_20260209_20260214.csv \
    --events-csv backtest_output/pm_5m_last180s_1s.csv \
    --ticker BTC \
    --resample-seconds 10 \
    --output backtest_output/btc_1s_with_pm_closes.png

2) Auto-discover closes from Gamma:
  python3 plot_price_with_pm_closes.py \
    --input backtest_output/btcusdt_1s_20260209_20260214.csv \
    --ticker BTC \
    --discover \
    --lookahead-days 21 \
    --resample-seconds 10
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Plot price and overlay PM event close timestamps."
    )
    parser.add_argument("--input", required=True, help="Input Binance CSV path.")
    parser.add_argument(
        "--events-csv",
        default="",
        help="Optional CSV with event_end_utc column (e.g. pm_5m_last180s_1s.csv).",
    )
    parser.add_argument(
        "--ticker",
        default="BTC",
        help="Ticker filter for markers (BTC,ETH,SOL,XRP). Default: BTC",
    )
    parser.add_argument(
        "--resample-seconds",
        type=int,
        default=10,
        help="Resample step for price series in seconds (default: 10).",
    )
    parser.add_argument(
        "--start",
        default="",
        help="Optional UTC lower bound YYYY-MM-DD for plotting window.",
    )
    parser.add_argument(
        "--end",
        default="",
        help="Optional UTC upper bound YYYY-MM-DD for plotting window.",
    )
    parser.add_argument(
        "--discover",
        action="store_true",
        help="Discover PM event closes from Gamma API instead of events CSV.",
    )
    parser.add_argument(
        "--lookahead-days",
        type=int,
        default=21,
        help="Used with --discover.",
    )
    parser.add_argument(
        "--output",
        default="",
        help="Optional PNG output path. If empty, shows interactive plot.",
    )
    return parser.parse_args()


def load_price(path: Path, resample_seconds: int) -> pd.Series:
    df = pd.read_csv(path)
    if "open_time_utc" in df.columns:
        ts = pd.to_datetime(df["open_time_utc"], utc=True, errors="coerce")
    elif "open_time" in df.columns:
        ts = pd.to_datetime(df["open_time"], unit="ms", utc=True, errors="coerce")
    else:
        raise ValueError("CSV must contain open_time_utc or open_time.")

    close = pd.to_numeric(df.get("close"), errors="coerce")
    out = pd.DataFrame({"ts": ts, "close": close}).dropna().sort_values("ts")
    if out.empty:
        raise ValueError("No valid price rows after parsing.")
    series = (
        out.set_index("ts")["close"].resample(f"{max(1, resample_seconds)}s").last()
    )
    return series.dropna()


def load_event_closes_from_csv(path: Path, ticker: str) -> list[pd.Timestamp]:
    df = pd.read_csv(path)
    if "event_end_utc" not in df.columns:
        raise ValueError("events CSV must contain event_end_utc.")
    if "ticker" in df.columns:
        df = df[df["ticker"].astype(str).str.upper() == ticker.upper()]
    closes = pd.to_datetime(df["event_end_utc"], utc=True, errors="coerce").dropna()
    closes = closes.drop_duplicates().sort_values()
    return list(closes)


def discover_event_closes(ticker: str, lookahead_days: int) -> list[pd.Timestamp]:
    from backend.services.event_discovery import discover_live_events

    cfg = {
        "enabled": True,
        "symbols": [ticker.upper()],
        "lookahead_days": int(lookahead_days),
        "max_events": 400,
        "require_15m": False,
        "allowed_timeframes": [5, 15, 60],
        "only_live_now": False,
        "min_minutes": 3,
        "max_minutes": 70,
    }
    events = discover_live_events(cfg)
    raw = [e.get("event_end_time", "") for e in events]
    closes = pd.to_datetime(raw, utc=True, errors="coerce")
    closes = pd.Series(closes).dropna().drop_duplicates().sort_values()
    return list(closes)


def filter_window(
    series: pd.Series, closes: list[pd.Timestamp], start: str, end: str
) -> tuple[pd.Series, list[pd.Timestamp]]:
    out = series
    if start:
        start_ts = pd.to_datetime(start, utc=True)
        out = out[out.index >= start_ts]
    if end:
        end_ts = pd.to_datetime(end, utc=True)
        out = out[out.index < end_ts]

    min_ts = out.index.min() if not out.empty else None
    max_ts = out.index.max() if not out.empty else None
    if min_ts is not None and max_ts is not None:
        closes = [c for c in closes if min_ts <= c <= max_ts]
    return out, closes


def main() -> None:
    args = parse_args()
    ticker = args.ticker.upper()

    price = load_price(Path(args.input), args.resample_seconds)
    if args.discover:
        closes = discover_event_closes(
            ticker=ticker, lookahead_days=args.lookahead_days
        )
    else:
        if not args.events_csv:
            raise ValueError("Provide --events-csv or use --discover.")
        closes = load_event_closes_from_csv(Path(args.events_csv), ticker=ticker)

    price, closes = filter_window(price, closes, args.start, args.end)
    if price.empty:
        raise ValueError("No rows left in selected plotting window.")

    fig, ax = plt.subplots(figsize=(14, 5))
    ax.plot(price.index, price.values, linewidth=0.9, label=f"{ticker} close")

    for i, close_ts in enumerate(closes):
        ax.axvline(
            close_ts,
            color="#f26a5c",
            linestyle="--",
            linewidth=0.8,
            alpha=0.55,
            label="PM close" if i == 0 else None,
        )

    ax.set_title(
        f"{ticker} price ({args.resample_seconds}s) with PM closes "
        f"[markers={len(closes)}]"
    )
    ax.set_xlabel("Time (UTC)")
    ax.set_ylabel("Price")
    ax.grid(alpha=0.22)
    ax.legend(loc="best")
    fig.tight_layout()

    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(out, dpi=140)
        print(f"Saved plot: {out}")
    else:
        plt.show()


if __name__ == "__main__":
    main()
