"""
Análisis de perfil de trader externo en Polymarket.

Uso:
    python3 scripts/profile_trader.py 0xABCD...
    python3 scripts/profile_trader.py 0xABCD... --limit 200
    python3 scripts/profile_trader.py 0xABCD... --json

    # Buscar bots ganadores en tus propios mercados:
    python3 scripts/profile_trader.py --find-winners
    python3 scripts/profile_trader.py --find-winners --markets 30 --min-wr 65 --min-vol 300
"""

import argparse
import csv
import json
import os
import sys
import time
from collections import Counter, defaultdict
from statistics import mean, median

import urllib.request
import urllib.error

BASE     = "https://data-api.polymarket.com"
BOT_CSVS = [
    "backtest_output_v2/bot_orders_2026-03-24.csv",
    "backtest_output_v2/bot_orders_2026-03-23.csv",
    "backtest_output/bot_orders_2026-03-24.csv",
    "backtest_output/bot_orders_2026-03-23.csv",
]


def fetch(url: str, silent: bool = False) -> list | dict | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        if not silent:
            print(f"  HTTP {e.code}: {url}", file=sys.stderr)
        return None
    except Exception as e:
        if not silent:
            print(f"  Error: {e}", file=sys.stderr)
        return None


# ── Core analysis ─────────────────────────────────────────────────────────────

