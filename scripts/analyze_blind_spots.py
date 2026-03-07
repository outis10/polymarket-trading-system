#!/usr/bin/env python3
"""
Blind Spot Analysis — Polymarket Bot

Identifica condiciones donde el modelo pierde consistentemente para ajustar filtros
del gate (spread, horas, slots). Diseñado para re-ejecutarse cada 2-4 semanas con
nuevos datos acumulados.

Uso:
  python3 scripts/analyze_blind_spots.py
  python3 scripts/analyze_blind_spots.py --min-n 10 --days 14
  python3 scripts/analyze_blind_spots.py --since 2026-03-01

Outputs:
  - Resumen en consola con tablas por dimensión
  - Archivo CSV en backtest_output/blind_spot_report_YYYY-MM-DD.csv (opcional con --save)

Ver documentación metodológica en: docs/blind_spot_analysis.md
"""

import argparse
import csv
from datetime import datetime, timedelta, timezone
from glob import glob
from pathlib import Path

import pandas as pd


# ---------------------------------------------------------------------------
# Carga y filtro de datos
# ---------------------------------------------------------------------------

def load_resolved(since: str | None = None, days: int | None = None) -> pd.DataFrame:
    files = sorted(glob("backtest_output/bot_orders_*.csv"))
    if not files:
        raise FileNotFoundError("No se encontraron archivos bot_orders_*.csv en backtest_output/")
    dfs = [pd.read_csv(f) for f in files]
    df = pd.concat(dfs, ignore_index=True)
    df = df[(df["status"] == "placed") & (df["resolution_status"] == "resolved")].copy()

    df["placed_dt"] = pd.to_datetime(df["placed_at_utc"], utc=True)

    if since:
        cutoff = pd.Timestamp(since, tz="UTC")
        df = df[df["placed_dt"] >= cutoff]
    elif days:
        cutoff = pd.Timestamp.now(tz="UTC") - timedelta(days=days)
        df = df[df["placed_dt"] >= cutoff]

    # Derivadas
    df["hour_utc"] = df["placed_dt"].dt.hour
    df["hour_pst"] = (df["hour_utc"] - 8) % 24
    for col in ["slot", "diff_vs_ptb_at_send", "quant_prob", "edge_pct",
                "fill_price_real", "slippage_pct", "spread_pct_at_send", "won",
                "pnl_simulated", "notional_usd"]:
        df[col] = pd.to_numeric(df.get(col, pd.NA), errors="coerce")

    return df


# ---------------------------------------------------------------------------
# Tablas de análisis
# ---------------------------------------------------------------------------

def table_by(df: pd.DataFrame, col: str, bins=None, labels=None,
             min_n: int = 5) -> pd.DataFrame:
    if bins:
        df = df.copy()
        df["_bin"] = pd.cut(df[col], bins=bins, labels=labels, right=False)
        group_col = "_bin"
    else:
        group_col = col

    g = df.groupby(group_col, observed=True).agg(
        n=("won", "count"),
        win_rate=("won", "mean"),
        pnl=("pnl_simulated", "sum"),
        avg_stake=("notional_usd", "mean"),
    ).reset_index()
    g = g[g["n"] >= min_n].copy()
    g["win_rate_pct"] = (g["win_rate"] * 100).round(1)
    g["pnl_per_trade"] = (g["pnl"] / g["n"]).round(2)
    g["pnl"] = g["pnl"].round(2)
    g["avg_stake"] = g["avg_stake"].round(2)
    g = g.rename(columns={group_col: col})
    return g[[ col, "n", "win_rate_pct", "pnl", "pnl_per_trade", "avg_stake"]]


