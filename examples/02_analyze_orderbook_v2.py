"""
Analizar el libro de órdenes de mercados activos
"""
from py_clob_client.client import ClobClient

client = ClobClient("https://clob.polymarket.com")

print("🔍 Buscando mercados con orderbooks activos...")
print()

# Obtener mercados
markets_response = client.get_markets()

# Extraer datos
if isinstance(markets_response, dict):
    markets = markets_response.get('data', [])
else:
    markets = markets_response

print(f"Total mercados disponibles: {len(markets)}")
print()

# Buscar un mercado con orderbook activo
found = False
market_count = 0

for market in markets[:20]:  # Revisar primeros 20
    if found:
        break

    market_count += 1
    tokens = market.get('tokens', [])

    if not tokens:
        continue

    # Intentar con primer token
    token = tokens[0]
    token_id = token.get('token_id')
    outcome = token.get('outcome', 'Unknown')

    try:
        # Intentar obtener orderbook
        book = client.get_order_book(token_id)

        bids = book.get('bids', [])
        asks = book.get('asks', [])

        # Verificar si tiene órdenes
        if bids and asks:
            found = True
            question = market.get('question', 'N/A')

            print("=" * 70)
            print(f"📊 MERCADO ENCONTRADO")
            print("=" * 70)
            print()
            print(f"Pregunta: {question}")
            print(f"Token analizado: {outcome}")
            print(f"Token ID: {token_id[:30]}...")
            print()

            # Calcular precios
            best_bid = float(bids[0]['price']) if bids else 0
            best_ask = float(asks[0]['price']) if asks else 0
            mid_price = (best_bid + best_ask) / 2 if best_bid and best_ask else 0
            spread = best_ask - best_bid if best_bid and best_ask else 0

            print("💰 PRECIOS:")
            print(f"   Precio medio: ${mid_price:.4f}")
            print(f"   Mejor BID (Compra): ${best_bid:.4f}")
            print(f"   Mejor ASK (Venta): ${best_ask:.4f}")
            print(f"   Spread: ${spread:.4f} ({spread/mid_price*100:.2f}% del precio)" if mid_price > 0 else "")
            print()

            # Mostrar orderbook
            print("📗 TOP 5 BIDS (Órdenes de Compra):")
            print("   Precio      | Tamaño    | Total")
            print("   " + "-" * 40)
            for i, bid in enumerate(bids[:5], 1):
                price = float(bid['price'])
                size = float(bid['size'])
                total = price * size
                print(f"   ${price:.4f}  | ${size:8.2f} | ${total:8.2f}")

            print()
            print("📕 TOP 5 ASKS (Órdenes de Venta):")
            print("   Precio      | Tamaño    | Total")
            print("   " + "-" * 40)
            for i, ask in enumerate(asks[:5], 1):
                price = float(ask['price'])
                size = float(ask['size'])
                total = price * size
                print(f"   ${price:.4f}  | ${size:8.2f} | ${total:8.2f}")

            print()

            # Profundidad del mercado
            total_bid_size = sum(float(bid['size']) for bid in bids[:10])
            total_ask_size = sum(float(ask['size']) for ask in asks[:10])
            total_bid_value = sum(float(bid['price']) * float(bid['size']) for bid in bids[:10])
            total_ask_value = sum(float(ask['price']) * float(ask['size']) for ask in asks[:10])

            print("📊 PROFUNDIDAD DEL MERCADO (Top 10 órdenes):")
            print(f"   Total BID: ${total_bid_size:.2f} ({len(bids)} órdenes en total)")
            print(f"   Total ASK: ${total_ask_size:.2f} ({len(asks)} órdenes en total)")
            print(f"   Valor BID: ${total_bid_value:.2f}")
            print(f"   Valor ASK: ${total_ask_value:.2f}")
            print()

            # Análisis básico
            print("🔍 ANÁLISIS:")

            if spread / mid_price > 0.05:
                print(f"   ⚠️  Spread alto ({spread/mid_price*100:.2f}%) - baja liquidez")
            else:
                print(f"   ✓ Spread aceptable ({spread/mid_price*100:.2f}%)")

            if len(bids) < 10 or len(asks) < 10:
                print(f"   ⚠️  Pocas órdenes en el libro - baja actividad")
            else:
                print(f"   ✓ Buen número de órdenes ({len(bids)} bids, {len(asks)} asks)")

            if mid_price < 0.20:
                print(f"   💡 Precio bajo (${mid_price:.4f}) - mercado favorece el 'No'")
            elif mid_price > 0.80:
                print(f"   💡 Precio alto (${mid_price:.4f}) - mercado favorece el 'Sí'")
            else:
                print(f"   💡 Precio equilibrado (${mid_price:.4f}) - mercado incierto")

            print()
            print("=" * 70)
            break

    except Exception as e:
        # Mercado sin orderbook activo, continuar
        continue

if not found:
    print("⚠️  No se encontraron mercados con orderbooks activos")
    print("   Los mercados pueden no tener órdenes si son muy nuevos o inactivos")
else:
    print()
    print("✅ Análisis completado!")
    print()
    print("CONCEPTOS CLAVE:")
    print()
    print("• BID (Compra): Órdenes de personas que quieren COMPRAR")
    print("• ASK (Venta): Órdenes de personas que quieren VENDER")
    print("• Spread: Diferencia entre el mejor precio de compra y venta")
    print("• Liquidez: Cuántas órdenes hay (más = mejor)")
    print("• Precio: Entre $0.00 (casi imposible) y $1.00 (casi seguro)")
    print()
