"""
Explorar mercados activos usando Gamma API (recomendado)
Gamma API es más eficiente para obtener metadata de mercados
"""
import requests
import json

# Gamma API base URL
GAMMA_API = "https://gamma-api.polymarket.com"

print("=" * 70)
print("MERCADOS ACTIVOS - USANDO GAMMA API")
print("=" * 70)
print()

# Obtener eventos activos y abiertos
print("🔍 Obteniendo eventos activos y abiertos...")
print()

params = {
    'active': 'true',      # Solo eventos activos
    'closed': 'false',     # Solo eventos abiertos (no cerrados)
    'archived': 'false',   # No archivados
    'limit': 10            # Primeros 10
}

response = requests.get(f"{GAMMA_API}/events", params=params)

if response.status_code != 200:
    print(f"❌ Error: {response.status_code}")
    print(response.text)
    exit(1)

events = response.json()

print(f"📊 Total eventos encontrados: {len(events)}")
print()

# Explorar cada evento
for i, event in enumerate(events, 1):
    print("-" * 70)
    print(f"{i}. {event.get('title', 'N/A')}")
    print()

    # Información básica
    print(f"   ID: {event.get('id', 'N/A')}")
    print(f"   Slug: {event.get('slug', 'N/A')}")
    print()

    # Estado
    active = event.get('active', False)
    closed = event.get('closed', False)
    archived = event.get('archived', False)

    print(f"   Estado:")
    print(f"     • Activo: {'✓ Sí' if active else '✗ No'}")
    print(f"     • Cerrado: {'✓ Sí' if closed else '✗ No'}")
    print(f"     • Archivado: {'✓ Sí' if archived else '✗ No'}")
    print()

    # Fechas
    start_date = event.get('startDate', 'N/A')
    end_date = event.get('endDate', 'N/A')

    print(f"   Fechas:")
    if start_date and start_date != 'N/A':
        print(f"     • Inicio: {start_date[:10]}")
    if end_date and end_date != 'N/A':
        print(f"     • Fin: {end_date[:10]}")
    print()

    # Mercados dentro del evento
    markets = event.get('markets', [])
    print(f"   Mercados: {len(markets)}")

    for j, market in enumerate(markets[:2], 1):  # Mostrar primeros 2
        question = market.get('question', 'N/A')
        condition_id = market.get('conditionId', 'N/A')

        print(f"     {j}. {question[:50]}...")
        print(f"        Condition ID: {condition_id[:20]}...")

        # Tokens (opciones)
        tokens = market.get('tokens', [])
        if tokens:
            print(f"        Opciones:")
            for token in tokens:
                outcome = token.get('outcome', 'N/A')
                token_id = token.get('token_id', 'N/A')

                # Precio
                price = token.get('price', None)
                if price:
                    price_float = float(price)
                    print(f"          • {outcome}: ${price_float:.4f} ({price_float*100:.1f}%)")
                else:
                    print(f"          • {outcome}: (Sin precio)")

    if len(markets) > 2:
        print(f"     ... y {len(markets) - 2} mercados más")

    print()

print("=" * 70)
print()
print("✅ Exploración completada con Gamma API")
print()
print("VENTAJAS DE GAMMA API:")
print()
print("• Filtra por activo/cerrado directamente")
print("• Devuelve metadata completa de eventos")
print("• Incluye precios actuales")
print("• Más eficiente para exploración")
print("• Menos llamadas a la API")
print()
print("CUÁNDO USAR CADA API:")
print()
print("Gamma API (gamma-api.polymarket.com):")
print("  → Explorar mercados")
print("  → Buscar eventos activos")
print("  → Obtener metadata")
print("  → Ver precios actuales")
print()
print("CLOB API (clob.polymarket.com):")
print("  → Hacer trading (crear/cancelar órdenes)")
print("  → Ver orderbook en detalle")
print("  → Gestionar posiciones")
print("  → Ejecutar trades")
print()
print("PRÓXIMO PASO:")
print("  Usa los condition_id de arriba para obtener orderbooks en CLOB API")
print()