def analyze(address: str, limit: int = 100, show_json: bool = False) -> dict:
    """Fetch and analyze a trader. Returns summary dict for --find-winners."""
    address = address.lower()
    print(f"\n{'='*60}")
    print(f"Trader: {address}")
    print(f"{'='*60}")

    positions = fetch(f"{BASE}/positions?user={address}&sizeThreshold=.1&limit=500") or []
    activity  = fetch(f"{BASE}/activity?user={address}&limit={limit}") or []
    profile   = fetch(f"{BASE}/profile?address={address}")

    if show_json:
        print("\n--- POSITIONS (raw, first 5) ---")
        print(json.dumps(positions[:5], indent=2))
        print("\n--- ACTIVITY (raw, first 5) ---")
        print(json.dumps(activity[:5], indent=2))

    # ── Profile ──────────────────────────────────────────────────
    name = "unknown"
    if profile and isinstance(profile, dict):
        name = (profile.get("name") or profile.get("username")
                or profile.get("pseudonym") or "unknown")
    print(f"\nNombre: {name}")

    # ── Positions ────────────────────────────────────────────────
    pos_summary = {}
    if positions:
        total_initial = sum(float(p.get("initialValue") or 0) for p in positions)
        total_current = sum(float(p.get("currentValue") or 0) for p in positions)
        total_pnl     = sum(float(p.get("cashPnl") or 0) for p in positions)
        redeemable    = sum(1 for p in positions if p.get("redeemable"))
        n_pos         = len(positions)
        avg_prices    = [float(p["avgPrice"]) for p in positions if p.get("avgPrice")]
        outcomes      = Counter(p.get("outcome", "?") for p in positions)
        markets       = Counter()
        for p in positions:
            title = p.get("title", "")
            if "Bitcoin" in title or "BTC" in title:   markets["BTC"] += 1
            elif "Ethereum" in title or "ETH" in title: markets["ETH"] += 1
            elif "Solana" in title or "SOL" in title:   markets["SOL"] += 1
            else:                                        markets["Other"] += 1

        pnl_pct = (total_pnl / total_initial * 100) if total_initial > 0 else 0
        print(f"\n── POSICIONES ({n_pos}) ──────────────────────────")
        print(f"  Invertido:       ${total_initial:,.2f}")
        print(f"  Valor actual:    ${total_current:,.2f}")
        print(f"  PnL no realiz.:  ${total_pnl:+,.2f} ({pnl_pct:+.1f}%)")
        print(f"  Redeemable:      {redeemable}/{n_pos}")
        if avg_prices:
            print(f"  Precio avg:      {mean(avg_prices):.3f}  (med {median(avg_prices):.3f})")
        print(f"  Outcomes:        {dict(outcomes)}")
        print(f"  Mercados:        {dict(markets)}")
        buckets = defaultdict(int)
        for p in avg_prices:
            b = int(p * 10) / 10
            buckets[f"{b:.1f}–{b+0.1:.1f}"] += 1
        print("  Dist. precios:   " + "  ".join(f"{k}:{v}" for k, v in sorted(buckets.items())))
        pos_summary = {"pnl_pct": pnl_pct, "n_pos": n_pos}
    else:
        print("\n  Sin posiciones abiertas.")

    # ── Activity ─────────────────────────────────────────────────
    if not activity:
        print("\n  Sin actividad reciente.")
        return {}

    def get_type(a):  return (a.get("type") or a.get("tradeType") or "?").upper()
    def get_price(a):
        try: return float(a.get("price") or a.get("usdcSize", 0) / max(float(a.get("size", 1)), 1e-9))
        except: return None
    def get_usdc(a):
        try: return float(a.get("usdcSize") or a.get("amount") or 0)
        except: return 0.0
    def get_asset(a):
        t = a.get("title", "") or a.get("market", "")
        if "Bitcoin" in t or "BTC" in t: return "BTC"
        if "Ethereum" in t or "ETH" in t: return "ETH"
        if "Solana" in t or "SOL" in t: return "SOL"
        return "Other"
    def get_tf(a):
        t = a.get("title", "") or ""
        if "15" in t: return "15m"
        if "60" in t or "1H" in t: return "60m"
        return "5m"

    types  = Counter(get_type(a) for a in activity)
    assets = Counter(get_asset(a) for a in activity)
    tfs    = Counter(get_tf(a) for a in activity)
    prices = [p for a in activity if (p := get_price(a)) is not None and 0 < p <= 1]
    usdcs  = [u for a in activity if (u := get_usdc(a)) > 0]

    timestamps = []
    for a in activity:
        ts = a.get("timestamp") or a.get("createdAt") or a.get("time")
        if ts:
            try: timestamps.append(int(ts) if str(ts).isdigit() else int(float(ts)))
            except: pass
    timestamps.sort()

    duration_min = (timestamps[-1] - timestamps[0]) / 60 if len(timestamps) > 1 else 0
    gaps         = [timestamps[i+1] - timestamps[i] for i in range(len(timestamps)-1)]
    min_gap      = min(gaps) if gaps else 0
    avg_gap      = mean(gaps) if gaps else 0
    simultaneous = sum(1 for c in Counter(timestamps).values() if c > 1)

    redeems         = [a for a in activity if "REDEEM" in get_type(a) or "MERGE" in get_type(a)]
    winning_redeems = [a for a in redeems if get_usdc(a) > 0]
    win_rate        = len(winning_redeems) / len(redeems) * 100 if redeems else 0
    total_vol       = sum(usdcs)

    print(f"\n── ACTIVIDAD ({len(activity)} trades) ──────────────────────")
    print(f"  Ventana:         {duration_min:.0f} min")
    print(f"  Tipos:           {dict(types)}")
    print(f"  Activos:         {dict(assets)}")
    print(f"  Timeframes:      {dict(tfs)}")
    if prices:
        print(f"  Precio entrada:  avg={mean(prices):.3f}  min={min(prices):.3f}  max={max(prices):.3f}")
    if usdcs:
        print(f"  USDC por trade:  avg=${mean(usdcs):.2f}  total=${total_vol:.2f}")
    print(f"  Gap entre trades: min={min_gap:.0f}s  avg={avg_gap:.0f}s")
    print(f"  Trades simultán.: {simultaneous} timestamps con >1 trade")
    if redeems:
        print(f"  Redeems:         {len(redeems)} total  win rate={win_rate:.0f}% ({len(winning_redeems)}/{len(redeems)})")

    # ── Fingerprint ───────────────────────────────────────────────
    print(f"\n── FINGERPRINT ─────────────────────────────────────────")
    is_bot     = simultaneous > 3 or (min_gap <= 3 and len(activity) > 20)
    only_buys  = types.get("BUY", 0) > 0 and types.get("SELL", 0) == 0
    high_prob  = prices and mean(prices) > 0.80
    low_prob   = prices and mean(prices) < 0.45
    scalper    = duration_min > 0 and len(activity) / duration_min > 1.5
    multi_asset= len([k for k, v in assets.items() if v > 2 and k != "Other"]) >= 2

    flags = []
    if is_bot:      flags.append("🤖 BOT (trades simultáneos / gaps <3s)")
    if only_buys:   flags.append("📥 Solo compras (no vende)")
    if high_prob:   flags.append(f"🎯 Alta prob (avg {mean(prices):.2f}) — compra favorito")
    if low_prob:    flags.append(f"🎲 Baja prob (avg {mean(prices):.2f}) — apuesta al underdog")
    if scalper:     flags.append(f"⚡ Scalper ({len(activity)/max(duration_min,1):.1f} trades/min)")
    if multi_asset: flags.append("🔀 Multi-activo simultáneo")
    buy_ps  = [get_price(a) for a in activity if get_type(a)=="BUY"  and get_price(a)]
    sell_ps = [get_price(a) for a in activity if get_type(a)=="SELL" and get_price(a)]
    if buy_ps and sell_ps and mean(buy_ps) > mean(sell_ps) + 0.05:
        flags.append(f"⚠️  Compra alto ({mean(buy_ps):.2f}), vende bajo ({mean(sell_ps):.2f}) — patrón perdedor")

    for f in flags: print(f"  {f}")
    if not flags:   print("  Sin patrón claro con los datos disponibles")
    print()

    return {
        "address": address,
        "win_rate": win_rate,
        "n_redeems": len(redeems),
        "total_vol": total_vol,
        "avg_price": mean(prices) if prices else 0,
        "is_bot": is_bot,
        "n_trades": len(activity),
        **pos_summary,
    }


