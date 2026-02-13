#!/usr/bin/env python3
"""
Run timeframe matrix experiments using backtest_xlsx_template.py logic.

Setups:
- A1: 5m,15m,30m,60m
- A2: 5m,10m,15m,20m,30m,60m
- B: 2m..60m
- C: 3m,5m,8m,13m,21m,34m,55m
"""

from __future__ import annotations

import argparse
import itertools
from pathlib import Path

import numpy as np
import pandas as pd

from backtest_xlsx_template import run_backtest

SETUPS: dict[str, list[int]] = {
    "A1": [5, 15, 30, 60],
    "A2": [5, 10, 15, 20, 30, 60],
    "B": list(range(2, 61)),
    "C": [3, 5, 8, 13, 21, 34, 55],
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run timeframe matrix experiments over XLSX sheets."
    )
    parser.add_argument("--input", required=True, help="Input XLSX path.")
    parser.add_argument(
        "--setups",
        default="A1,A2,B,C",
        help="Comma-separated setup names to run (A1,A2,B,C).",
    )
    parser.add_argument(
        "--output-summary",
        default="backtest_output/timeframe_setups_summary.csv",
        help="CSV output for setup-level summary.",
    )
    parser.add_argument(
        "--output-detail",
        default="backtest_output/timeframe_setups_detail.csv",
        help="CSV output for per-interval detail.",
    )
    parser.add_argument(
        "--save-trades-dir",
        default="",
        help="Optional directory to export trade CSVs per setup/interval.",
    )
    parser.add_argument("--initial-capital", type=float, default=10_000.0)
    parser.add_argument("--fee-bps", type=float, default=5.0)
    parser.add_argument("--risk-per-trade", type=float, default=0.01)
    parser.add_argument("--prob-threshold", type=float, default=0.60)
    parser.add_argument("--exit-prob-threshold", type=float, default=0.50)
    parser.add_argument("--min-taker-ratio", type=float, default=0.55)
    parser.add_argument("--max-roi-entry", type=float, default=0.012)
    parser.add_argument("--sl-mult", type=float, default=0.8)
    parser.add_argument("--tp-mult", type=float, default=1.5)
    parser.add_argument("--vol-window", type=int, default=20)
    parser.add_argument(
        "--grid-search",
        action="store_true",
        help="Run cartesian product of parameter lists below.",
    )
    parser.add_argument("--grid-prob-thresholds", default="0.60,0.65,0.70")
    parser.add_argument("--grid-min-taker-ratios", default="0.55,0.60,0.65")
    parser.add_argument("--grid-max-roi-entries", default="0.008,0.010,0.012")
    parser.add_argument("--grid-sl-mults", default="0.60,0.80")
    parser.add_argument("--grid-tp-mults", default="1.5,2.0")
    parser.add_argument(
        "--max-combos",
        type=int,
        default=0,
        help="Optional cap of grid combinations (0 means all).",
    )
    parser.add_argument("--top", type=int, default=10, help="Rows to print per table.")
    return parser.parse_args()


def interval_to_sheet(minutes: int) -> str:
    return f"{minutes}min"


def requested_setups(raw: str) -> list[str]:
    names = [x.strip().upper() for x in raw.split(",") if x.strip()]
    invalid = [n for n in names if n not in SETUPS]
    if invalid:
        raise ValueError(f"Unsupported setup names: {invalid}. Valid: {list(SETUPS)}")
    if not names:
        raise ValueError("At least one setup must be provided.")
    return names


def finite_mean(values: pd.Series) -> float:
    arr = values.to_numpy(dtype=float)
    arr = arr[np.isfinite(arr)]
    return float(np.mean(arr)) if len(arr) else 0.0


def parse_float_list(raw: str, name: str) -> list[float]:
    values: list[float] = []
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        try:
            values.append(float(token))
        except ValueError as exc:
            raise ValueError(f"Invalid float in {name}: '{token}'") from exc
    if not values:
        raise ValueError(f"At least one value is required in {name}.")
    return values


