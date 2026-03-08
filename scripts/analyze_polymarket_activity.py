"""
Análisis de actividad de Polymarket — 5 dimensiones.

Requiere haber corrido primero:
    python3 scripts/export_polymarket_activity.py

Archivos de entrada (se auto-detectan el más reciente):
    backtest_output/polymarket_activity_*.csv
    backtest_output/polymarket_positions_*.csv

Uso:
    python3 scripts/analyze_polymarket_activity.py
    python3 scripts/analyze_polymarket_activity.py --since 2026-03-04   # solo desde esa fecha
    python3 scripts/analyze_polymarket_activity.py --save               # exportar resultados a CSV

Análisis disponibles:
    1. P&L real por mercado (top ganadores y perdedores)
    2. Distribución de fills reales (precio de ejecución)
    3. Actividad por hora PST (win rate y P&L por hora del día)
    4. Slippage estimado (precio ponderado vs precio mid de la sesión)
    5. Posiciones abiertas actuales con valor de mercado
"""

import argparse
import csv
import glob
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
OUTPUT_DIR = Path(__file__).parent.parent / "backtest_output"
PST_OFFSET = timedelta(hours=-8)  # PST = UTC-8 (no DST ajuste aquí)


# ---------------------------------------------------------------------------
# I/O helpers
# ---------------------------------------------------------------------------

def _latest_file(pattern: str) -> Path | None:
    files = sorted(glob.glob(str(OUTPUT_DIR / pattern)))
    return Path(files[-1]) if files else None


def _load_csv(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _safe_float(v) -> float:
    try:
        return float(v) if v not in (None, "", "None") else 0.0
    except (ValueError, TypeError):
        return 0.0


def _ts_to_dt_utc(ts: str) -> datetime:
    return datetime.fromtimestamp(int(ts), tz=timezone.utc)


def _ts_to_pst_hour(ts: str) -> int:
    return (_ts_to_dt_utc(ts) + PST_OFFSET).hour


def _save_analysis_csv(rows: list[dict], filename: str) -> None:
    if not rows:
        return
    path = OUTPUT_DIR / filename
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"  → Guardado: {path}")


def _header(title: str) -> None:
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


# ---------------------------------------------------------------------------
# 1. P&L real por mercado
# ---------------------------------------------------------------------------

