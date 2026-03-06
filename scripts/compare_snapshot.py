#!/usr/bin/env python3
"""
Compare two bot performance snapshots to measure impact of changes.

Usage:
  # Generate a new snapshot and compare with baseline:
  python3 scripts/compare_snapshot.py

  # Save a new snapshot without comparing:
  python3 scripts/compare_snapshot.py --save

  # Compare two specific files:
  python3 scripts/compare_snapshot.py --before backtest_output/snapshot_baseline.json --after backtest_output/snapshot_after.json
"""

import argparse
import csv
import json
import os
import sys
from datetime import datetime, timezone
from glob import glob


def build_snapshot(label: str, note: str = "") -> dict:
    files = sorted(glob("backtest_output/bot_orders_*.csv"))
    if not files:
        print("ERROR: No bot_orders_*.csv files found in backtest_output/")
        sys.exit(1)

    rows = []
    for f in files:
        with open(f) as fh:
            rows.extend(list(csv.DictReader(fh)))

    def asf(v):
        try:
            return float(v)
        except Exception:
            return 0.0

    placed   = [r for r in rows if r["status"].lower() == "placed"]
    nofill   = [r for r in rows if r["status"].lower() == "no_fill"]
    failed   = [r for r in rows if r["status"].lower() == "failed"]
    resolved = [r for r in rows if r.get("resolution_status", "").lower() == "resolved"]
    wins     = [r for r in resolved if str(r.get("won", "")).strip() == "1"]

    lat_vals = sorted(
        asf(r["fill_latency_ms"])
        for r in placed
        if asf(r.get("fill_latency_ms", 0)) > 0
    )
    avg_lat = sum(lat_vals) / len(lat_vals) if lat_vals else 0
    p50_lat = lat_vals[len(lat_vals) // 2] if lat_vals else 0
    p95_lat = lat_vals[int(len(lat_vals) * 0.95)] if lat_vals else 0

    avg_edge_placed = (
        sum(asf(r["edge_pct"]) for r in placed) / len(placed) if placed else 0
    )
    avg_edge_nofill = (
        sum(asf(r["edge_pct"]) for r in nofill) / len(nofill) if nofill else 0
    )

    stake_vals = [
        asf(r["filled_notional_usd_real"])
        if asf(r.get("filled_notional_usd_real", 0)) > 0
        else asf(r["notional_usd"])
        for r in placed
    ]
    avg_stake = sum(stake_vals) / len(stake_vals) if stake_vals else 0

    total_pnl = sum(asf(r.get("pnl_simulated", 0)) for r in resolved)

    return {
        "label": label,
        "snapshot_at": datetime.now(timezone.utc).isoformat(),
        "csv_files": len(files),
        "total_rows": len(rows),
        "placed": len(placed),
        "no_fill": len(nofill),
        "failed": len(failed),
        "no_fill_rate_pct": round(len(nofill) / len(rows) * 100, 2) if rows else 0,
        "fail_rate_pct": round((len(nofill) + len(failed)) / len(rows) * 100, 2) if rows else 0,
        "resolved": len(resolved),
        "wins": len(wins),
        "win_rate_pct": round(len(wins) / len(resolved) * 100, 2) if resolved else 0,
        "total_pnl_sim_usd": round(total_pnl, 2),
        "avg_pnl_per_resolved_usd": round(total_pnl / len(resolved), 4) if resolved else 0,
        "avg_latency_ms": round(avg_lat, 1),
        "p50_latency_ms": round(p50_lat, 1),
        "p95_latency_ms": round(p95_lat, 1),
        "n_latency_samples": len(lat_vals),
        "avg_edge_placed_pct": round(avg_edge_placed, 4),
        "avg_edge_nofill_pct": round(avg_edge_nofill, 4),
        "avg_stake_usd": round(avg_stake, 4),
        "note": note,
    }


def fmt_delta(before, after, key, fmt=".2f", invert=False):
    """Return colored delta string. invert=True means lower is better."""
    a, b = before.get(key, 0), after.get(key, 0)
    delta = b - a
    if delta == 0:
        sign = "  "
        color = ""
        reset = ""
    else:
        better = delta < 0 if invert else delta > 0
        color = "\033[92m" if better else "\033[91m"  # green / red
        reset = "\033[0m"
        sign = "▲" if delta > 0 else "▼"
    return f"{b:{fmt}}  {color}{sign}{abs(delta):{fmt}}{reset}"


def compare(before: dict, after: dict):
    print()
    print("=" * 62)
    print(f"  SNAPSHOT COMPARISON")
    print(f"  Before : {before.get('snapshot_at', '?')}  [{before.get('label', '?')}]")
    print(f"  After  : {after.get('snapshot_at', '?')}  [{after.get('label', '?')}]")
    print("=" * 62)

    rows = [
        ("VOLUME", None),
        ("Total rows",        "total_rows",          "d",    False),
        ("Placed",            "placed",               "d",    False),
        ("No-fill",           "no_fill",              "d",    True),
        ("Failed",            "failed",               "d",    True),
        ("No-fill rate %",    "no_fill_rate_pct",     ".2f",  True),
        ("Fail rate %",       "fail_rate_pct",        ".2f",  True),
        ("", None),
        ("OUTCOME", None),
        ("Resolved",          "resolved",             "d",    False),
        ("Wins",              "wins",                 "d",    False),
        ("Win rate %",        "win_rate_pct",         ".2f",  False),
        ("Total PnL sim $",   "total_pnl_sim_usd",    ".2f",  False),
        ("Avg PnL/resolved $","avg_pnl_per_resolved_usd",".4f",False),
        ("", None),
        ("EXECUTION", None),
        ("Avg latency ms",    "avg_latency_ms",       ".1f",  True),
        ("P50 latency ms",    "p50_latency_ms",       ".1f",  True),
        ("P95 latency ms",    "p95_latency_ms",       ".1f",  True),
        ("Avg stake $",       "avg_stake_usd",        ".4f",  False),
        ("", None),
        ("EDGE", None),
        ("Avg edge placed %", "avg_edge_placed_pct",  ".4f",  False),
        ("Avg edge no_fill %","avg_edge_nofill_pct",  ".4f",  False),
    ]

    print(f"  {'Metric':<26} {'Before':>10}  {'After / Δ':>20}")
    print(f"  {'-'*26} {'-'*10}  {'-'*20}")

    for row in rows:
        if row[1] is None:
            if row[0]:
                print(f"\n  [{row[0]}]")
            else:
                print()
            continue
        label, key, fmt, invert = row
        bval = before.get(key, 0)
        print(f"  {label:<26} {format(bval, fmt):>10}  {fmt_delta(before, after, key, fmt, invert):>20}")

    print()
    print("  Notes:")
    print(f"    Before: {before.get('note', '')}")
    print(f"    After : {after.get('note', '')}")
    print("=" * 62)
    print()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--save", action="store_true", help="Save a new snapshot and compare with baseline")
    parser.add_argument("--before", default="backtest_output/snapshot_baseline.json")
    parser.add_argument("--after",  default="backtest_output/snapshot_after.json")
    parser.add_argument("--label",  default="after_no_fill_reduction")
    parser.add_argument("--note",   default="AFTER no_fill reduction (tolerance 0.03 + retry)")
    args = parser.parse_args()

    if args.save or not os.path.exists(args.after):
        print(f"Building snapshot → {args.after}")
        snap = build_snapshot(label=args.label, note=args.note)
        with open(args.after, "w") as f:
            json.dump(snap, f, indent=2)
        print(json.dumps(snap, indent=2))

    if not os.path.exists(args.before):
        print(f"No baseline found at {args.before}. Run with --save to create after snapshot only.")
        return

    with open(args.before) as f:
        before = json.load(f)
    with open(args.after) as f:
        after = json.load(f)

    compare(before, after)


if __name__ == "__main__":
    main()