def section(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print('='*60)


def flag(row, win_thresh=50.0, pnl_thresh=-5.0) -> str:
    if row["win_rate_pct"] < win_thresh and row["pnl"] < pnl_thresh:
        return "🔴 BLIND SPOT"
    if row["win_rate_pct"] > 70.0 and row["pnl"] > 10.0:
        return "✅ STRONG"
    return ""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--since", default=None,
                        help="Fecha mínima YYYY-MM-DD (ej: 2026-03-01)")
    parser.add_argument("--days", type=int, default=None,
                        help="Últimos N días (alternativa a --since)")
    parser.add_argument("--min-n", type=int, default=5,
                        help="Mínimo de trades por bucket para incluir (default: 5)")
    parser.add_argument("--save", action="store_true",
                        help="Guarda resumen en backtest_output/blind_spot_report_DATE.csv")
    args = parser.parse_args()

    df = load_resolved(since=args.since, days=args.days)
    total = len(df)
    wins = int(df["won"].sum())
    pnl = df["pnl_simulated"].sum()
    stake = df["notional_usd"].sum()

    print(f"\nPERIODO: {df['placed_dt'].min().date()} → {df['placed_dt'].max().date()}")
    print(f"Trades resueltos: {total} | Wins: {wins} ({wins/total*100:.1f}%) | "
          f"PnL: ${pnl:.2f} | Stake: ${stake:.2f} | ROI: {pnl/stake*100:.1f}%")

    all_rows = []

    # --- Spread ---
    section("SPREAD (el filtro más accionable)")
    sbins   = [0, 0.01, 0.02, 0.03, 0.05, 0.10, 1.0]
    slabels = ["<1%", "1-2%", "2-3%", "3-5%", "5-10%", ">10%"]
    t = table_by(df, "spread_pct_at_send", bins=sbins, labels=slabels, min_n=args.min_n)
    t["flag"] = t.apply(flag, axis=1)
    print(t.to_string(index=False))
    t["dimension"] = "spread"
    all_rows.append(t)

    # --- Hora PST ---
    section("HORA PST")
    t = table_by(df, "hour_pst", min_n=args.min_n).sort_values("hour_pst")
    t["flag"] = t.apply(flag, axis=1)
    print(t.to_string(index=False))
    t["dimension"] = "hora_pst"
    all_rows.append(t)

    # --- Slot ---
    section("SLOT (posición en ventana 5min)")
    t = table_by(df, "slot", min_n=args.min_n).sort_values("slot")
    t["flag"] = t.apply(flag, axis=1)
    print(t.to_string(index=False))
    t["dimension"] = "slot"
    all_rows.append(t)

    # --- Side ---
    section("SIDE (up vs down)")
    t = table_by(df, "side", min_n=args.min_n)
    t["flag"] = t.apply(flag, axis=1)
    print(t.to_string(index=False))
    t["dimension"] = "side"
    all_rows.append(t)

    # --- Diff vs PTB ---
    section("DIFF vs PRICE_TO_BEAT (USD)")
    dbins   = [-500, -200, -100, -50, -20, -5, 5, 20, 50, 100, 200, 500]
    t = table_by(df, "diff_vs_ptb_at_send", bins=dbins,
                 labels=[f"[{dbins[i]},{dbins[i+1]})" for i in range(len(dbins)-1)],
                 min_n=args.min_n)
    t["flag"] = t.apply(flag, axis=1)
    print(t.to_string(index=False))
    t["dimension"] = "diff_vs_ptb"
    all_rows.append(t)

    # --- Edge bucket ---
    section("EDGE PCT")
    ebins   = [0, 5, 8, 10, 12, 15, 20, 50]
    elabels = ["<5%", "5-8%", "8-10%", "10-12%", "12-15%", "15-20%", ">20%"]
    t = table_by(df, "edge_pct", bins=ebins, labels=elabels, min_n=args.min_n)
    t["flag"] = t.apply(flag, axis=1)
    print(t.to_string(index=False))
    t["dimension"] = "edge_pct"
    all_rows.append(t)

    # --- Fill price bucket ---
    section("PRECIO DE FILL")
    pbins   = [0, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.85, 1.01]
    t = table_by(df, "fill_price_real", bins=pbins,
                 labels=[f"[{pbins[i]:.2f},{pbins[i+1]:.2f})" for i in range(len(pbins)-1)],
                 min_n=args.min_n)
    t["flag"] = t.apply(flag, axis=1)
    print(t.to_string(index=False))
    t["dimension"] = "fill_price"
    all_rows.append(t)

    # --- Combos peores: hora PST x side ---
    section("COMBOS PEORES (hora_pst × side, n≥10, win<50%)")
    combos = df.groupby(["hour_pst", "side"], observed=True).agg(
        n=("won", "count"), win_rate=("won", "mean"), pnl=("pnl_simulated", "sum")
    ).reset_index()
    combos = combos[combos["n"] >= 10].copy()
    combos["win_rate_pct"] = (combos["win_rate"] * 100).round(1)
    combos["pnl"] = combos["pnl"].round(2)
    worst = combos[combos["win_rate_pct"] < 50].sort_values("win_rate_pct")
    if worst.empty:
        print("  (ninguno con n≥10 y win<50%)")
    else:
        print(worst[["hour_pst", "side", "n", "win_rate_pct", "pnl"]].to_string(index=False))

    # --- Resumen de blind spots ---
    section("RESUMEN — BLIND SPOTS DETECTADOS")
    combined = pd.concat(all_rows, ignore_index=True)
    bs = combined[combined["flag"] == "🔴 BLIND SPOT"].copy()
    if bs.empty:
        print("  No se detectaron blind spots claros con los umbrales actuales.")
    else:
        print(bs[["dimension", "spread_pct_at_send", "n", "win_rate_pct", "pnl"]].to_string(index=False))

    # --- Recomendaciones automáticas ---
    section("RECOMENDACIONES DE FILTRO")
    spread_bs = df.groupby(
        pd.cut(df["spread_pct_at_send"], bins=sbins, labels=slabels, right=False),
        observed=True
    ).agg(n=("won","count"), pnl=("pnl_simulated","sum")).reset_index()
    bad_spread = spread_bs[spread_bs["pnl"] < -10]
    if not bad_spread.empty:
        worst_spread_label = bad_spread.sort_values("pnl").iloc[0]["spread_pct_at_send"]
        idx = slabels.index(str(worst_spread_label))
        threshold = sbins[idx]
        print(f"  ✦ Filtro spread recomendado: quant_gate_max_spread_pct = {threshold:.2f}")
        print(f"    (buckets con PnL negativo: {list(bad_spread['spread_pct_at_send'].astype(str))})")
    else:
        print("  ✦ El spread no muestra patrón negativo claro — mantener filtro actual.")

    hours_pnl = df.groupby("hour_pst").agg(n=("won","count"), pnl=("pnl_simulated","sum")).reset_index()
    bad_hours = sorted(hours_pnl[(hours_pnl["pnl"] < -15) & (hours_pnl["n"] >= 15)]["hour_pst"].tolist())
    if bad_hours:
        print(f"  ✦ Horas PST con pérdidas consistentes (n≥15, PnL<-$15): {bad_hours}")
        print(f"    Considera reducir min_edge o desactivar en esas horas.")

    slots_pnl = df.groupby("slot").agg(n=("won","count"), pnl=("pnl_simulated","sum")).reset_index()
    bad_slots = sorted(slots_pnl[(slots_pnl["pnl"] < -20) & (slots_pnl["n"] >= 15)]["slot"].tolist())
    if bad_slots:
        print(f"  ✦ Slots problemáticos (n≥15, PnL<-$20): {[int(s) for s in bad_slots]}")

    # --- Guardar CSV ---
    if args.save:
        out_path = Path("backtest_output") / f"blind_spot_report_{datetime.now(timezone.utc).date()}.csv"
        combined.to_csv(out_path, index=False)
        print(f"\n  Reporte guardado en: {out_path}")

    print()


if __name__ == "__main__":
    main()
