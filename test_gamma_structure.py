"""
Verificar estructura de respuesta de Gamma API
"""
import requests
import json

GAMMA_API = "https://gamma-api.polymarket.com"

params = {
    'active': 'true',
    'closed': 'false',
    'limit': 1
}

response = requests.get(f"{GAMMA_API}/events", params=params)
events = response.json()

if events:
    print("Estructura del primer evento:")
    print(json.dumps(events[0], indent=2)[:2000])  # Primeros 2000 chars
else:
    print("No se encontraron eventos")
