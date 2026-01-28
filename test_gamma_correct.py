"""
Obtener mercados con tokens usando el endpoint correcto de Gamma API
"""
import requests
import json

GAMMA_API = "https://gamma-api.polymarket.com"

print("=" * 70)
print("TEST: Obtener mercados activos con tokens")
print("=" * 70)
print()

# Usar endpoint /markets directamente (no /events)
print("1. Probando endpoint /markets...")
params = {
    'active': 'true',
    'closed': 'false',
    'limit': 3
}

response = requests.get(f"{GAMMA_API}/markets", params=params)
markets = response.json()

print(f"   Respuesta: {len(markets)} mercados")
print()

if markets and len(markets) > 0:
    print("2. Estructura del primer mercado:")
    market = markets[0]

    # Mostrar todas las claves
    print(f"   Claves disponibles: {list(market.keys())}")
    print()

    # Información básica
    print(f"   Question: {market.get('question', 'N/A')}")
    print(f"   Condition ID: {market.get('conditionId', 'N/A')}")
    print(f"   Active: {market.get('active', 'N/A')}")
    print(f"   Closed: {market.get('closed', 'N/A')}")
    print()

    # Buscar tokens
    if 'tokens' in market:
        tokens = market.get('tokens', [])
        print(f"   Tokens encontrados: {len(tokens)}")
        for token in tokens:
            print(f"     - {token}")
    elif 'clobTokenIds' in market:
        print(f"   CLOB Token IDs: {market.get('clobTokenIds')}")

    # Buscar outcomePrices
    if 'outcomePrices' in market:
        print(f"   Outcome Prices: {market.get('outcomePrices')}")

    if 'outcomes' in market:
        print(f"   Outcomes: {market.get('outcomes')}")

    print()
    print("3. JSON completo del primer mercado:")
    print(json.dumps(market, indent=2)[:2000])