# ── Find winners ──────────────────────────────────────────────────────────────

def find_winners(n_markets: int = 20, min_wr: float = 60.0,
                 min_vol: float = 200.0, min_redeems: int = 5,
                 activity_limit: int = 100):
    """
    1. Extrae token_ids de tus CSVs (placed orders)
    2. Busca otros traders que operaron en esos mercados via data-api/trades
    3. Corre analyze() en cada uno y filtra por win_rate / volumen
    """
    print(f"\n🔍 Buscando traders en tus últimos {n_markets} mercados...")
    print(f"   Filtros: win_rate≥{min_wr}%  vol≥${min_vol}  redeems≥{min_redeems}\n")

    # Collect token_ids from CSVs
    token_ids = []
    seen = set()
    for csv_path in BOT_CSVS:
        if not os.path.exists(csv_path):
            continue
        try:
            with open(csv_path) as f:
                for r in csv.DictReader(f):
                    tid = r.get("token_id", "")
                    if tid and tid not in seen and r.get("status") == "placed":
                        token_ids.append(tid)
                        seen.add(tid)
        except Exception:
            pass
        if len(token_ids) >= n_markets:
            break

    if not token_ids:
        print("❌ No se encontraron token_ids en los CSVs.")
        return

    token_ids = token_ids[:n_markets]
    print(f"  Escaneando {len(token_ids)} token_ids...")

    # Collect addresses from trades
    addr_data = defaultdict(lambda: {"usdc": 0.0, "n": 0})
    OWN = set()  # skip our own wallet

    for i, tid in enumerate(token_ids):
        r = fetch(f"{BASE}/trades?token_id={tid}&limit=50", silent=True)
        if isinstance(r, list):
            for t in r:
                addr = t.get("proxyWallet", "")
                if not addr or not addr.startswith("0x") or len(addr) != 42:
                    continue
                addr = addr.lower()
                price = float(t.get("price") or 0)
                size  = float(t.get("size") or 0)
                usdc  = price * size
                addr_data[addr]["usdc"] += usdc
                addr_data[addr]["n"]    += 1
        time.sleep(0.05)  # be gentle with the API

    print(f"  Encontrados {len(addr_data)} addresses únicos\n")

    # Filter by minimum volume and rank
    candidates = [
        (addr, d) for addr, d in addr_data.items()
        if d["usdc"] >= min_vol and addr not in OWN
    ]
    candidates.sort(key=lambda x: -x[1]["usdc"])

    print(f"  Candidatos con vol≥${min_vol}: {len(candidates)}")
    print(f"  Analizando perfiles...\n")
    print("─" * 60)

    winners = []
    for addr, d in candidates[:30]:  # analyze top 30 by volume
        summary = analyze(addr, limit=activity_limit)
        if (summary.get("win_rate", 0) >= min_wr
                and summary.get("n_redeems", 0) >= min_redeems
                and summary.get("total_vol", 0) >= min_vol):
            winners.append(summary)
        time.sleep(0.1)

    # ── Final ranking ─────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("🏆 BOTS GANADORES ENCONTRADOS")
    print("=" * 60)
    if not winners:
        print("  Ninguno pasó los filtros. Prueba bajando --min-wr o --min-redeems.")
        return

    winners.sort(key=lambda x: (-x["win_rate"], -x["total_vol"]))
    for i, w in enumerate(winners, 1):
        print(f"\n#{i}  {w['address']}")
        print(f"     win_rate={w['win_rate']:.0f}%  redeems={w['n_redeems']}"
              f"  vol=${w['total_vol']:.0f}  avg_price={w['avg_price']:.3f}"
              f"  {'🤖' if w.get('is_bot') else '👤'}")


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Analiza traders de Polymarket")
    parser.add_argument("address", nargs="?", help="Dirección Ethereum (0x...)")
    parser.add_argument("--limit",       type=int,   default=100,  help="Actividades a traer (default 100)")
    parser.add_argument("--json",        action="store_true",       help="Mostrar JSON crudo")
    parser.add_argument("--find-winners",action="store_true",       help="Buscar bots ganadores en tus mercados")
    parser.add_argument("--markets",     type=int,   default=20,   help="N de mercados a escanear (default 20)")
    parser.add_argument("--min-wr",      type=float, default=60.0, help="Win rate mínimo %% (default 60)")
    parser.add_argument("--min-vol",     type=float, default=200.0,help="Volumen mínimo USD (default 200)")
    parser.add_argument("--min-redeems", type=int,   default=5,    help="Redeems mínimos (default 5)")
    args = parser.parse_args()

    if args.find_winners:
        find_winners(
            n_markets=args.markets,
            min_wr=args.min_wr,
            min_vol=args.min_vol,
            min_redeems=args.min_redeems,
            activity_limit=args.limit,
        )
    elif args.address:
        analyze(args.address, limit=args.limit, show_json=args.json)
    else:
        parser.print_help()
