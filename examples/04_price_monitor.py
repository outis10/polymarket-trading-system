"""
Monitorear precios de un mercado en tiempo real
"""
from py_clob_client.client import ClobClient
import time
from datetime import datetime

client = ClobClient("https://clob.polymarket.com")

# Configurar mercado a monitorear
markets = client.get_markets(closed=False, active=True)
market = markets[0]  # Primer mercado activo
token = market['tokens'][0]
token_id = token['token_id']

print(f"📊 Monitoreando: {market.get('question')}")
print(f"   Token: {token.get('outcome')}")
print(f"   Token ID: {token_id[:20]}...\n")
print("Presiona Ctrl+C para detener\n")
print("-" * 60)

try:
    while True:
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        mid = client.get_midpoint(token_id)
        buy = client.get_price(token_id, "BUY")
        sell = client.get_price(token_id, "SELL")
        spread = sell - buy if sell and buy else 0
        
        print(f"[{timestamp}] Mid: ${mid:.4f} | Bid: ${buy:.4f} | Ask: ${sell:.4f} | Spread: ${spread:.4f}")
        
        time.sleep(5)  # Actualizar cada 5 segundos
        
except KeyboardInterrupt:
    print("\n\n✅ Monitoreo detenido!")
