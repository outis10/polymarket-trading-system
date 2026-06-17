"""
Model calibration script — issue #4 (v1.3 Model Recalibration)

Loads resolved bot_orders, fits isotonic regression on quant_prob → actual WR,
and exports a calibration table to config/prob_calibration.json.

Usage:
    python3 scripts/calibrate_model.py
    python3 scripts/calibrate_model.py --output-dir backtest_output_v2
    python3 scripts/calibrate_model.py --min-samples 20 --dry-run
"""

import argparse
import csv
import json
import os
import sys
from datetime import datetime, timezone

import numpy as np
from sklearn.isotonic import IsotonicRegression


def load_resolved_orders(output_dirs: list[str]) -> list[dict]:
    """Load from bot_orders_*.csv (live) or paper_trades.csv (paper mode, raw probs only)."""
    import glob
    rows = []
    for d in output_dirs:
        # paper_trades.csv takes priority — use it if present
        paper_path = os.path.join(d, "paper_trades.csv")
        if os.path.exists(paper_path):
            loaded = _load_paper_trades(paper_path, d)
            rows.extend(loaded)
            print(f"  {d}/paper_trades.csv → {len(loaded)} rows")
            continue
        # Fallback: live mode bot_orders_*.csv
        for path in sorted(glob.glob(os.path.join(d, "bot_orders_*.csv"))):
            loaded = _load_bot_orders_csv(path)
            rows.extend(loaded)
            print(f"  {path} → {len(loaded)} rows")
    return rows


def _load_paper_trades(path: str, directory: str) -> list[dict]:
    rows = []
    try:
        with open(path, newline="") as f:
            for row in csv.DictReader(f):
                if row.get("status") != "resolved":
                    continue
                side = row.get("side_taken", "").strip().lower()
                outcome = row.get("event_outcome_real", "").strip().lower()
                if not side or not outcome:
                    continue
                # For DOWN bets: use prob_down if available, else QuantumEdge+ask.
                # Never use 1-prob_up: calibration is applied independently per side.
                prob_up_raw = row.get("prob_up", "").strip()
                prob_down_raw = row.get("prob_down", "").strip()
                quantum_edge = row.get("QuantumEdge", "").strip()
                ask = row.get("best_ask_at_decision", "").strip()
                if not prob_up_raw or prob_up_raw in ("None", ""):
                    continue
                try:
                    if side == "up":
                        qp = float(prob_up_raw)
                    elif prob_down_raw and prob_down_raw not in ("None", ""):
                        qp = float(prob_down_raw)
                    elif quantum_edge and ask:
                        qp = float(quantum_edge) + float(ask)
                    else:
                        continue  # can't determine quant_prob for this side
                    row["_won"] = (side == outcome)
                    row["_quant_prob"] = qp
                    row["_diff"] = float(row.get("diff_vs_ptb_at_decision") or 0)
                    row["_slot"] = int(float(row.get("slot") or 0))
                    rows.append(row)
                except (ValueError, TypeError):
                    continue
    except Exception as e:
        print(f"  Warning: could not read {path}: {e}", file=sys.stderr)
    return rows


def _load_bot_orders_csv(path: str) -> list[dict]:
    rows = []
    try:
        with open(path, newline="") as f:
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
                    row["_quant_prob"] = float(qp)
                    row["_diff"] = float(row.get("diff_vs_ptb_at_send") or 0)
                    row["_slot"] = int(float(row.get("slot") or 0))
                    rows.append(row)
                except (ValueError, TypeError):
                    continue
    except Exception as e:
        print(f"  Warning: could not read {path}: {e}", file=sys.stderr)
    return rows


def calibration_report(rows: list[dict], prob_key="_quant_prob", label="raw") -> dict:
    from collections import defaultdict
    buckets = defaultdict(list)
    for r in rows:
        b = round(r[prob_key] * 10) / 10
        buckets[b].append(r["_won"])

    print(f"\n{'─'*55}")
    print(f"  Calibration report ({label}) — {len(rows)} samples")
    print(f"{'─'*55}")
    print(f"  {'bucket':>7} | {'predicted':>9} | {'actual WR':>9} | {'gap':>7} | {'n':>5}")
    print(f"  {'─'*7}-+-{'─'*9}-+-{'─'*9}-+-{'─'*7}-+-{'─'*5}")

    results = {}
    for b in sorted(buckets):
        wins = buckets[b]
        n = len(wins)
        if n < 3:
            continue
        pred = sum(r[prob_key] for r in rows if round(r[prob_key] * 10) / 10 == b) / n
        wr = sum(wins) / n
        gap = wr - pred
        marker = " ✓" if abs(gap) < 0.05 else " ✗"
        print(f"  {b:>7.1f} | {pred:>9.3f} | {wr:>9.3f} | {gap:>+7.3f}{marker} | {n:>5}")
        results[b] = {"predicted": round(pred, 4), "actual_wr": round(wr, 4), "gap": round(gap, 4), "n": n}

    avg_gap = sum(abs(v["gap"]) for v in results.values()) / len(results) if results else 0
    print(f"\n  Mean absolute gap: {avg_gap:.4f}")
    return results