def build_param_grid(args: argparse.Namespace) -> list[dict[str, float]]:
    if not args.grid_search:
        return [
            {
                "prob_threshold": args.prob_threshold,
                "min_taker_ratio": args.min_taker_ratio,
                "max_roi_entry": args.max_roi_entry,
                "sl_mult": args.sl_mult,
                "tp_mult": args.tp_mult,
            }
        ]

    prob_vals = parse_float_list(args.grid_prob_thresholds, "grid_prob_thresholds")
    taker_vals = parse_float_list(args.grid_min_taker_ratios, "grid_min_taker_ratios")
    roi_vals = parse_float_list(args.grid_max_roi_entries, "grid_max_roi_entries")
    sl_vals = parse_float_list(args.grid_sl_mults, "grid_sl_mults")
    tp_vals = parse_float_list(args.grid_tp_mults, "grid_tp_mults")

    combos: list[dict[str, float]] = []
    for prob, taker, roi, sl, tp in itertools.product(
        prob_vals, taker_vals, roi_vals, sl_vals, tp_vals
    ):
        combos.append(
            {
                "prob_threshold": prob,
                "min_taker_ratio": taker,
                "max_roi_entry": roi,
                "sl_mult": sl,
                "tp_mult": tp,
            }
        )
    if args.max_combos > 0:
        combos = combos[: args.max_combos]
    return combos


def combo_id(combo: dict[str, float]) -> str:
    return (
        f"p{combo['prob_threshold']:.3f}"
        f"_t{combo['min_taker_ratio']:.3f}"
        f"_r{combo['max_roi_entry']:.3f}"
        f"_sl{combo['sl_mult']:.2f}"
        f"_tp{combo['tp_mult']:.2f}"
    )


def build_bt_args(
    args: argparse.Namespace,
    sheet: str,
    trades_output: str,
    combo: dict[str, float],
) -> argparse.Namespace:
    return argparse.Namespace(
        input=args.input,
        sheet=sheet,
        initial_capital=args.initial_capital,
        fee_bps=args.fee_bps,
        risk_per_trade=args.risk_per_trade,
        prob_threshold=combo["prob_threshold"],
        exit_prob_threshold=args.exit_prob_threshold,
        min_taker_ratio=combo["min_taker_ratio"],
        max_roi_entry=combo["max_roi_entry"],
        sl_mult=combo["sl_mult"],
        tp_mult=combo["tp_mult"],
        vol_window=args.vol_window,
        trades_output=trades_output,
    )