def analysis_pnl_by_market(activity: list[dict], positions: list[dict], since_dt: datetime | None, save: bool) -> None:
    """
    PnL = USDC recibido (REDEEM+SELL) - USDC gastado (BUY) + currentValue si aún abierta.
    Agrupa por conditionId (cada conditionId = un outcome en un mercado específico).
    """
    _header("1. P&L REAL POR MERCADO")

    # Build positions currentValue lookup by conditionId
    pos_cv: dict[str, float] = {}
    pos_title: dict[str, str] = {}
    for p in positions:
        cid = p.get("conditionId", "")
        pos_cv[cid]    = _safe_float(p.get("currentValue"))
        pos_title[cid] = p.get("title", "")

    # Aggregate by conditionId
    market_spent:    dict[str, float] = defaultdict(float)
    market_received: dict[str, float] = defaultdict(float)
    market_title:    dict[str, str]   = {}
    market_n_buys:   dict[str, int]   = defaultdict(int)

    for row in activity:
        ts = row.get("timestamp", "0")
        if since_dt and _ts_to_dt_utc(ts) < since_dt:
            continue
        cid   = row.get("conditionId", "")
        usdc  = _safe_float(row.get("usdcSize"))
        typ   = row.get("type", "")
        title = row.get("title", "")
        if title and cid not in market_title:
            market_title[cid] = title

        if typ == "TRADE" and row.get("side") == "BUY":
            market_spent[cid]  += usdc
            market_n_buys[cid] += 1
        elif typ in ("TRADE", "REDEEM") and row.get("side") in ("SELL", ""):
            market_received[cid] += usdc

    # Compute PnL
    all_cids = set(market_spent) | set(market_received)
    results = []
    for cid in all_cids:
        spent    = market_spent[cid]
        received = market_received[cid]
        cv       = pos_cv.get(cid, 0.0)
        pnl      = received + cv - spent
        title    = market_title.get(cid) or pos_title.get(cid) or cid[:16]
        results.append({
            "conditionId": cid,
            "title":        title[:60],
            "n_buys":       market_n_buys[cid],
            "spent_usdc":   round(spent, 4),
            "received_usdc": round(received, 4),
            "current_value": round(cv, 4),
            "pnl_usdc":     round(pnl, 4),
            "roi_pct":      round(pnl / spent * 100, 2) if spent > 0 else 0.0,
        })

    results.sort(key=lambda x: x["pnl_usdc"])

    total_spent    = sum(r["spent_usdc"] for r in results)
    total_received = sum(r["received_usdc"] for r in results)
    total_cv       = sum(r["current_value"] for r in results)
    total_pnl      = sum(r["pnl_usdc"] for r in results)

    print(f"\nTotal mercados: {len(results)}")
    print(f"USDC gastado:   ${total_spent:,.2f}")
    print(f"USDC recibido:  ${total_received:,.2f}  (redeems + sells)")
    print(f"Valor abierto:  ${total_cv:,.2f}")
    print(f"PnL neto:       ${total_pnl:+,.2f}  (ROI: {total_pnl/total_spent*100:+.2f}%)")

    print(f"\n{'TOP 10 PERDEDORES':}")
    for r in results[:10]:
        print(f"  {r['pnl_usdc']:+7.2f}  ({r['roi_pct']:+5.1f}%)  n={r['n_buys']:3d}  {r['title']}")

    print(f"\nTOP 10 GANADORES:")
    for r in sorted(results, key=lambda x: x["pnl_usdc"], reverse=True)[:10]:
        print(f"  {r['pnl_usdc']:+7.2f}  ({r['roi_pct']:+5.1f}%)  n={r['n_buys']:3d}  {r['title']}")

    if save:
        _save_analysis_csv(results, "analysis_pnl_by_market.csv")


# ---------------------------------------------------------------------------
# 2. Distribución de fills reales
# ---------------------------------------------------------------------------

def analysis_fill_distribution(activity: list[dict], since_dt: datetime | None, save: bool) -> None:
    """
    Distribución del precio de fill real (price) en los BUYs.
    Muestra cuántos trades caen en cada bucket de precio y si son rentables.
    Requiere cruzar con REDEEMs del mismo conditionId para saber si ganó.
    """
    _header("2. DISTRIBUCIÓN DE FILLS REALES")

    buys = [r for r in activity
            if r.get("type") == "TRADE" and r.get("side") == "BUY"
            and (not since_dt or _ts_to_dt_utc(r["timestamp"]) >= since_dt)]

    # Determine which conditionIds ended in redeem (= win)
    redeemed_cids: set[str] = set(
        r["conditionId"] for r in activity
        if r.get("type") == "REDEEM"
        and (not since_dt or _ts_to_dt_utc(r["timestamp"]) >= since_dt)
    )

    # Buckets: [0,0.1), [0.1,0.2), ... [0.9,1.0]
    buckets = [(i / 10, (i + 1) / 10) for i in range(10)]
    bucket_data: dict[str, dict] = {}
    for lo, hi in buckets:
        label = f"{lo:.1f}-{hi:.1f}"
        bucket_data[label] = {"n": 0, "wins": 0, "usdc_spent": 0.0, "usdc_received": 0.0}

    # Map conditionId → total redeem received
    redeem_by_cid: dict[str, float] = defaultdict(float)
    for r in activity:
        if r.get("type") == "REDEEM":
            redeem_by_cid[r["conditionId"]] += _safe_float(r.get("usdcSize"))

    for row in buys:
        price = _safe_float(row.get("price"))
        usdc  = _safe_float(row.get("usdcSize"))
        cid   = row.get("conditionId", "")
        won   = cid in redeemed_cids
        for lo, hi in buckets:
            if lo <= price < hi or (hi == 1.0 and price == 1.0):
                label = f"{lo:.1f}-{hi:.1f}"
                bucket_data[label]["n"] += 1
                bucket_data[label]["usdc_spent"] += usdc
                if won:
                    bucket_data[label]["wins"] += 1
                break

    print(f"\n{'Bucket':12} {'N':>5} {'Win%':>6} {'Spent':>9} {'Avg stake':>10}")
    print("-" * 50)
    rows_out = []
    for lo, hi in buckets:
        label = f"{lo:.1f}-{hi:.1f}"
        d = bucket_data[label]
        if d["n"] == 0:
            continue
        win_pct = d["wins"] / d["n"] * 100
        avg_stake = d["usdc_spent"] / d["n"]
        flag = " ⚠" if d["n"] >= 10 and win_pct < 40 else (" ✅" if win_pct > 65 and d["n"] >= 10 else "")
        print(f"  {label:10} {d['n']:5d} {win_pct:5.1f}%  ${d['usdc_spent']:7.2f}  ${avg_stake:7.2f}{flag}")
        rows_out.append({
            "price_bucket": label,
            "n_trades": d["n"],
            "wins": d["wins"],
            "win_pct": round(win_pct, 1),
            "usdc_spent": round(d["usdc_spent"], 2),
            "avg_stake_usd": round(avg_stake, 2),
        })

    note = """
Nota: 'win' = el conditionId tuvo al menos un REDEEM en el período.
No es perfecto (un conditionId puede tener trades en múltiples períodos),
pero es la mejor aproximación disponible sin datos de resolución explícitos.
"""
    print(note)
    if save:
        _save_analysis_csv(rows_out, "analysis_fill_distribution.csv")


