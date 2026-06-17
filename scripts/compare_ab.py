"""
A/B comparison script — V1 (baseline) vs V2 (smoothing + calibration)

Metrics per instance:
  - Bets placed / resolved
  - Win Rate
  - PnL total and per bet
  - MAE  (quant_prob vs won — individual level)
  - MAG  (Mean Abs Gap by 0.1 bucket)
  - Brier Score
  - Edge accuracy (predicted edge vs realized edge)

Usage:
    python3 scripts/compare_ab.py
    python3 scripts/compare_ab.py --days 7
    python3 scripts/compare_ab.py --v1-dir backtest_output --v2-dir backtest_output_v2
    python3 scripts/compare_ab.py --save docs/images/ab_comparison.png
"""

import argparse
import csv
import glob
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone, timedelta

# ── CLI ──────────────────────────────────────────────────────────────────────
parser = argparse.ArgumentParser(description="A/B test comparison V1 vs V2")
parser.add_argument("--v1-dir", default="backtest_output", help="V1 output dir")
parser.add_argument("--v2-dir", default="backtest_output_v2", help="V2 output dir")
parser.add_argument("--days", type=int, default=0,
                    help="Only include orders from last N days (0 = all)")
parser.add_argument("--save", default="", help="Save chart to this PNG path")
parser.add_argument("--no-chart", action="store_true", help="Skip chart generation")
args = parser.parse_args()


# ── Load orders ──────────────────────────────────────────────────────────────
def load_orders(directory: str, days: int = 0) -> list[dict]:
    """Load from paper_trades.csv (paper mode) or bot_orders_*.csv (live mode)."""
    cutoff = None
    if days > 0:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    # Try paper_trades.csv first
    paper_path = os.path.join(directory, "paper_trades.csv")
    if os.path.exists(paper_path):
        return _load_paper_trades(paper_path, cutoff)

    # Fall back to bot_orders_*.csv (live mode)
    return _load_bot_orders(directory, cutoff)


def _load_paper_trades(path: str, cutoff) -> list[dict]:
    rows = []
    try:
        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("status") != "resolved":
                    continue
                side = row.get("side_taken", "").strip().lower()
                outcome = row.get("event_outcome_real", "").strip().lower()
                if not side or not outcome:
                    continue
                prob_up = row.get("prob_up", "").strip()
                if not prob_up or prob_up in ("None", ""):
                    continue
                try:
                    pu = float(prob_up)
                    # quant_prob for the side taken.
                    # prob_up and prob_down are calibrated independently so
                    # they don't sum to 1. Use prob_down directly when available
                    # (new schema), or QuantumEdge+ask as fallback (old data).
                    prob_down_raw = row.get("prob_down", "").strip()
                    quantum_edge = row.get("QuantumEdge", "").strip()
                    ask_at_dec = row.get("best_ask_at_decision", "").strip()
                    if side == "up":
                        qp = pu
                    elif prob_down_raw and prob_down_raw not in ("None", ""):
                        qp = float(prob_down_raw)
                    elif quantum_edge and ask_at_dec:
                        qp = float(quantum_edge) + float(ask_at_dec)
                    else:
                        qp = 1.0 - pu  # last resort
                    row["_won"] = (side == outcome)
                    row["_qp"] = qp
                    row["_notional"] = float(row.get("stake_usd") or 0)
                    row["_fill_price"] = float(row.get("fill_price_real") or
                                               row.get("best_ask_at_decision") or 0)
                    row["_pnl"] = float(row.get("pnl_sim_adjusted") or
                                        row.get("pnl_simulated") or 0)
                    row["_pnl_precomputed"] = True
                    placed = row.get("decision_time", "")
                    if placed:
                        dt = datetime.fromisoformat(placed.replace("Z", "+00:00"))
                        if cutoff and dt < cutoff:
                            continue
                        row["_placed_dt"] = dt
                    else:
                        row["_placed_dt"] = None
                    rows.append(row)
                except (ValueError, TypeError):
                    continue
    except Exception as e:
        print(f"  Warning: {path}: {e}", file=sys.stderr)
    return rows


