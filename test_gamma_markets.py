"""
Obtener mercados con tokens de Gamma API
"""
import requests
import json

GAMMA_API = "https://gamma-api.polymarket.com"

# Primero obtener un evento
params = {
    'active': 'true',
    'closed': 'false',
    'limit': 1
}

response = requests.get(f"{GAMMA_API}/events", params=params)
events = response.json()

if events and len(events) > 0:
    event = events[0]
    print(f"Evento: {event.get('title')}")
    print()

    markets = event.get('markets', [])
    print(f"Mercados en el evento: {len(markets)}")

    if markets:
        market = markets[0]
        print(f"\nPrimer mercado:")
        print(f"  Question: {market.get('question')}")
        print(f"  Condition ID: {market.get('conditionId')}")
        print()

        # Verificar si tiene tokens
        if 'tokens' in market:
            print(f"  Tokens: {len(market.get('tokens', []))}")
            for token in market.get('tokens', []):
                print(f"    - {token}")
        else:
            print("  ⚠️  No hay 'tokens' en market")

        # Intentar obtener el market individual por slug
        slug = market.get('slug')
        if slug:
            print(f"\n  Obteniendo market individual por slug: {slug}")
            market_response = requests.get(f"{GAMMA_API}/markets/{slug}")
            market_data = market_response.json()

            print(f"\n  Estructura de market individual:")
            print(json.dumps(market_data, indent=2)[:1500])