# ---------------------------------------------------------------------------
# 3. Actividad por hora PST
# ---------------------------------------------------------------------------

def analysis_by_hour(activity: list[dict], since_dt: datetime | None, save: bool) -> None:
    """
    Agrupa BUYs por hora PST y calcula cuánto se gastó y cuánto se recuperó.
    Win rate aproximado = trades cuyo conditionId tuvo REDEEM.
    """
    _header("3. ACTIVIDAD POR HORA PST")

    redeemed_cids: set[str] = set(
        r["conditionId"] for r in activity
        if r.get("type") == "REDEEM"
        and (not since_dt or _ts_to_dt_utc(r["timestamp"]) >= since_dt)
    )

    hour_data: dict[int, dict] = {h: {"n": 0, "wins": 0, "spent": 0.0} for h in range(24)}

    for row in activity:
        if row.get("type") != "TRADE" or row.get("side") != "BUY":
            continue
        ts = row.get("timestamp", "0")
        if since_dt and _ts_to_dt_utc(ts) < since_dt:
            continue
        hour = _ts_to_pst_hour(ts)
        usdc = _safe_float(row.get("usdcSize"))
        won  = row.get("conditionId", "") in redeemed_cids
        hour_data[hour]["n"]     += 1
        hour_data[hour]["spent"] += usdc
        if won:
            hour_data[hour]["wins"] += 1

    print(f"\n{'Hora PST':10} {'N':>5} {'Win%':>6} {'Spent':>9} {'Avg':>7}")
    print("-" * 45)
    rows_out = []
    for h in range(24):
        d = hour_data[h]
        if d["n"] == 0:
            continue
        win_pct   = d["wins"] / d["n"] * 100
        avg_stake = d["spent"] / d["n"]
        flag = " ⚠" if d["n"] >= 10 and win_pct < 45 else (" ✅" if win_pct > 65 and d["n"] >= 10 else "")
        print(f"  {h:02d}:00       {d['n']:5d} {win_pct:5.1f}%  ${d['spent']:7.2f}  ${avg_stake:5.2f}{flag}")
        rows_out.append({
            "hour_pst": h,
            "n_trades": d["n"],
            "wins": d["wins"],
            "win_pct": round(win_pct, 1),
            "usdc_spent": round(d["spent"], 2),
            "avg_stake_usd": round(avg_stake, 2),
        })

    if save:
        _save_analysis_csv(rows_out, "analysis_by_hour_pst.csv")


# ---------------------------------------------------------------------------
# 4. Slippage estimado
# ---------------------------------------------------------------------------

