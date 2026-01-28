"""
FLUJO COMPLETO: Explorar mercados activos y ver orderbooks
Usa Gamma API para datos de mercados + CLOB API para orderbooks
"""
import requests
from py_clob_client.client import ClobClient
import json

# APIs
GAMMA_API = "https://gamma-api.polymarket.com"
clob_client = ClobClient("https://clob.polymarket.com")

print("=" * 70)
print("EXPLORACIÓN COMPLETA DE MERCADOS ACTIVOS")
print("Gamma API (datos) + CLOB API (orderbooks)")
print("=" * 70)
print()

# PASO 1: Obtener mercados activos de Gamma API
print("PASO 1: Obtener mercados activos (Gamma API)")
print("-" * 70)

params = {
    'active': 'true',
    'closed': 'false',
    'limit': 5
}

response = requests.get(f"{GAMMA_API}/markets", params=params)
markets = response.json()

print(f"✓ Encontrados {len(markets)} mercados activos")
print()

# PASO 2: Mostrar mercados con precios
print("PASO 2: Mercados con precios actuales")
print("-" * 70)
print()

for i, market in enumerate(markets, 1):
    question = market.get('question', 'N/A')
    condition_id = market.get('conditionId', 'N/A')

    # Parsear outcomes y precios (vienen como strings JSON)
    outcomes_str = market.get('outcomes', '[]')
    prices_str = market.get('outcomePrices', '[]')

    try:
        outcomes = json.loads(outcomes_str) if isinstance(outcomes_str, str) else outcomes_str
        prices = json.loads(prices_str) if isinstance(prices_str, str) else prices_str
    except:
        outcomes = []
        prices = []

    # Token IDs
    token_ids_str = market.get('clobTokenIds', '[]')
    try:
        token_ids = json.loads(token_ids_str) if isinstance(token_ids_str, str) else token_ids_str
    except:
        token_ids = []

    # Estadísticas
    volume_24h = float(market.get('volume24hr', 0))
    liquidity = float(market.get('liquidityClob', 0))
    best_bid = market.get('bestBid', 'N/A')
    best_ask = market.get('bestAsk', 'N/A')

    print(f"{i}. {question[:65]}...")
    print()
    print(f"   📊 Opciones y Probabilidades:")

    for j, outcome in enumerate(outcomes):
        price = float(prices[j]) if j < len(prices) else 0
        token_id = token_ids[j] if j < len(token_ids) else 'N/A'

        prob_pct = price * 100
        print(f"      • {outcome}: ${price:.4f} ({prob_pct:.1f}% probabilidad)")
        print(f"        Token ID: {str(token_id)[:30]}...")

    print()
    print(f"   📈 Estadísticas:")
    print(f"      • Volumen 24h: ${volume_24h:,.2f}")
    print(f"      • Liquidez: ${liquidity:,.2f}")
    print(f"      • Best Bid: {best_bid}")
    print(f"      • Best Ask: {best_ask}")
    print()

print("=" * 70)
print()

# PASO 3: Seleccionar un mercado y ver orderbook en CLOB API
print("PASO 3: Orderbook detallado (CLOB API)")
print("-" * 70)

# Tomar el primer mercado que tenga token IDs
selected_market = None
selected_token_id = None

for market in markets:
    token_ids_str = market.get('clobTokenIds', '[]')
    try:
        token_ids = json.loads(token_ids_str) if isinstance(token_ids_str, str) else token_ids_str
        if token_ids and len(token_ids) > 0:
            selected_market = market
            selected_token_id = token_ids[0]
            break
    except:
        continue

if selected_market and selected_token_id:
    question = selected_market.get('question', 'N/A')
    outcomes_str = selected_market.get('outcomes', '[]')
    outcomes = json.loads(outcomes_str) if isinstance(outcomes_str, str) else outcomes_str

    print(f"Mercado: {question[:50]}...")
    print(f"Token: {outcomes[0] if outcomes else 'Unknown'}")
    print(f"Token ID: {str(selected_token_id)[:40]}...")
    print()

    try:
        # Obtener orderbook del CLOB
        orderbook = clob_client.get_order_book(str(selected_token_id))

        # OrderBookSummary tiene atributos .bids y .asks
        bids = orderbook.bids if hasattr(orderbook, 'bids') else []
        asks = orderbook.asks if hasattr(orderbook, 'asks') else []

        if bids or asks:
            print("📗 BIDS (Órdenes de Compra) - Top 5:")
            if bids:
                for bid in bids[:5]:
                    price = float(bid.price)
                    size = float(bid.size)
                    total = price * size
                    print(f"   ${price:.4f} x {size:,.2f} shares = ${total:,.2f}")
            else:
                print("   (Sin órdenes de compra)")

            print()
            print("📕 ASKS (Órdenes de Venta) - Top 5:")
            if asks:
                for ask in asks[:5]:
                    price = float(ask.price)
                    size = float(ask.size)
                    total = price * size
                    print(f"   ${price:.4f} x {size:,.2f} shares = ${total:,.2f}")
            else:
                print("   (Sin órdenes de venta)")

            print()

            # Calcular spread si hay ambos
            if bids and asks:
                best_bid = float(bids[0].price)
                best_ask = float(asks[0].price)
                spread = best_ask - best_bid
                mid = (best_bid + best_ask) / 2

                print("💰 RESUMEN DE PRECIOS:")
                print(f"   Best Bid (Compra): ${best_bid:.4f}")
                print(f"   Best Ask (Venta):  ${best_ask:.4f}")
                print(f"   Spread:            ${spread:.4f} ({spread/mid*100:.2f}%)" if mid > 0 else "")
                print(f"   Mid Price:         ${mid:.4f}")
                print()
                print(f"   Total Bids: {len(bids)} órdenes")
                print(f"   Total Asks: {len(asks)} órdenes")

                # Información adicional
                if hasattr(orderbook, 'last_trade_price'):
                    print(f"   Último precio: ${float(orderbook.last_trade_price):.4f}")
        else:
            print("⚠️  No hay orderbook activo para este token")

    except Exception as e:
        print(f"⚠️  Error obteniendo orderbook: {e}")
else:
    print("⚠️  No se encontraron mercados con token IDs válidos")

print()
print("=" * 70)
print()
print("✅ EXPLORACIÓN COMPLETADA")
print()
print("RESUMEN DEL FLUJO:")
print()
print("1. GAMMA API (/markets):")
print("   → Lista mercados activos/abiertos")
print("   → Precios actuales (outcomePrices)")
print("   → Token IDs (clobTokenIds)")
print("   → Estadísticas (volumen, liquidez)")
print()
print("2. CLOB API (get_order_book):")
print("   → Orderbook en tiempo real")
print("   → Bids y Asks detallados")
print("   → Para ejecutar trades")
print()
print("PARA TU BOT:")
print("   • Usa Gamma API para encontrar oportunidades")
print("   • Usa CLOB API para ejecutar trades")
print()
