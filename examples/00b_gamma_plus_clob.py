"""
Ejemplo completo: Gamma API + CLOB API
1. Usar Gamma API para encontrar mercados activos
2. Usar CLOB API para ver orderbooks y tradear
"""
import requests
from py_clob_client.client import ClobClient

# APIs
GAMMA_API = "https://gamma-api.polymarket.com"
clob_client = ClobClient("https://clob.polymarket.com")

print("=" * 70)
print("FLUJO COMPLETO: GAMMA API → CLOB API")
print("=" * 70)
print()

# PASO 1: Usar Gamma API para encontrar mercados activos
print("PASO 1: Obtener mercados activos con GAMMA API")
print("-" * 70)

params = {
    'active': 'true',
    'closed': 'false',
    'limit': 5  # Solo 5 eventos
}

response = requests.get(f"{GAMMA_API}/events", params=params)
events = response.json()

print(f"✓ Encontrados {len(events)} eventos activos")
print()

# Tomar el primer evento con mercados
selected_event = None
selected_market = None

for event in events:
    markets = event.get('markets', [])
    if markets and len(markets) > 0:
        selected_event = event
        selected_market = markets[0]  # Primer mercado del evento
        break

if not selected_market:
    print("No se encontraron mercados activos")
    exit(1)

print(f"📊 Evento seleccionado:")
print(f"   {selected_event.get('title', 'N/A')}")
print()

print(f"📊 Mercado seleccionado:")
question = selected_market.get('question', 'N/A')
condition_id = selected_market.get('conditionId', 'N/A')
print(f"   {question}")
print(f"   Condition ID: {condition_id}")
print()

# Mostrar tokens del mercado
tokens = selected_market.get('tokens', [])
print(f"   Opciones ({len(tokens)}):")
for token in tokens:
    outcome = token.get('outcome', 'N/A')
    token_id = token.get('token_id', 'N/A')
    price = token.get('price', None)

    if price:
        price_float = float(price)
        print(f"     • {outcome}: ${price_float:.4f} ({price_float*100:.1f}%)")
        print(f"       Token ID: {token_id}")
    else:
        print(f"     • {outcome}: Sin precio")
        print(f"       Token ID: {token_id}")

print()
print("=" * 70)
print()

# PASO 2: Usar CLOB API para obtener orderbook detallado
print("PASO 2: Obtener orderbook con CLOB API")
print("-" * 70)

if not tokens:
    print("No hay tokens para analizar")
    exit(1)

# Tomar primer token
first_token = tokens[0]
token_id = first_token.get('token_id')
outcome = first_token.get('outcome', 'Unknown')

print(f"Analizando: {outcome}")
print(f"Token ID: {token_id}")
print()

try:
    # Obtener orderbook del CLOB
    orderbook = clob_client.get_order_book(token_id)

    bids = orderbook.get('bids', [])
    asks = orderbook.get('asks', [])

    if not bids and not asks:
        print("⚠️  No hay orderbook disponible para este token")
        print("   (El mercado puede no tener órdenes activas todavía)")
    else:
        # Calcular estadísticas
        best_bid = float(bids[0]['price']) if bids else 0
        best_ask = float(asks[0]['price']) if asks else 0
        spread = best_ask - best_bid if best_bid and best_ask else 0
        mid_price = (best_bid + best_ask) / 2 if best_bid and best_ask else 0

        print("💰 PRECIOS:")
        print(f"   Mejor BID (Compra): ${best_bid:.4f}")
        print(f"   Mejor ASK (Venta):  ${best_ask:.4f}")
        print(f"   Precio medio:       ${mid_price:.4f}")
        print(f"   Spread:             ${spread:.4f} ({spread/mid_price*100:.2f}%)" if mid_price > 0 else "")
        print()

        # Mostrar orderbook
        print("📗 TOP 3 BIDS (Órdenes de Compra):")
        for i, bid in enumerate(bids[:3], 1):
            price = float(bid['price'])
            size = float(bid['size'])
            print(f"   {i}. ${price:.4f} x ${size:.2f}")

        print()
        print("📕 TOP 3 ASKS (Órdenes de Venta):")
        for i, ask in enumerate(asks[:3], 1):
            price = float(ask['price'])
            size = float(ask['size'])
            print(f"   {i}. ${price:.4f} x ${size:.2f}")

        print()

        # Análisis de oportunidad
        print("🔍 ANÁLISIS DE OPORTUNIDAD:")
        if spread / mid_price > 0.05 if mid_price > 0 else False:
            print(f"   ⚠️  Spread alto ({spread/mid_price*100:.2f}%) - Baja liquidez")
        else:
            print(f"   ✓ Spread razonable ({spread/mid_price*100:.2f}%)")

        if mid_price < 0.30:
            print(f"   💡 Precio bajo - Mercado favorece 'No' ({(1-mid_price)*100:.1f}% prob)")
        elif mid_price > 0.70:
            print(f"   💡 Precio alto - Mercado favorece 'Sí' ({mid_price*100:.1f}% prob)")
        else:
            print(f"   💡 Precio equilibrado - Resultado incierto")

except Exception as e:
    print(f"⚠️  Error obteniendo orderbook: {e}")
    print("   (Este token puede no tener órdenes activas)")

print()
print("=" * 70)
print()
print("✅ FLUJO COMPLETADO")
print()
print("RESUMEN DEL FLUJO:")
print()
print("1. Gamma API → Encontrar eventos y mercados activos")
print("   • Filtra por activo/cerrado")
print("   • Devuelve metadata completa")
print("   • Incluye precios estimados")
print()
print("2. CLOB API → Obtener detalles de trading")
print("   • Orderbook en tiempo real")
print("   • Precios exactos de bids/asks")
print("   • Listo para ejecutar trades")
print()
print("PARA TRADING:")
print("  • Usa Gamma API para encontrar oportunidades")
print("  • Usa CLOB API para ejecutar trades")
print("  • Combina ambas en tu estrategia")
print()