def analysis_slippage(activity: list[dict], since_dt: datetime | None, save: bool) -> None:
    """
    Slippage = diferencia entre el precio de fill de la primera compra en un mercado
    vs el precio de fill de compras posteriores en el mismo mercado.

    También calcula precio promedio ponderado por conditionId y distribución de
    desviaciones de precio dentro de la misma sesión (mismo slug + mismo minuto).
    """
    _header("4. SLIPPAGE ESTIMADO")

    buys = [r for r in activity
            if r.get("type") == "TRADE" and r.get("side") == "BUY"
            and (not since_dt or _ts_to_dt_utc(r["timestamp"]) >= since_dt)]

    # Group by conditionId
    by_cid: dict[str, list] = defaultdict(list)
    for row in buys:
        by_cid[row["conditionId"]].append(row)

    # For each conditionId with >1 buy: compute price spread within same market
    slippage_cases = []
    for cid, rows in by_cid.items():
        if len(rows) < 2:
            continue
        prices = [_safe_float(r["price"]) for r in rows]
        p_min  = min(prices)
        p_max  = max(prices)
        p_avg  = sum(prices) / len(prices)
        spread = p_max - p_min
        if spread > 0.005:  # solo casos con spread notable
            slippage_cases.append({
                "conditionId":   cid,
                "title":         rows[0].get("title", "")[:50],
                "n_buys":        len(rows),
                "price_min":     round(p_min, 4),
                "price_max":     round(p_max, 4),
                "price_avg":     round(p_avg, 4),
                "price_spread":  round(spread, 4),
                "spread_pct":    round(spread / p_min * 100, 1),
            })

    slippage_cases.sort(key=lambda x: x["spread_pct"], reverse=True)

    # Summary stats
    all_prices  = [_safe_float(r["price"]) for r in buys]
    all_usdc    = [_safe_float(r["usdcSize"]) for r in buys]
    wavg_price  = sum(p * u for p, u in zip(all_prices, all_usdc)) / sum(all_usdc) if all_usdc else 0
    p50_price   = sorted(all_prices)[len(all_prices) // 2]

    print(f"\nTotal BUYs analizados: {len(buys)}")
    print(f"Precio promedio ponderado por USDC: {wavg_price:.4f}")
    print(f"Precio mediana (fill): {p50_price:.4f}")
    print(f"\nCasos con spread de precio > 0.5% dentro del mismo conditionId: {len(slippage_cases)}")

    print(f"\n{'Top 10 casos con mayor spread de precio interno':}")
    print(f"  {'Spread%':>7} {'PMin':>6} {'PMax':>6} {'N':>4}  Mercado")
    print("  " + "-" * 70)
    for case in slippage_cases[:10]:
        print(f"  {case['spread_pct']:6.1f}%  {case['price_min']:.3f}  {case['price_max']:.3f}"
              f"  {case['n_buys']:3d}  {case['title']}")

    # Distribution of fills by price bucket (detailed)
    print(f"\nDistribución de fills por rango de precio (USDC ponderado):")
    edges = [0, 0.2, 0.35, 0.5, 0.65, 0.8, 1.01]
    labels = ["0.00-0.20", "0.20-0.35", "0.35-0.50", "0.50-0.65", "0.65-0.80", "0.80-1.00"]
    bucket_usdc = defaultdict(float)
    bucket_n    = defaultdict(int)
    for p, u in zip(all_prices, all_usdc):
        for i in range(len(edges) - 1):
            if edges[i] <= p < edges[i + 1]:
                bucket_usdc[labels[i]] += u
                bucket_n[labels[i]]    += 1
                break
    for lbl in labels:
        if bucket_n[lbl] > 0:
            print(f"  {lbl}  n={bucket_n[lbl]:4d}  USDC=${bucket_usdc[lbl]:7.2f}  avg=${bucket_usdc[lbl]/bucket_n[lbl]:.2f}")

    if save:
        _save_analysis_csv(slippage_cases, "analysis_slippage_by_market.csv")


# ---------------------------------------------------------------------------
# 5. Posiciones abiertas con valor de mercado
# ---------------------------------------------------------------------------

def analysis_open_positions(positions: list[dict], save: bool) -> None:
    """
    Filtra posiciones con currentValue > 0 o redeemable=True.
    Muestra el estado actual del portafolio abierto.
    """
    _header("5. POSICIONES ABIERTAS / REDIMIBLES")

    redeemable = [p for p in positions if p.get("redeemable", "").lower() == "true"]
    open_pos   = [p for p in positions if _safe_float(p.get("currentValue")) > 0
                  and p.get("redeemable", "").lower() != "true"]
    all_active = redeemable + open_pos

    total_cv           = sum(_safe_float(p.get("currentValue")) for p in all_active)
    total_iv           = sum(_safe_float(p.get("initialValue")) for p in all_active)
    total_redeemable_v = sum(_safe_float(p.get("currentValue")) for p in redeemable)

    print(f"\nPosiciones redimibles (redeemable=True): {len(redeemable)}")
    print(f"Posiciones abiertas con valor > 0:       {len(open_pos)}")
    print(f"\nValor total redimible:  ${total_redeemable_v:.2f}")
    print(f"Valor total portafolio: ${total_cv:.2f}")
    print(f"Costo total (initial):  ${total_iv:.2f}")
    print(f"PnL no realizado:       ${total_cv - total_iv:+.2f}")

    # Sort by currentValue desc
    all_active.sort(key=lambda x: _safe_float(x.get("currentValue")), reverse=True)

    print(f"\n{'curPrice':>8} {'curValue':>9} {'initVal':>8} {'PnL':>7}  Outcome  Mercado")
    print("  " + "-" * 80)
    rows_out = []
    for p in all_active[:30]:
        cv   = _safe_float(p.get("currentValue"))
        iv   = _safe_float(p.get("initialValue"))
        pnl  = cv - iv
        flag = " 🔴" if p.get("redeemable") == "True" else ""
        print(f"  {_safe_float(p.get('curPrice')):7.3f}  ${cv:7.2f}  ${iv:6.2f}  {pnl:+6.2f}"
              f"  {p.get('outcome',''):5}    {p.get('title','')[:45]}{flag}")
        rows_out.append({
            "title":         p.get("title", ""),
            "outcome":       p.get("outcome", ""),
            "curPrice":      p.get("curPrice"),
            "currentValue":  p.get("currentValue"),
            "initialValue":  p.get("initialValue"),
            "pnl_usdc":      round(pnl, 4),
            "redeemable":    p.get("redeemable"),
            "endDate":       p.get("endDate"),
            "size":          p.get("size"),
            "avgPrice":      p.get("avgPrice"),
        })

    if save:
        _save_analysis_csv(rows_out, "analysis_open_positions.csv")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Análisis de actividad Polymarket — 5 dimensiones")
    parser.add_argument("--since", default="", help="Filtrar desde fecha UTC (YYYY-MM-DD), ej: 2026-03-04")
    parser.add_argument("--save", action="store_true", help="Guardar resultados como CSV en backtest_output/")
    args = parser.parse_args()

    # Load files
    act_file = _latest_file("polymarket_activity_*.csv")
    pos_file = _latest_file("polymarket_positions_*.csv")

    if not act_file or not pos_file:
        print("ERROR: No se encontraron archivos de actividad.")
        print("Corre primero: python3 scripts/export_polymarket_activity.py")
        sys.exit(1)

    print(f"Leyendo: {act_file.name}")
    print(f"Leyendo: {pos_file.name}")

    activity  = _load_csv(act_file)
    positions = _load_csv(pos_file)

    since_dt: datetime | None = None
    if args.since:
        since_dt = datetime.fromisoformat(args.since).replace(tzinfo=timezone.utc)
        print(f"Filtrando desde: {since_dt.date()} UTC")

    print(f"\nActivity rows: {len(activity)}, Positions rows: {len(positions)}")

    # Run all analyses
    analysis_pnl_by_market(activity, positions, since_dt, args.save)
    analysis_fill_distribution(activity, since_dt, args.save)
    analysis_by_hour(activity, since_dt, args.save)
    analysis_slippage(activity, since_dt, args.save)
    analysis_open_positions(positions, args.save)

    print(f"\n{'='*60}")
    print("  Análisis completo.")
    if args.save:
        print(f"  Resultados guardados en: {OUTPUT_DIR}/analysis_*.csv")
    else:
        print("  Usa --save para exportar resultados a CSV.")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
