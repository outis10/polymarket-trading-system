"""
Exploración básica de Polymarket sin necesidad de credenciales
"""
from py_clob_client.client import ClobClient
from pprint import pprint

# Crear cliente público
client = ClobClient("https://clob.polymarket.com")

print("🔹 1. Health Check")
print(f"   OK: {client.get_ok()}")
print(f"   Server Time: {client.get_server_time()}\n")

print("🔹 2. Obtener Mercados Activos")
markets_response = client.get_markets()

# La API devuelve un dict con 'data', 'count', etc.
if isinstance(markets_response, dict):
    markets = markets_response.get('data', [])
    total_count = markets_response.get('count', len(markets))
else:
    markets = markets_response
    total_count = len(markets) if markets else 0

print(f"   Total mercados disponibles: {total_count}")
print(f"   Mercados en esta página: {len(markets)}")

# Mostrar primeros 5 mercados
print("\n   📊 Primeros 5 mercados:")
for i, market in enumerate(markets[:5], 1):
    question = market.get('question', 'N/A')
    condition_id = market.get('condition_id', 'N/A')
    active = market.get('active', False)

    print(f"\n   {i}. {question[:70]}...")
    print(f"      Market ID: {condition_id[:20] if condition_id else 'N/A'}...")
    print(f"      Active: {'✓' if active else '✗'}")

    # Mostrar tokens (opciones de apuesta)
    tokens = market.get('tokens', [])
    if tokens:
        print(f"      Opciones ({len(tokens)}):")
        for token in tokens[:2]:  # Mostrar máximo 2 tokens
            outcome = token.get('outcome', 'N/A')
            token_id = token.get('token_id', 'N/A')
            print(f"         - {outcome}: {token_id[:20] if token_id else 'N/A'}...")

print("\n✅ Exploración básica completada!")
