#!/usr/bin/env python3
"""
Contrarian / upset betting analysis.

Simulates betting $1 on the OPPOSITE side of each bot order that LOST,
measuring whether those contrarian bets would have been +EV.

Usage:
  python3 scripts/analyze_contrarian_ev.py
  python3 scripts/analyze_contrarian_ev.py --slot-max 5
  python3 scripts/analyze_contrarian_ev.py --hours-pst 8 9 10
  python3 scripts/analyze_contrarian_ev.py --opp-ask-max 0.35

Key concept:
  When the bot loses, the opposite side won.
  opp_ask ≈ 1 - our_ask  (binary market approximation)
  payout  = $1 / opp_ask
  EV > $1.00 per bet → strategy is profitable
"""

import argparse
import csv
from collections import defaultdict
from datetime import datetime, timedelta
from glob import glob

PST = timedelta(hours=-8)


def asf(v):
    try:
        return float(v)
    except Exception:
        return 0.0


def get_pst_hour(r):
    ts = r.get("placed_at_utc", "")
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return (dt + PST).hour
    except Exception:
        return -1


def load_resolved():
    rows = []
    for f in sorted(glob("backtest_output/bot_orders_*.csv")):
        with open(f) as fh:
            rows.extend(list(csv.DictReader(fh)))
    placed = [r for r in rows if r["status"].lower() == "placed"]
    return [r for r in placed if r.get("resolution_status", "").lower() == "resolved"]


def build_upsets(resolved):
    losses = [r for r in resolved if str(r.get("won", "")).strip() != "1"]
    results = []
    for r in losses:
        our_ask = asf(r.get("ask_price") or r.get("price", 0))
        opp_ask = round(1 - our_ask, 4)
        payout = round(1.0 / opp_ask, 4) if opp_ask > 0 else 0
        profit = round(payout - 1.0, 4)
        results.append({
            "r": r,
            "our_ask": our_ask,
            "opp_ask": opp_ask,
            "payout": payout,
            "profit": profit,
            "diff": asf(r.get("diff_vs_ptb_at_send", 0)),
            "slot": int(asf(r.get("slot_in_window", r.get("slot", 0)))),
            "hour_pst": get_pst_hour(r),
        })
    return results


def ev_report(label, subset, total_resolved):
    if not subset:
        print(f"── {label} ── (sin datos)\n")
        return
    n = len(subset)
    cost = float(n)
    gross = sum(x["payout"] for x in subset)
    net = gross - cost
    avg_opp = sum(x["opp_ask"] for x in subset) / n

    print(f"── {label} ──")
    print(f"  Upsets (contrario ganó)  : {n}")
    print(f"  Upset rate               : {n/total_resolved*100:.1f}% del total resolved")
    print(f"  Avg ask contrario        : {avg_opp:.3f}  ({avg_opp*100:.1f}¢)")
    for thr in [0.20, 0.25, 0.30, 0.35]:
        cnt = sum(1 for x in subset if x["opp_ask"] < thr)
        mult = round(1/thr, 1)
        print(f"  Opp ask < {thr:.0%}           : {cnt:3d} casos  (payout > {mult}x)")
    print(f"  Costo total ($1 c/u)     : ${cost:.0f}")
    print(f"  Retorno bruto            : ${gross:.2f}")
    print(f"  Retorno neto             : ${net:.2f}")
    print(f"  EV por $1 apostado       : ${net/cost:.3f}")
    print()


def distribution_report(upsets):
    print("── DISTRIBUCIÓN OPP_ASK ──")
    buckets = [
        (0.05, 0.10), (0.10, 0.15), (0.15, 0.20),
        (0.20, 0.25), (0.25, 0.30), (0.30, 0.35),
        (0.35, 0.40), (0.40, 0.50), (0.50, 1.00),
    ]
    for lo, hi in buckets:
        subset = [x for x in upsets if lo <= x["opp_ask"] < hi]
        if not subset:
            print(f"  [{lo:.2f},{hi:.2f})  n=  0")
            continue
        gross = sum(x["payout"] for x in subset)
        net = gross - len(subset)
        avg_p = gross / len(subset)
        print(f"  [{lo:.2f},{hi:.2f})  n={len(subset):3d}  "
              f"payout_avg=${avg_p:.2f}  neto_total=${net:.2f}")
    print()


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--slot-max", type=int, default=None,
                        help="Solo slots <= N (ej: 5 para early window)")
    parser.add_argument("--hours-pst", type=int, nargs="+", default=None,
                        help="Filtrar por horas PST (ej: 8 9 10)")
    parser.add_argument("--opp-ask-max", type=float, default=None,
                        help="Solo upsets con opp_ask < umbral (ej: 0.35)")
    parser.add_argument("--diff-max", type=float, default=None,
                        help="Solo upsets con |diff_vs_ptb| < umbral (ej: 50)")
    args = parser.parse_args()

    resolved = load_resolved()
    upsets   = build_upsets(resolved)
    total    = len(resolved)

    print(f"Total resolved: {total}  |  Upsets totales: {len(upsets)}\n")

    ev_report("TODOS LOS UPSETS", upsets, total)
    distribution_report(upsets)

    # Segmentos predefinidos (siempre se muestran)
    ev_report("SLOTS 1-5 (early window)",
              [x for x in upsets if 1 <= x["slot"] <= 5], total)

    ev_report("APERTURA NY (08-10h PST)",
              [x for x in upsets if 8 <= x["hour_pst"] <= 10], total)

    ev_report("DIFF DÉBIL |diff|<50",
              [x for x in upsets if abs(x["diff"]) < 50], total)

    ev_report("COMBINADO (slots 1-5 OR apertura NY)",
              [x for x in upsets if (1 <= x["slot"] <= 5) or (8 <= x["hour_pst"] <= 10)], total)

    # Segmento custom por args
    custom = upsets
    label_parts = []
    if args.slot_max:
        custom = [x for x in custom if x["slot"] <= args.slot_max]
        label_parts.append(f"slot<={args.slot_max}")
    if args.hours_pst:
        custom = [x for x in custom if x["hour_pst"] in args.hours_pst]
        label_parts.append(f"hours={args.hours_pst}")
    if args.opp_ask_max:
        custom = [x for x in custom if x["opp_ask"] < args.opp_ask_max]
        label_parts.append(f"opp_ask<{args.opp_ask_max}")
    if args.diff_max:
        custom = [x for x in custom if abs(x["diff"]) < args.diff_max]
        label_parts.append(f"|diff|<{args.diff_max}")
    if label_parts:
        ev_report("CUSTOM: " + " + ".join(label_parts), custom, total)


if __name__ == "__main__":
    main()