def _load_bot_orders(directory: str, cutoff) -> list[dict]:
    rows = []
    for path in sorted(glob.glob(os.path.join(directory, "bot_orders_*.csv"))):
        try:
            with open(path, newline="", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    if row.get("status") != "placed":
                        continue
                    won = row.get("won", "").strip().lower()
                    if won not in ("true", "false", "1", "0"):
                        continue
                    qp = row.get("quant_prob", "").strip()
                    if not qp or qp in ("None", ""):
                        continue
                    try:
                        row["_won"] = won in ("true", "1")
                        row["_qp"] = float(qp)
                        notional = row.get("filled_notional_usd_real") or row.get("notional_usd") or "0"
                        row["_notional"] = float(notional or 0)
                        fill = row.get("fill_price_real") or row.get("price") or "0"
                        row["_fill_price"] = float(fill or 0)
                        placed = row.get("placed_at_utc", "")
                        if placed:
                            dt = datetime.fromisoformat(placed.replace("Z", "+00:00"))
                            if cutoff and dt < cutoff:
                                continue
                            row["_placed_dt"] = dt
                        else:
                            row["_placed_dt"] = None
                        rows.append(row)
                    except (ValueError, TypeError):
                        continue
        except Exception as e:
            print(f"  Warning: {path}: {e}", file=sys.stderr)
    return rows


# ── Metrics ──────────────────────────────────────────────────────────────────
def compute_metrics(rows: list[dict], label: str) -> dict:
    if not rows:
        return {"label": label, "n": 0}

    n = len(rows)
    wins = sum(1 for r in rows if r["_won"])
    wr = wins / n

    # PnL: use pre-computed value from paper_trades.csv when available,
    # otherwise calculate from fill_price (live mode)
    pnl_total = 0.0
    for r in rows:
        if r.get("_pnl_precomputed"):
            pnl_total += r["_pnl"]
        else:
            notional = r["_notional"]
            if notional <= 0:
                notional = 1.0
            if r["_won"]:
                fill = r["_fill_price"]
                pnl = (notional / fill - notional) if fill > 0 else 0.0
            else:
                pnl = -notional
            r["_pnl"] = pnl
            pnl_total += pnl

    pnl_per_bet = pnl_total / n

    # MAE — individual level
    mae = sum(abs(r["_qp"] - float(r["_won"])) for r in rows) / n

    # Brier Score
    brier = sum((r["_qp"] - float(r["_won"])) ** 2 for r in rows) / n

    # MAG — by 0.1 bucket
    buckets = defaultdict(list)
    for r in rows:
        b = round(r["_qp"] * 10) / 10
        buckets[b].append(r)

    mag_gaps = []
    bucket_details = {}
    for b in sorted(buckets):
        br = buckets[b]
        if len(br) < 3:
            continue
        pred = sum(r["_qp"] for r in br) / len(br)
        actual_wr = sum(r["_won"] for r in br) / len(br)
        gap = actual_wr - pred
        mag_gaps.append(abs(gap))
        bucket_details[b] = {"pred": pred, "wr": actual_wr, "gap": gap, "n": len(br)}

    mag = sum(mag_gaps) / len(mag_gaps) if mag_gaps else None

    # Avg edge predicted vs realized
    avg_pred_edge = sum(r["_qp"] - r["_fill_price"] for r in rows if r["_fill_price"] > 0) / n
    avg_real_edge = wr - (sum(r["_fill_price"] for r in rows if r["_fill_price"] > 0) / n)

    return {
        "label": label,
        "n": n,
        "wins": wins,
        "wr": wr,
        "pnl_total": pnl_total,
        "pnl_per_bet": pnl_per_bet,
        "mae": mae,
        "brier": brier,
        "mag": mag,
        "avg_pred_edge": avg_pred_edge,
        "avg_real_edge": avg_real_edge,
        "bucket_details": bucket_details,
        "rows": rows,
    }


# ── Print report ─────────────────────────────────────────────────────────────
def print_report(m1: dict, m2: dict):
    SEP = "═" * 62

    def delta(v1, v2, higher_better=True, pct=False):
        if v1 is None or v2 is None:
            return ""
        diff = v2 - v1
        sym = "▲" if (diff > 0) == higher_better else "▼"
        if pct:
            return f"  {sym} {diff*100:+.2f}pp"
        return f"  {sym} {diff:+.4f}"

    print(f"\n{SEP}")
    print(f"  A/B Test Report — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    if args.days:
        print(f"  Window: last {args.days} days")
    print(SEP)
    print(f"  {'Métrica':<30} {'V1 (baseline)':>14} {'V2 (smooth+cal)':>16} {'Δ':>10}")
    print(f"  {'─'*30} {'─'*14} {'─'*16} {'─'*10}")

    def row(label, key, fmt=".4f", higher_better=True, pct=False, multiply=100):
        v1 = m1.get(key)
        v2 = m2.get(key)
        if v1 is None and v2 is None:
            return
        v1s = f"{v1*multiply:{fmt}}" if v1 is not None else "—"
        v2s = f"{v2*multiply:{fmt}}" if v2 is not None else "—"
        d = delta(v1, v2, higher_better, pct) if (v1 is not None and v2 is not None) else ""
        print(f"  {label:<30} {v1s:>14} {v2s:>16} {d:>10}")

    print(f"  {'Bets resueltos':<30} {m1.get('n',0):>14} {m2.get('n',0):>16}")
    row("Win Rate (%)",       "wr",       ".2f", True,  True,  100)
    row("PnL total ($)",      "pnl_total",".2f", True,  False, 1)
    row("PnL por bet ($)",    "pnl_per_bet",".4f",True, False, 1)
    print(f"  {'─'*30} {'─'*14} {'─'*16} {'─'*10}")
    row("MAE  (↓ mejor)",     "mae",      ".4f", False, False, 1)
    row("Brier Score (↓ mejor)","brier",  ".4f", False, False, 1)
    row("MAG  (↓ mejor)",     "mag",      ".4f", False, False, 1)
    print(f"  {'─'*30} {'─'*14} {'─'*16} {'─'*10}")
    row("Edge predicho avg",  "avg_pred_edge",".4f",True,False,1)
    row("Edge realizado avg", "avg_real_edge",".4f",True,False,1)
    print(SEP)

    # Bucket detail
    all_buckets = sorted(set(list(m1.get("bucket_details", {}).keys()) +
                              list(m2.get("bucket_details", {}).keys())))
    if all_buckets:
        print(f"\n  Detalle por bucket (quant_prob)")
        print(f"  {'bucket':>7} │ {'V1 pred':>8} {'V1 WR':>7} {'V1 gap':>7} {'n':>5} │"
              f" {'V2 pred':>8} {'V2 WR':>7} {'V2 gap':>7} {'n':>5}")
        print(f"  {'─'*7}-+-{'─'*8}-{'─'*7}-{'─'*7}-{'─'*5}-+-{'─'*8}-{'─'*7}-{'─'*7}-{'─'*5}")
        for b in all_buckets:
            d1 = m1.get("bucket_details", {}).get(b)
            d2 = m2.get("bucket_details", {}).get(b)
            s1 = f"{d1['pred']:>8.3f} {d1['wr']:>7.3f} {d1['gap']:>+7.3f} {d1['n']:>5}" if d1 else f"{'—':>8} {'—':>7} {'—':>7} {'—':>5}"
            s2 = f"{d2['pred']:>8.3f} {d2['wr']:>7.3f} {d2['gap']:>+7.3f} {d2['n']:>5}" if d2 else f"{'—':>8} {'—':>7} {'—':>7} {'—':>5}"
            print(f"  {b:>7.1f} │ {s1} │ {s2}")
    print()


# ── Chart ────────────────────────────────────────────────────────────────────
def make_chart(m1: dict, m2: dict, save_path: str = ""):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.gridspec as gridspec
        import numpy as np
    except ImportError:
        print("matplotlib not available — skipping chart")
        return

    plt.rcParams.update({
        "figure.facecolor": "#1a1a2e", "axes.facecolor": "#16213e",
        "axes.edgecolor": "#444", "axes.labelcolor": "#ddd",
        "xtick.color": "#aaa", "ytick.color": "#aaa",
        "grid.color": "#333", "grid.linestyle": "--", "grid.alpha": 0.5,
        "text.color": "#eee", "font.family": "monospace",
    })

    fig = plt.figure(figsize=(15, 10))
    gs = gridspec.GridSpec(2, 3, figure=fig, hspace=0.38, wspace=0.32)

    C1, C2 = "#e74c3c", "#2ecc71"

    # ── 1. Equity curves ─────────────────────────────────────────────────────
    ax1 = fig.add_subplot(gs[0, :2])
    for m, color, label in [(m1, C1, "V1 baseline"), (m2, C2, "V2 smooth+cal")]:
        if not m.get("rows"):
            continue
        sorted_rows = sorted(m["rows"], key=lambda r: r.get("_placed_dt") or datetime.min.replace(tzinfo=timezone.utc))
        cumulative = [0.0]
        for r in sorted_rows:
            cumulative.append(cumulative[-1] + r.get("_pnl", 0))
        ax1.plot(cumulative, color=color, lw=2, label=f"{label} (n={m['n']})")

    ax1.axhline(0, color="#555", lw=1)
    ax1.set_title("Equity Curve — PnL acumulado ($)", fontsize=11)
    ax1.set_xlabel("Orden #")
    ax1.set_ylabel("PnL ($)")
    ax1.legend(framealpha=0.15, fontsize=9)
    ax1.grid(True)

    # ── 2. Win Rate bar ───────────────────────────────────────────────────────
    ax2 = fig.add_subplot(gs[0, 2])
    labels = ["V1\nbaseline", "V2\nsmooth+cal"]
    wrs = [m1.get("wr", 0) * 100, m2.get("wr", 0) * 100]
    colors = [C1, C2]
    bars = ax2.bar(labels, wrs, color=colors, alpha=0.8, width=0.5)
    ax2.axhline(50, color="#f39c12", ls="--", lw=1.5, label="50% (break-even)")
    for bar, val in zip(bars, wrs):
        ax2.text(bar.get_x() + bar.get_width() / 2, val + 0.5,
                 f"{val:.1f}%", ha="center", fontsize=11, color="white")
    ax2.set_ylim(0, 100)
    ax2.set_title("Win Rate (%)", fontsize=11)
    ax2.legend(framealpha=0.15, fontsize=9)
    ax2.grid(True, axis="y")

    # ── 3. Calibration buckets V1 ────────────────────────────────────────────
    ax3 = fig.add_subplot(gs[1, 0])
    _plot_reliability(ax3, m1, C1, "V1 baseline — Reliability")

    # ── 4. Calibration buckets V2 ────────────────────────────────────────────
    ax4 = fig.add_subplot(gs[1, 1])
    _plot_reliability(ax4, m2, C2, "V2 smooth+cal — Reliability")

    # ── 5. Metrics bar chart ──────────────────────────────────────────────────
    ax5 = fig.add_subplot(gs[1, 2])
    metrics = ["MAE", "Brier", "MAG"]
    v1_vals = [m1.get("mae", 0), m1.get("brier", 0), m1.get("mag") or 0]
    v2_vals = [m2.get("mae", 0), m2.get("brier", 0), m2.get("mag") or 0]
    x = np.arange(len(metrics))
    w = 0.35
    ax5.bar(x - w/2, v1_vals, w, color=C1, alpha=0.8, label="V1")
    ax5.bar(x + w/2, v2_vals, w, color=C2, alpha=0.8, label="V2")
    ax5.set_xticks(x)
    ax5.set_xticklabels(metrics)
    ax5.set_title("Métricas calibración (↓ mejor)", fontsize=11)
    ax5.legend(framealpha=0.15, fontsize=9)
    ax5.grid(True, axis="y")

    fig.suptitle(
        f"A/B Test: V1 (raw) vs V2 (isotonic smooth + calibración)\n"
        f"{datetime.now(timezone.utc).strftime('%Y-%m-%d')} — "
        f"V1: {m1.get('n',0)} bets  |  V2: {m2.get('n',0)} bets",
        fontsize=13, y=1.01,
    )

    out = save_path or "docs/images/ab_comparison.png"
    os.makedirs(os.path.dirname(out) if os.path.dirname(out) else ".", exist_ok=True)
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Chart saved → {out}")


def _plot_reliability(ax, m: dict, color: str, title: str):
    import numpy as np
    bd = m.get("bucket_details", {})
    if not bd:
        ax.set_title(title + "\n(sin datos)", fontsize=10)
        return
    xs = sorted(bd.keys())
    preds = [bd[x]["pred"] for x in xs]
    wrs   = [bd[x]["wr"]   for x in xs]
    ns    = [bd[x]["n"]    for x in xs]
    ax.plot([0.4, 1.0], [0.4, 1.0], "--", color="#6c757d", lw=1.5, label="Perfecta")
    ax.scatter(preds, wrs, c=color, s=[n * 1.5 for n in ns], alpha=0.8, zorder=5)
    ax.plot(preds, wrs, color=color, lw=1.5, alpha=0.7)
    for x, y, n in zip(preds, wrs, ns):
        ax.annotate(f"n={n}", (x, y), textcoords="offset points",
                    xytext=(4, 4), fontsize=7, color="#aaa")
    mae_val = m.get("mae", 0)
    ax.text(0.97, 0.05, f"MAE={mae_val:.4f}", transform=ax.transAxes,
            ha="right", fontsize=9, color=color,
            bbox=dict(boxstyle="round", facecolor="#0f3460", alpha=0.8))
    ax.set_xlim(0.40, 1.0)
    ax.set_ylim(0.35, 1.0)
    ax.set_xlabel("Prob predicha", fontsize=9)
    ax.set_ylabel("WR real", fontsize=9)
    ax.set_title(title, fontsize=10)
    ax.legend(fontsize=8, framealpha=0.15)
    ax.grid(True)


# ── Main ─────────────────────────────────────────────────────────────────────
print(f"\nLoading V1 from {args.v1_dir}...")
rows_v1 = load_orders(args.v1_dir, args.days)
print(f"  {len(rows_v1)} resolved orders")

print(f"Loading V2 from {args.v2_dir}...")
rows_v2 = load_orders(args.v2_dir, args.days)
print(f"  {len(rows_v2)} resolved orders")

if not rows_v1 and not rows_v2:
    print("\nNo resolved orders found in either directory.", file=sys.stderr)
    sys.exit(1)

m1 = compute_metrics(rows_v1, "V1 baseline")
m2 = compute_metrics(rows_v2, "V2 smooth+cal")

print_report(m1, m2)

if not args.no_chart:
    make_chart(m1, m2, args.save)
