"""
bitacora.py — Genera bitácora de trades del bot a partir de los logs CSV.

Uso:
    python scripts/bitacora.py                    # usa backtest_output/ por defecto
    python scripts/bitacora.py --dir /ruta/logs   # directorio personalizado
    python scripts/bitacora.py --date 2026-02-21  # filtra por fecha UTC (placed_at_utc)

Salida:
    - Imprime resumen en consola
    - Guarda backtest_output/bitacora_trades.csv con detalle completo

Archivos que consume (todos en --dir):
    bot_orders.csv | bot_orders_YYYY-MM-DD.csv  — órdenes ejecutadas por el bot
    opportunity_outcomes.csv   — resultados de señales (won, pnl, close_price, ...)
    opportunities_log.csv      — todas las señales detectadas
    opportunity_blocked.csv    — señales bloqueadas por quant gate
    order_blocked_log.csv      — órdenes bloqueadas por risk guard
"""

import argparse
import glob
import os
import sys

import pandas as pd


# ── Helpers ───────────────────────────────────────────────────────────────────

def load(directory: str, filename: str) -> pd.DataFrame:
    path = os.path.join(directory, filename)
    if not os.path.exists(path):
        print(f"  [WARN] No encontrado: {path}")
        return pd.DataFrame()
    return pd.read_csv(path)


def load_bot_orders(directory: str) -> pd.DataFrame:
    """Load bot_orders.csv or merge all bot_orders_YYYY-MM-DD.csv files."""
    single = os.path.join(directory, "bot_orders.csv")
    if os.path.exists(single):
        return pd.read_csv(single)
    dated = sorted(glob.glob(os.path.join(directory, "bot_orders_*.csv")))
    if not dated:
        print(f"  [WARN] No encontrado: bot_orders*.csv en {directory}")
        return pd.DataFrame()
    frames = [pd.read_csv(p) for p in dated]
    return pd.concat(frames, ignore_index=True)


def pct_bar(hit: float, total: int) -> str:
    filled = round(hit / 10)
    return f"{'█' * filled}{'░' * (10 - filled)} {hit:.0f}%  (n={total})"


# ── Main ──────────────────────────────────────────────────────────────────────

