"""
Retroactively resolves bot orders that are placed+pending because
the bot was offline when those events closed.

Queries Binance 1m klines for the BTC/ETH close price at each event's
end time, then applies the same resolution logic as _reconcile_bot_orders.

Usage:
    python3 scripts/resolve_pending_bot_orders.py [--dry-run]
"""

import csv
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone

BACKTEST_DIR = os.path.join(os.path.dirname(__file__), "..", "backtest_output")
DRY_RUN = "--dry-run" in sys.argv

TICKER_SYMBOL = {"BTC": "BTCUSDT", "ETH": "ETHUSDT"}

# Must match _BOT_ORDERS_FIELDNAMES in event_manager.py
FIELDNAMES = [
    "placed_at_utc", "event_id", "ticker", "slot", "range", "side",
    "event_end_utc_at_send", "token_id", "shares", "price", "notional_usd",
    "order_id", "quant_prob", "edge_pct", "price_source_at_send",
    "price_to_beat_at_send", "current_price_at_send", "diff_vs_ptb_at_send",
    "best_bid_at_send", "best_ask_at_send", "mid_at_send", "spread_at_send",
    "spread_pct_at_send", "fill_price_real", "filled_at_utc", "fill_latency_ms",
    "slippage_pct", "filled_notional_usd_real", "filled_shares_real", "fill_count",
    "fills_detail_json", "edge_at_fill_pct", "kelly_pct", "bankroll_usd",
    "percentile_at_signal", "close_price_at_resolution", "event_outcome_real",
    "won", "pnl_simulated", "resolution_status", "status",
]


def fetch_btc_price_at(end_utc: datetime, symbol: str = "BTCUSDT") -> float:
    """Return the close price of the 1m candle that closes at end_utc."""
    end_ms = int(end_utc.timestamp() * 1000)
    start_ms = end_ms - 60_000  # 1 minute before → candle closes AT end_utc
    url = (
        f"https://api.binance.com/api/v3/klines"
        f"?symbol={symbol}&interval=1m&startTime={start_ms}&limit=1"
    )
    with urllib.request.urlopen(url, timeout=10) as r:
        data = json.load(r)
    if not data:
        raise ValueError(f"No kline data for {symbol} at {end_utc}")
    return float(data[0][4])  # close price


def resolve_csv(path: str) -> int:
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))

    changed = 0
    for row in rows:
        if row.get("status") != "placed":
            continue
        if row.get("resolution_status") == "resolved":
            continue

        end_raw = row.get("event_end_utc_at_send", "").strip()
        if not end_raw:
            continue
        try:
            end_dt = datetime.fromisoformat(end_raw)
            if end_dt.tzinfo is None:
                end_dt = end_dt.replace(tzinfo=timezone.utc)
        except Exception:
            print(f"  [SKIP] bad end date: {end_raw}")
            continue

        now = datetime.now(timezone.utc)
        if now < end_dt:
            print(f"  [SKIP] event not yet ended: {end_raw}")
            continue

        ticker = row.get("ticker", "BTC").upper()
        symbol = TICKER_SYMBOL.get(ticker, f"{ticker}USDT")

        try:
            close_price = fetch_btc_price_at(end_dt, symbol)
        except Exception as e:
            print(f"  [ERROR] fetching price for {row['event_id']}: {e}")
            continue

        ptb_str = row.get("price_to_beat_at_send", "").strip()
        try:
            ptb = float(ptb_str)
        except (ValueError, TypeError):
            print(f"  [SKIP] bad ptb: {ptb_str}")
            continue

        q_str = row.get("fill_price_real", "").strip() or row.get("price", "").strip()
        try:
            q = float(q_str)
        except (ValueError, TypeError):
            print(f"  [SKIP] bad price/fill_price_real: {q_str}")
            continue

        stake_str = row.get("filled_notional_usd_real", "").strip()
        if not stake_str or float(stake_str) <= 0:
            stake_str = row.get("notional_usd", "").strip()
        try:
            stake = float(stake_str)
        except (ValueError, TypeError):
            print(f"  [SKIP] bad stake: {stake_str}")
            continue

        side = row.get("side", "").strip().lower()
        if side not in {"up", "down"}:
            print(f"  [SKIP] bad side: {side}")
            continue

        event_outcome_real = "up" if close_price >= ptb else "down"
        won = event_outcome_real == side
        pnl = (stake * (1.0 / q - 1.0)) if won else (-stake)

        print(
            f"  {'[DRY]' if DRY_RUN else '[FIX]'} {row['event_id']} | "
            f"end={end_raw[:16]} ptb={ptb:.2f} close={close_price:.2f} "
            f"side={side} outcome={event_outcome_real} won={won} pnl={pnl:.4f}"
        )

        row["close_price_at_resolution"] = f"{close_price:.6f}"
        row["event_outcome_real"] = event_outcome_real
        row["won"] = "1" if won else "0"
        row["pnl_simulated"] = f"{pnl:.6f}"
        row["resolution_status"] = "resolved"
        changed += 1

    if changed and not DRY_RUN:
        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
            writer.writeheader()
            for row in rows:
                writer.writerow({k: row.get(k, "") for k in FIELDNAMES})
        print(f"  → Saved {changed} resolved rows to {os.path.basename(path)}")

    return changed


def main():
    import re
    pattern = re.compile(r"^bot_orders_\d{4}-\d{2}-\d{2}\.csv$")
    files = sorted(
        os.path.join(BACKTEST_DIR, f)
        for f in os.listdir(BACKTEST_DIR)
        if pattern.match(f)
    )
    if not files:
        print("No bot_orders_*.csv files found.")
        return

    total = 0
    for path in files:
        print(f"\n{os.path.basename(path)}:")
        total += resolve_csv(path)

    print(f"\nTotal resolved: {total}" + (" (dry run)" if DRY_RUN else ""))


if __name__ == "__main__":
    main()
