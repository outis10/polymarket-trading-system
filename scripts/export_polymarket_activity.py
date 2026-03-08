"""
Export all Polymarket activity for a wallet to CSV.

Endpoints hit:
  - data-api.polymarket.com/activity   (trades executados)
  - data-api.polymarket.com/positions  (posiciones actuales, incluye resueltas con value>0)
  - data-api.polymarket.com/portfolio  (P&L por mercado)

Usage:
    python3 scripts/export_polymarket_activity.py
    python3 scripts/export_polymarket_activity.py --wallet 0xABC...
    python3 scripts/export_polymarket_activity.py --out backtest_output/my_activity.csv
"""

import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
DATA_API = "https://data-api.polymarket.com"
PAGE_SIZE = 100
RATE_LIMIT_DELAY = 0.3  # seconds between pages

OUTPUT_DIR = Path(__file__).parent.parent / "backtest_output"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_wallet() -> str:
    """Read POLYMARKET_FUNDER from .env or environment."""
    # Try env first
    w = os.getenv("POLYMARKET_FUNDER", "")
    if w:
        return w
    # Try root .env
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line.startswith("POLYMARKET_FUNDER="):
                return line.split("=", 1)[1].strip()
    return ""


def _paginate(endpoint: str, wallet: str, extra_params: dict | None = None) -> list[dict]:
    """Fetch all pages from a data-api endpoint."""
    results: list[dict] = []
    offset = 0
    while True:
        params = {"user": wallet, "limit": PAGE_SIZE, "offset": offset}
        if extra_params:
            params.update(extra_params)
        try:
            r = requests.get(f"{DATA_API}/{endpoint}", params=params, timeout=15)
            r.raise_for_status()
            page = r.json()
        except Exception as exc:
            print(f"  [!] {endpoint} offset={offset}: {exc}")
            break

        if not page:
            break
        results.extend(page)
        print(f"  {endpoint}: {len(results)} rows fetched...", end="\r")
        if len(page) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
        time.sleep(RATE_LIMIT_DELAY)

    print(f"  {endpoint}: {len(results)} rows total          ")
    return results


def _save_csv(rows: list[dict], path: Path, label: str) -> None:
    if not rows:
        print(f"  [{label}] No data, skipping.")
        return
    # Collect all keys across all rows (some rows may have different fields)
    fieldnames = list(dict.fromkeys(k for row in rows for k in row.keys()))
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            # Flatten nested dicts/lists to JSON strings for readability
            flat = {}
            for k, v in row.items():
                if isinstance(v, (dict, list)):
                    flat[k] = json.dumps(v)
                else:
                    flat[k] = v
            writer.writerow(flat)
    print(f"  [{label}] Saved {len(rows)} rows → {path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Export Polymarket wallet activity to CSV")
    parser.add_argument("--wallet", default="", help="Wallet address (default: POLYMARKET_FUNDER from .env)")
    parser.add_argument("--out-dir", default=str(OUTPUT_DIR), help="Output directory")
    args = parser.parse_args()

    wallet = args.wallet or _get_wallet()
    if not wallet:
        print("ERROR: No wallet address found. Pass --wallet or set POLYMARKET_FUNDER in .env")
        sys.exit(1)

    out_dir = Path(args.out_dir)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    print(f"\nExporting Polymarket activity for {wallet[:10]}...{wallet[-6:]}")
    print(f"Output dir: {out_dir}\n")

    # 1. Activity (trades executed)
    print("1. Fetching trades/activity...")
    activity = _paginate("activity", wallet)
    _save_csv(activity, out_dir / f"polymarket_activity_{ts}.csv", "activity")

    # 2. Positions (open + recently resolved with value)
    print("\n2. Fetching positions...")
    positions = _paginate("positions", wallet, {"sizeThreshold": "0"})
    _save_csv(positions, out_dir / f"polymarket_positions_{ts}.csv", "positions")

    # 3. Portfolio P&L summary per market
    print("\n3. Fetching portfolio P&L...")
    try:
        r = requests.get(f"{DATA_API}/portfolio", params={"user": wallet}, timeout=15)
        r.raise_for_status()
        portfolio = r.json()
        if isinstance(portfolio, dict):
            portfolio = [portfolio]
        _save_csv(portfolio, out_dir / f"polymarket_portfolio_{ts}.csv", "portfolio")
    except Exception as exc:
        print(f"  [portfolio] Error: {exc}")

    print("\nDone. Files written to:", out_dir)
    print("\nColumns available per file:")
    for label, fname in [
        ("activity", f"polymarket_activity_{ts}.csv"),
        ("positions", f"polymarket_positions_{ts}.csv"),
        ("portfolio", f"polymarket_portfolio_{ts}.csv"),
    ]:
        p = out_dir / fname
        if p.exists():
            with open(p) as f:
                header = f.readline().strip()
            print(f"  [{label}] {header}")


if __name__ == "__main__":
    main()
