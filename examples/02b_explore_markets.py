"""
Explorar mercados y sus precios disponibles
"""
from py_clob_client.client import ClobClient

client = ClobClient("https://clob.polymarket.com")

print("=" * 70)
print("EXPLORACIÓN DE MERCADOS DE POLYMARKET")
print("=" * 70)
print()

# Obtener mercados
markets_response = client.get_markets()

if isinstance(markets_response, dict):
    markets = markets_response.get('data', [])
else:
    markets = markets_response

print(f"📊 Total mercados disponibles: {len(markets)}")
print()

# Explorar primeros 10 mercados
print("🔍 Explorando primeros 10 mercados...")
print()

for i, market in enumerate(markets[:10], 1):
    question = market.get('question', 'N/A')
    condition_id = market.get('condition_id', 'N/A')
    active = market.get('active', True)
    closed = market.get('closed', False)
    archived = market.get('archived', False)
    tokens = market.get('tokens', [])

    print("-" * 70)
    print(f"{i}. {question[:60]}...")
    print()
    print(f"   Estado:")
    print(f"     • Activo: {'✓ Sí' if active else '✗ No'}")
    print(f"     • Cerrado: {'✓ Sí' if closed else '✗ No'}")
    print(f"     • Archivado: {'✓ Sí' if archived else '✗ No'}")
    print()

    if tokens:
        print(f"   Opciones disponibles:")
        for token in tokens[:2]:
            outcome = token.get('outcome', 'N/A')
            token_id = token.get('token_id', 'N/A')
            print(f"     • {outcome}")
            print(f"       Token ID: {token_id[:30] if token_id else 'N/A'}...")

            # Intentar obtener precio
            try:
                # Usar método de midpoints que es más confiable
                prices_response = client.get_midpoints([token_id])
                if prices_response and len(prices_response) > 0:
                    price_data = prices_response[0]
                    mid_price = float(price_data.get('mid', 0))
                    if mid_price > 0:
                        print(f"       Precio estimado: ${mid_price:.4f} ({mid_price * 100:.1f}%)")
                        print(f"       Probabilidad implícita: {mid_price * 100:.1f}%")
                    else:
                        print(f"       Precio: No disponible")
                else:
                    print(f"       Precio: No disponible")
            except Exception as e:
                print(f"       Precio: No disponible")

        print()
    else:
        print("   ⚠️  Sin tokens disponibles")
        print()

print("=" * 70)
print()
print("✅ Exploración completada!")
print()
print("CONCEPTOS CLAVE:")
print()
print("• Cada mercado tiene una PREGUNTA (ej: '¿Quién ganará?')")
print("• Cada mercado tiene OPCIONES (tokens) para apostar")
print("• El PRECIO va de $0.00 (imposible) a $1.00 (seguro)")
print("• El precio = probabilidad según el mercado")
print()
print("EJEMPLO:")
print("  Si 'Sí' cuesta $0.70:")
print("  → El mercado cree que hay 70% de probabilidad")
print("  → Si apuestas $1 y ganas, recibes $1.43 ($0.43 de ganancia)")
print("  → Si apuestas $1 y pierdes, pierdes $1")
print()
print("NEXT STEP:")
print("  python examples/03_find_arbitrage.py")
print()
