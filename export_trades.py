#!/usr/bin/env python3
"""
Export trade history from Polymarket to CSV/JSON.

Examples:
  python export_trades.py --output trades.csv
  python export_trades.py --format json --output trades.json --limit 500
  python export_trades.py --poll-seconds 1 --duration-seconds 600 --append
"""

from __future__ import annotations

import argparse
import csv
import json
import time
from pathlib import Path
from typing import Any

from config.settings import Settings
from core.client_wrapper import PolymarketClient


def _to_dict(trade: Any) -> dict[str, Any]:
    """Normalize trade objects to plain dictionaries."""
    if isinstance(trade, dict):
        return trade
    if hasattr(trade, "model_dump"):
        return trade.model_dump()
    if hasattr(trade, "dict"):
        return trade.dict()
    if hasattr(trade, "__dict__"):
        return {k: v for k, v in vars(trade).items() if not k.startswith("_")}
    return {"value": str(trade)}


def _trade_key(trade: dict[str, Any]) -> str:
    """Build a stable key for de-duplication in polling mode."""
    return "|".join(
        [
            str(
                trade.get("id")
                or trade.get("trade_id")
                or trade.get("transaction_hash")
                or ""
            ),
            str(trade.get("asset_id") or trade.get("token_id") or ""),
            str(trade.get("side") or ""),
            str(trade.get("size") or trade.get("shares") or ""),
            str(trade.get("price") or ""),
            str(trade.get("timestamp") or trade.get("created_at") or ""),
        ]
    )


def _filter_local(
    trades: list[dict[str, Any]], args: argparse.Namespace
) -> list[dict[str, Any]]:
    """Apply local filters in case upstream API ignores unsupported params."""
    out = trades

    if args.side:
        side = args.side.upper()
        out = [t for t in out if str(t.get("side", "")).upper() == side]

    if args.asset_id:
        out = [t for t in out if str(t.get("asset_id", "")) == args.asset_id]

    if args.market:
        market_q = args.market.lower()
        out = [t for t in out if market_q in str(t.get("market", "")).lower()]

    return out


def _write_json(path: Path, trades: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(trades, f, indent=2, ensure_ascii=False)


def _write_csv(path: Path, trades: list[dict[str, Any]], append: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    if not trades:
        if not append and not path.exists():
            with path.open("w", newline="", encoding="utf-8") as f:
                f.write("")
        return

    existing_fields: list[str] = []
    if append and path.exists() and path.stat().st_size > 0:
        with path.open("r", newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            existing_fields = next(reader, [])

    fields: list[str] = existing_fields or sorted(
        {k for trade in trades for k in trade.keys()}
    )
    mode = "a" if append else "w"

    write_header = True
    if append and path.exists() and path.stat().st_size > 0:
        write_header = False

    with path.open(mode, newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        if write_header:
            writer.writeheader()
        for trade in trades:
            writer.writerow(trade)


def _fetch_trades(
    client: PolymarketClient, args: argparse.Namespace
) -> list[dict[str, Any]]:
    raw = client.get_trades()
    normalized = [_to_dict(t) for t in raw]
    return _filter_local(normalized, args)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export Polymarket trade history.")
    parser.add_argument(
        "--output", default="trades_export.csv", help="Output path for CSV/JSON."
    )
    parser.add_argument(
        "--format", choices=["csv", "json"], default="csv", help="Export format."
    )
    parser.add_argument(
        "--limit", type=int, default=None, help="Max trades per fetch request."
    )
    parser.add_argument(
        "--market",
        default=None,
        help="Market filter (id/name, depending on API support).",
    )
    parser.add_argument("--asset-id", default=None, help="Asset/Token ID filter.")
    parser.add_argument(
        "--side",
        choices=["BUY", "SELL", "buy", "sell"],
        default=None,
        help="Filter by side.",
    )
    parser.add_argument(
        "--before", default=None, help="API before cursor/time if supported."
    )
    parser.add_argument(
        "--after", default=None, help="API after cursor/time if supported."
    )
    parser.add_argument(
        "--poll-seconds",
        type=float,
        default=0,
        help="Polling interval in seconds (e.g. 1).",
    )
    parser.add_argument(
        "--duration-seconds",
        type=int,
        default=0,
        help="Stop polling after N seconds (0 = infinite).",
    )
    parser.add_argument(
        "--append", action="store_true", help="Append mode for polling exports."
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output = Path(args.output)

    settings = Settings()
    settings.validate()
    client = PolymarketClient(settings.polymarket)

    if args.poll_seconds <= 0:
        trades = _fetch_trades(client, args)
        if args.format == "json":
            _write_json(output, trades)
        else:
            _write_csv(output, trades)
        print(f"Exported {len(trades)} trades to {output}")
        return

    seen: set[str] = set()
    total_written = 0
    start_time = time.time()
    collected: list[dict[str, Any]] = []

    print(
        f"Polling trades every {args.poll_seconds}s. "
        f"Output: {output} ({args.format}, append={args.append})"
    )
    if args.duration_seconds > 0:
        print(f"Will stop after {args.duration_seconds}s")

    try:
        while True:
            trades = _fetch_trades(client, args)

            new_trades: list[dict[str, Any]] = []
            for trade in trades:
                key = _trade_key(trade)
                if key in seen:
                    continue
                seen.add(key)
                new_trades.append(trade)

            if new_trades:
                if args.format == "json":
                    if args.append and output.exists():
                        with output.open("r", encoding="utf-8") as f:
                            existing = json.load(f)
                        if not isinstance(existing, list):
                            existing = []
                        existing.extend(new_trades)
                        _write_json(output, existing)
                    else:
                        collected.extend(new_trades)
                        _write_json(output, collected)
                else:
                    if args.append:
                        _write_csv(output, new_trades, append=True)
                    else:
                        collected.extend(new_trades)
                        _write_csv(output, collected, append=False)

                total_written += len(new_trades)
                print(
                    f"+ {len(new_trades)} new trades (total written: {total_written})"
                )

            if (
                args.duration_seconds > 0
                and (time.time() - start_time) >= args.duration_seconds
            ):
                break

            time.sleep(args.poll_seconds)

    except KeyboardInterrupt:
        pass

    print(f"Finished. Total written: {total_written}. File: {output}")


if __name__ == "__main__":
    main()