def main(directory: str, date_filter: str | None) -> None:
    print(f"\nDirectorio de logs : {os.path.abspath(directory)}")
    if date_filter:
        print(f"Filtro de fecha    : {date_filter}")

    # Carga
    bot    = load_bot_orders(directory)
    outc   = load(directory, "opportunity_outcomes.csv")
    opps   = load(directory, "opportunities_log.csv")
    block  = load(directory, "opportunity_blocked.csv")
    ordblk = load(directory, "order_blocked_log.csv")

    if bot.empty:
        print("\n[ERROR] bot_orders.csv vacío o no encontrado. Abortando.")
        sys.exit(1)

    # Filtro de fecha
    bot["placed_at_utc"] = pd.to_datetime(bot["placed_at_utc"], utc=True)
    if date_filter:
        bot = bot[bot["placed_at_utc"].dt.strftime("%Y-%m-%d") == date_filter]
        if bot.empty:
            print(f"\n[ERROR] Sin órdenes para la fecha {date_filter}.")
            sys.exit(1)

    placed = bot[bot["status"] == "placed"].copy()
    failed = bot[bot["status"] == "failed"].copy()

    # Cruce con outcomes
    # v2: bot_orders ya trae won/pnl_simulated embebidos — saltar merge
    # v1: necesita join con opportunity_outcomes.csv
    merged = pd.DataFrame()
    if "won" in placed.columns:
        merged = placed.copy()
        if "pnl_usd" not in merged.columns and "pnl_simulated" in merged.columns:
            merged = merged.rename(columns={"pnl_simulated": "pnl_usd"})
    elif not outc.empty and not placed.empty:
        merged = placed.merge(
            outc[[
                "event_id", "side", "won", "pnl_usd", "close_price",
                "entry_side_price", "return_pct", "minutes_to_close",
                "edge_pct_at_signal", "percentile_at_signal",
                "sample_size_at_signal", "closed_at_utc",
                "actual_outcome", "price_to_beat",
            ]],
            on=["event_id", "side"],
            how="left",
        )
    else:
        merged = placed.copy()

    merged["result"] = merged["won"].apply(
        lambda x: "WON" if x == 1 else ("LOST" if x == 0 else "PENDING")
    )
    merged = merged.sort_values("placed_at_utc")

    resolved = merged[merged["result"] != "PENDING"]
    pending  = merged[merged["result"] == "PENDING"]
    won      = resolved[resolved["result"] == "WON"]
    lost     = resolved[resolved["result"] == "LOST"]

    # ── Guardar CSV ───────────────────────────────────────────────────────────
    out_cols = [
        "placed_at_utc", "closed_at_utc", "result", "ticker", "side",
        "shares", "price", "notional_usd", "quant_prob", "edge_pct",
        "kelly_pct", "bankroll_usd", "percentile_at_signal", "sample_size_at_signal",
        "pnl_usd", "return_pct", "close_price", "price_to_beat",
        "minutes_to_close", "actual_outcome", "event_id",
    ]
    out_cols_present = [c for c in out_cols if c in merged.columns]
    out_path = os.path.join(directory, "bitacora_trades.csv")
    merged[out_cols_present].to_csv(out_path, index=False)
    print(f"Bitácora guardada  : {out_path}\n")

    # ── Resumen general ───────────────────────────────────────────────────────
    t_start = merged["placed_at_utc"].min().strftime("%Y-%m-%d %H:%M")
    t_end   = merged["placed_at_utc"].max().strftime("%Y-%m-%d %H:%M")

    print("╔══════════════════════════════════════════════════════╗")
    print("║              BITÁCORA — RESUMEN GENERAL              ║")
    print("╚══════════════════════════════════════════════════════╝")
    print(f"  Período          : {t_start} → {t_end} UTC")
    print(f"  Órdenes placed   : {len(placed)}")
    print(f"  Órdenes failed   : {len(failed)}")
    print(f"  Resueltas        : {len(resolved)}  |  Pendientes: {len(pending)}")

    if len(resolved):
        hit = len(won) / len(resolved) * 100
        print(f"  Won / Lost       : {len(won)} / {len(lost)}")
        print(f"  Hit rate         : {pct_bar(hit, len(resolved))}")
        print(f"  Notional total   : ${placed['notional_usd'].sum():.2f}")
        print(f"  PnL resueltas    : ${resolved['pnl_usd'].sum():.4f}")
        print(f"  PnL avg WON      : ${won['pnl_usd'].mean():.4f}")
        print(f"  PnL avg LOST     : ${lost['pnl_usd'].mean():.4f}")
        if "return_pct" in resolved.columns:
            print(f"  Return promedio  : {resolved['return_pct'].mean():.2f}%")

    # ── Por ticker ────────────────────────────────────────────────────────────
    if len(resolved) and "ticker" in resolved.columns:
        print("\n── Por ticker (resueltas) ──────────────────────────────")
        for tk, g in resolved.groupby("ticker"):
            w = (g["result"] == "WON").sum()
            l = len(g) - w
            print(f"  {tk:<5}: {len(g):>3} trades | {w}W/{l}L | hit {w/len(g)*100:.0f}% | PnL ${g['pnl_usd'].sum():.4f}")

    # ── Por side ──────────────────────────────────────────────────────────────
    if len(resolved) and "side" in resolved.columns:
        print("\n── Por side (resueltas) ────────────────────────────────")
        for sd, g in resolved.groupby("side"):
            w = (g["result"] == "WON").sum()
            l = len(g) - w
            print(f"  {sd:<5}: {len(g):>3} trades | {w}W/{l}L | hit {w/len(g)*100:.0f}% | PnL ${g['pnl_usd'].sum():.4f}")

    # ── Funnel de señales ─────────────────────────────────────────────────────
    print("\n── Funnel de señales ───────────────────────────────────")
    print(f"  Señales detectadas (opportunities_log)  : {len(opps)}")
    print(f"  Bloqueadas por quant gate               : {len(block)}")
    if not block.empty and "blocked_reason" in block.columns:
        for reason, cnt in block["blocked_reason"].value_counts().items():
            print(f"    · {reason}: {cnt}")
    print(f"  Bloqueadas por risk guard               : {len(ordblk)}")
    if not ordblk.empty and "reason" in ordblk.columns:
        for reason, cnt in ordblk["reason"].value_counts().items():
            print(f"    · {reason}: {cnt}")
    print(f"  Órdenes placed                          : {len(placed)}")
    print(f"  Órdenes failed (API)                    : {len(failed)}")

    # ── Distribución de percentil ─────────────────────────────────────────────
    if len(resolved) and "percentile_at_signal" in resolved.columns:
        p = resolved["percentile_at_signal"].dropna()
        if len(p):
            print("\n── Hit rate por percentil al momento de la señal ───────")
            bins   = [0, 20, 40, 60, 80, 100]
            labels = ["0-20", "20-40", "40-60", "60-80", "80-100"]
            cut = pd.cut(p, bins=bins, labels=labels, include_lowest=True)
            sub = resolved[resolved["percentile_at_signal"].notna()].copy()
            sub["pct_bin"] = cut
            for lbl, grp in sub.groupby("pct_bin", observed=True):
                w = (grp["result"] == "WON").sum()
                t = len(grp)
                print(f"  pct {lbl}: {pct_bar(w/t*100, t)} | PnL ${grp['pnl_usd'].sum():.4f}")

    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Genera bitácora de trades del bot.")
    parser.add_argument(
        "--dir",
        default="backtest_output",
        help="Directorio con los CSV de logs (default: backtest_output)",
    )
    parser.add_argument(
        "--date",
        default=None,
        help="Filtrar por fecha UTC en formato YYYY-MM-DD (default: todas)",
    )
    args = parser.parse_args()
    main(args.dir, args.date)