def fit_calibration(rows: list[dict]) -> tuple[np.ndarray, np.ndarray]:
    X = np.array([r["_quant_prob"] for r in rows])
    y = np.array([float(r["_won"]) for r in rows])

    ir = IsotonicRegression(out_of_bounds="clip", increasing=True)
    ir.fit(X, y)

    # Sample calibration curve at fine resolution
    x_eval = np.linspace(0.01, 0.99, 99)
    y_cal = ir.predict(x_eval)

    return x_eval, y_cal, ir


def apply_calibration(rows: list[dict], ir) -> list[dict]:
    X = np.array([r["_quant_prob"] for r in rows])
    calibrated = ir.predict(X)
    for r, c in zip(rows, calibrated):
        r["_calibrated_prob"] = float(c)
    return rows


def main():
    parser = argparse.ArgumentParser(description="Calibrate quant model probabilities")
    parser.add_argument(
        "--output-dir",
        nargs="+",
        default=["backtest_output"],
        help="Directories to scan for bot_orders_*.csv or paper_trades.csv. "
             "Only pass dirs with RAW (uncalibrated) probs — do not include V2 "
             "if prob_calibration_enabled=true there.",
    )
    parser.add_argument(
        "--config-dir",
        default="config",
        help="Directory to write prob_calibration.json",
    )
    parser.add_argument(
        "--min-samples",
        type=int,
        default=50,
        help="Minimum resolved orders required to generate calibration",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print report but don't write JSON",
    )
    args = parser.parse_args()

    print("Loading resolved orders...")
    existing_dirs = [d for d in args.output_dir if os.path.isdir(d)]
    if not existing_dirs:
        print(f"No output directories found: {args.output_dir}", file=sys.stderr)
        sys.exit(1)

    rows = load_resolved_orders(existing_dirs)
    print(f"Found {len(rows)} resolved placed orders across: {existing_dirs}")

    if len(rows) < args.min_samples:
        print(
            f"\nInsufficient data: {len(rows)} samples < {args.min_samples} minimum. "
            "Collect more resolved orders before calibrating.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Before calibration
    calibration_report(rows, prob_key="_quant_prob", label="before calibration")

    # Fit isotonic regression
    print("\nFitting isotonic regression...")
    x_eval, y_cal, ir = fit_calibration(rows)

    # Apply and report after
    rows = apply_calibration(rows, ir)
    calibration_report(rows, prob_key="_calibrated_prob", label="after calibration")

    # Build calibration points for JSON
    calibration_points = [
        {"raw_prob": round(float(x), 4), "calibrated_prob": round(float(y), 4)}
        for x, y in zip(x_eval, y_cal)
    ]

    # Stats summary
    raw_gaps = []
    cal_gaps = []
    from collections import defaultdict
    raw_buckets = defaultdict(list)
    cal_buckets = defaultdict(list)
    for r in rows:
        b = round(r["_quant_prob"] * 10) / 10
        raw_buckets[b].append((r["_quant_prob"], r["_won"]))
        cal_buckets[b].append((r["_calibrated_prob"], r["_won"]))

    for b in sorted(raw_buckets):
        if len(raw_buckets[b]) < 3:
            continue
        raw_pred = sum(x for x, _ in raw_buckets[b]) / len(raw_buckets[b])
        raw_wr = sum(w for _, w in raw_buckets[b]) / len(raw_buckets[b])
        cal_pred = sum(x for x, _ in cal_buckets[b]) / len(cal_buckets[b])
        cal_wr = sum(w for _, w in cal_buckets[b]) / len(cal_buckets[b])
        raw_gaps.append(abs(raw_wr - raw_pred))
        cal_gaps.append(abs(cal_wr - cal_pred))

    summary = {
        "mean_abs_gap_before": round(sum(raw_gaps) / len(raw_gaps), 4) if raw_gaps else None,
        "mean_abs_gap_after": round(sum(cal_gaps) / len(cal_gaps), 4) if cal_gaps else None,
        "improvement_pct": round(
            100 * (1 - sum(cal_gaps) / sum(raw_gaps)), 1
        ) if raw_gaps and sum(raw_gaps) > 0 else None,
    }

    print(f"\n{'─'*55}")
    print(f"  Summary")
    print(f"{'─'*55}")
    print(f"  Mean abs gap before: {summary['mean_abs_gap_before']:.4f}")
    print(f"  Mean abs gap after:  {summary['mean_abs_gap_after']:.4f}")
    print(f"  Improvement:         {summary['improvement_pct']:.1f}%")

    output = {
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "n_samples": len(rows),
        "source_dirs": existing_dirs,
        "method": "isotonic_regression",
        "summary": summary,
        "calibration_points": calibration_points,
    }

    if args.dry_run:
        print("\n[dry-run] Skipping write to JSON.")
        return

    os.makedirs(args.config_dir, exist_ok=True)
    out_path = os.path.join(args.config_dir, "prob_calibration.json")
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\n  Written → {out_path}")
    print(f"  {len(calibration_points)} calibration points")


if __name__ == "__main__":
    main()
