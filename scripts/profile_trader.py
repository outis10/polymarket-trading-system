"""
Análisis de perfil de trader externo en Polymarket.

Uso:
    python3 scripts/profile_trader.py 0xABCD...
    python3 scripts/profile_trader.py 0xABCD... --json      # output JSON crudo también
    python3 scripts/profile_trader.py 0xABCD... --limit 200 # más actividad (default 100)
"""

import argparse
import json
import sys
from collections import Counter, defaultdict
from statistics import mean, median

import urllib.request
import urllib.error

BASE = "https://data-api.polymarket.com"


def fetch(url: str) -> list | dict | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise
    except Exception as e:
        print(f"  Error fetching {url}: {e}", file=sys.stderr)
        return None


def analyze(address: str, limit: int = 100, show_json: bool = False):
    address = address.lower()
    print(f"\n{'='*60}")
    print(f"Trader: {address}")
    print(f"{'='*60}")

    # ── Fetch ────────────────────────────────────────────────────
    positions = fetch(f"{BASE}/positions?user={address}&sizeThreshold=.1&limit=500") or []
    activity  = fetch(f"{BASE}/activity?user={address}&limit={limit}") or []
    profile   = fetch(f"{BASE}/profile?address={address}")

    if show_json:
        print("\n--- POSITIONS (raw) ---")
        print(json.dumps(positions[:5], indent=2))
        print("\n--- ACTIVITY (raw, first 5) ---")
        print(json.dumps(activity[:5], indent=2))

    # ── Profile ──────────────────────────────────────────────────
    name = "unknown"
    if profile and isinstance(profile, dict):
        name = profile.get("name") or profile.get("username") or profile.get("pseudonym") or "unknown"
    print(f"\nNombre: {name}")

    # ── Positions ────────────────────────────────────────────────
    if positions:
        total_initial = sum(float(p.get("initialValue") or p.get("size", 0) * float(p.get("avgPrice", 0)) or 0) for p in positions)
        total_current = sum(float(p.get("currentValue") or 0) for p in positions)
        total_pnl     = sum(float(p.get("cashPnl") or p.get("pnl") or 0) for p in positions)
        redeemable    = sum(1 for p in positions if p.get("redeemable"))
        n_pos         = len(positions)

        avg_prices = [float(p["avgPrice"]) for p in positions if p.get("avgPrice")]
        outcomes   = Counter(p.get("outcome", "?") for p in positions)
        markets    = Counter()
        for p in positions:
            title = p.get("title", "")
            if "Bitcoin" in title or "BTC" in title:
                markets["BTC"] += 1
            elif "Ethereum" in title or "ETH" in title:
                markets["ETH"] += 1
            elif "Solana" in title or "SOL" in title:
                markets["SOL"] += 1
            else:
                markets["Other"] += 1

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

        # Price distribution
        buckets = defaultdict(int)
        for p in avg_prices:
            b = int(p * 10) / 10
            buckets[f"{b:.1f}–{b+0.1:.1f}"] += 1
        print("  Dist. precios:   " + "  ".join(f"{k}:{v}" for k, v in sorted(buckets.items())))
    else:
        print("\n  Sin posiciones abiertas.")

    # ── Activity ─────────────────────────────────────────────────
    if not activity:
        print("\n  Sin actividad reciente.")
        return

    # Normalize field names (polymarket uses different keys)
    def get_side(a):
        return (a.get("side") or a.get("outcome") or "?").upper()

    def get_price(a):
        try:
            return float(a.get("price") or a.get("usdcSize", 0) / max(float(a.get("size", 1)), 1e-9))
        except:
            return None

    def get_type(a):
        return (a.get("type") or a.get("tradeType") or "?").upper()

    def get_usdc(a):
        try:
            return float(a.get("usdcSize") or a.get("amount") or 0)
        except:
            return 0.0

    def get_asset(a):
        title = a.get("title", "") or a.get("market", "")
        if "Bitcoin" in title or "BTC" in title: return "BTC"
        if "Ethereum" in title or "ETH" in title: return "ETH"
        if "Solana" in title or "SOL" in title: return "SOL"
        return "Other"

    def get_tf(a):
        title = a.get("title", "") or ""
        if "15" in title: return "15m"
        if "60" in title or "1H" in title: return "60m"
        return "5m"

    types   = Counter(get_type(a) for a in activity)
    sides   = Counter(get_side(a) for a in activity if get_type(a) == "BUY")
    assets  = Counter(get_asset(a) for a in activity)
    tfs     = Counter(get_tf(a) for a in activity)
    prices  = [p for a in activity if (p := get_price(a)) is not None and 0 < p <= 1]
    usdcs   = [u for a in activity if (u := get_usdc(a)) > 0]

    # Timing
    timestamps = []
    for a in activity:
        ts = a.get("timestamp") or a.get("createdAt") or a.get("time")
        if ts:
            try:
                timestamps.append(int(ts) if str(ts).isdigit() else int(float(ts)))
            except:
                pass
    timestamps.sort()

    duration_min = (timestamps[-1] - timestamps[0]) / 60 if len(timestamps) > 1 else 0
    gaps = [timestamps[i+1] - timestamps[i] for i in range(len(timestamps)-1)]
    min_gap = min(gaps) if gaps else 0
    avg_gap = mean(gaps) if gaps else 0

    # Simultaneous trades (same second)
    ts_counter = Counter(timestamps)
    simultaneous = sum(1 for t, c in ts_counter.items() if c > 1)

    # Redeems
    redeems = [a for a in activity if "REDEEM" in get_type(a) or "MERGE" in get_type(a)]
    winning_redeems = [a for a in redeems if get_usdc(a) > 0]

    print(f"\n── ACTIVIDAD ({len(activity)} trades) ──────────────────────")
    print(f"  Ventana:         {duration_min:.0f} min")
    print(f"  Tipos:           {dict(types)}")
    print(f"  Lados (BUYs):    {dict(sides)}")
    print(f"  Activos:         {dict(assets)}")
    print(f"  Timeframes:      {dict(tfs)}")
    if prices:
        print(f"  Precio entrada:  avg={mean(prices):.3f}  min={min(prices):.3f}  max={max(prices):.3f}")
    if usdcs:
        print(f"  USDC por trade:  avg=${mean(usdcs):.2f}  total=${sum(usdcs):.2f}")
    print(f"  Gap entre trades: min={min_gap:.0f}s  avg={avg_gap:.0f}s")
    print(f"  Trades simultán.: {simultaneous} timestamps con >1 trade")
    if redeems:
        wr = len(winning_redeems) / len(redeems) * 100
        print(f"  Redeems:         {len(redeems)} total  win rate={wr:.0f}% ({len(winning_redeems)}/{len(redeems)})")

    # ── Strategy fingerprint ─────────────────────────────────────
    print(f"\n── FINGERPRINT ─────────────────────────────────────────")

    is_bot      = simultaneous > 3 or (min_gap <= 3 and len(activity) > 20)
    only_buys   = types.get("BUY", 0) > 0 and types.get("SELL", 0) == 0
    high_prob   = prices and mean(prices) > 0.80
    low_prob    = prices and mean(prices) < 0.45
    scalper     = duration_min > 0 and len(activity) / duration_min > 1.5
    multi_asset = len([k for k, v in assets.items() if v > 2 and k != "Other"]) >= 2

    flags = []
    if is_bot:        flags.append("🤖 BOT (trades simultáneos / gaps <3s)")
    if only_buys:     flags.append("📥 Solo compras (no vende)")
    if high_prob:     flags.append(f"🎯 Alta prob (avg {mean(prices):.2f}) — compra favorito")
    if low_prob:      flags.append(f"🎲 Baja prob (avg {mean(prices):.2f}) — apuesta al underdog")
    if scalper:       flags.append(f"⚡ Scalper ({len(activity)/max(duration_min,1):.1f} trades/min)")
    if multi_asset:   flags.append("🔀 Multi-activo simultáneo")
    if not only_buys and prices:
        buy_ps  = [get_price(a) for a in activity if get_type(a)=="BUY"  and get_price(a)]
        sell_ps = [get_price(a) for a in activity if get_type(a)=="SELL" and get_price(a)]
        if buy_ps and sell_ps and mean(buy_ps) > mean(sell_ps) + 0.05:
            flags.append(f"⚠️  Compra alto ({mean(buy_ps):.2f}), vende bajo ({mean(sell_ps):.2f}) — patrón perdedor")

    for f in flags:
        print(f"  {f}")
    if not flags:
        print("  Sin patrón claro con los datos disponibles")

    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Analiza el perfil de un trader de Polymarket")
    parser.add_argument("address", help="Dirección Ethereum (0x...)")
    parser.add_argument("--limit", type=int, default=100, help="Número de actividades a traer (default 100)")
    parser.add_argument("--json", action="store_true", help="Mostrar JSON crudo (primeros 5 items)")
    args = parser.parse_args()

    analyze(args.address, limit=args.limit, show_json=args.json)