def main() -> None:
    args = parse_args()
    setup_names = requested_setups(args.setups)
    combos = build_param_grid(args)

    xlsx = pd.ExcelFile(args.input)
    available = set(xlsx.sheet_names)
    print(f"Loaded XLSX: {args.input}")
    print(f"Available sheets: {', '.join(xlsx.sheet_names)}")
    print(f"Parameter combos: {len(combos)}")

    detail_rows: list[dict[str, float | int | str]] = []

    for idx, combo in enumerate(combos, start=1):
        cid = combo_id(combo)
        print(f"\nRunning combo {idx}/{len(combos)}: {cid}")
        for setup_name in setup_names:
            minutes_list = SETUPS[setup_name]
            print(f"  Setup {setup_name} ({len(minutes_list)} intervals)...")
            for minutes in minutes_list:
                sheet = interval_to_sheet(minutes)
                if sheet not in available:
                    print(f"    - skip {sheet}: sheet not found")
                    continue

                trades_output = ""
                if args.save_trades_dir:
                    out_dir = Path(args.save_trades_dir) / cid / setup_name
                    out_dir.mkdir(parents=True, exist_ok=True)
                    trades_output = str(out_dir / f"trades_{sheet}.csv")

                bt_args = build_bt_args(
                    args, sheet=sheet, trades_output=trades_output, combo=combo
                )
                try:
                    summary, trades_df = run_backtest(bt_args)
                except Exception as exc:  # pragma: no cover
                    print(f"    - fail {sheet}: {exc}")
                    continue

                detail_rows.append(
                    {
                        "combo_id": cid,
                        "setup": setup_name,
                        "interval_min": minutes,
                        "sheet": sheet,
                        "prob_threshold": combo["prob_threshold"],
                        "min_taker_ratio": combo["min_taker_ratio"],
                        "max_roi_entry": combo["max_roi_entry"],
                        "sl_mult": combo["sl_mult"],
                        "tp_mult": combo["tp_mult"],
                        "total_return_pct": summary["total_return_pct"],
                        "max_drawdown_pct": summary["max_drawdown_pct"],
                        "profit_factor": summary["profit_factor"],
                        "win_rate": summary["win_rate"],
                        "num_trades": summary["num_trades"],
                        "avg_trade_return_pct": summary["avg_trade_return_pct"],
                        "avg_pnl": summary["avg_pnl"],
                        "final_capital": summary["final_capital"],
                        "trades_file": trades_output,
                        "rows_trades": int(len(trades_df)),
                    }
                )
                print(
                    f"    - {sheet}: return={summary['total_return_pct']:.3f}% "
                    f"pf={summary['profit_factor']:.3f} dd={summary['max_drawdown_pct']:.3f}% "
                    f"trades={int(summary['num_trades'])}"
                )

    if not detail_rows:
        raise RuntimeError("No experiment rows produced. Verify sheet names in XLSX.")

    detail_df = pd.DataFrame(detail_rows).sort_values(
        ["combo_id", "setup", "interval_min"], ascending=[True, True, True]
    )

    grouped = detail_df.groupby(
        [
            "combo_id",
            "setup",
            "prob_threshold",
            "min_taker_ratio",
            "max_roi_entry",
            "sl_mult",
            "tp_mult",
        ],
        as_index=False,
    )
    summary_df = grouped.agg(
        intervals_tested=("sheet", "count"),
        total_trades=("num_trades", "sum"),
        avg_return_pct=("total_return_pct", "mean"),
        median_return_pct=("total_return_pct", "median"),
        avg_drawdown_pct=("max_drawdown_pct", "mean"),
        median_drawdown_pct=("max_drawdown_pct", "median"),
        avg_win_rate=("win_rate", "mean"),
        profitable_intervals=("total_return_pct", lambda s: int((s > 0).sum())),
    )

    pf_by_setup = (
        detail_df.groupby(
            [
                "combo_id",
                "setup",
                "prob_threshold",
                "min_taker_ratio",
                "max_roi_entry",
                "sl_mult",
                "tp_mult",
            ]
        )["profit_factor"]
        .apply(finite_mean)
        .rename("avg_profit_factor_finite")
        .reset_index()
    )
    summary_df = summary_df.merge(
        pf_by_setup,
        on=[
            "combo_id",
            "setup",
            "prob_threshold",
            "min_taker_ratio",
            "max_roi_entry",
            "sl_mult",
            "tp_mult",
        ],
        how="left",
    )
    stability_df = (
        detail_df.groupby(
            [
                "combo_id",
                "setup",
                "prob_threshold",
                "min_taker_ratio",
                "max_roi_entry",
                "sl_mult",
                "tp_mult",
            ]
        )["total_return_pct"]
        .std()
        .fillna(0.0)
        .rename("stability_return_std")
        .reset_index()
    )
    summary_df = summary_df.merge(
        stability_df,
        on=[
            "combo_id",
            "setup",
            "prob_threshold",
            "min_taker_ratio",
            "max_roi_entry",
            "sl_mult",
            "tp_mult",
        ],
        how="left",
    )
    summary_df["score"] = (
        summary_df["avg_return_pct"]
        + 0.5 * summary_df["avg_profit_factor_finite"]
        - 0.7 * summary_df["avg_drawdown_pct"]
        - 0.2 * summary_df["stability_return_std"]
    )
    summary_df = summary_df.sort_values("score", ascending=False)

    out_summary = Path(args.output_summary)
    out_detail = Path(args.output_detail)
    out_summary.parent.mkdir(parents=True, exist_ok=True)
    out_detail.parent.mkdir(parents=True, exist_ok=True)
    summary_df.to_csv(out_summary, index=False)
    detail_df.to_csv(out_detail, index=False)

    print("\n=== Setup Summary (top) ===")
    print(summary_df.head(max(1, args.top)).to_string(index=False))
    print(f"\nSaved summary: {out_summary}")
    print(f"Saved detail: {out_detail}")

    print("\n=== Interval Detail (top by return) ===")
    print(
        detail_df.sort_values("total_return_pct", ascending=False)
        .head(max(1, args.top))
        .to_string(index=False)
    )


if __name__ == "__main__":
    main()
