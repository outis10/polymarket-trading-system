"""
Analizar el libro de órdenes de un mercado específico
"""
from py_clob_client.client import ClobClient

client = ClobClient("https://clob.polymarket.com")

# Obtener mercados activos
markets_response = client.get_markets()

# Extraer datos
if isinstance(markets_response, dict):
    markets = markets_response.get('data', [])
else:
    markets = markets_response

if not markets:
    print("No hay mercados activos")
    exit()

# Tomar primer mercado
market = markets[0]
tokens = market.get('tokens', [])

if not tokens:
    print("Mercado sin tokens")
    exit()

# Analizar primer token
token = tokens[0]
token_id = token['token_id']
outcome = token.get('outcome', 'Unknown')

print(f"📊 Analizando: {market.get('question')}")
print(f"   Token: {outcome}")
print(f"   Token ID: {token_id[:20]}...\n")

# Obtener datos del token
print("🔹 Precios:")
mid = client.get_midpoint(token_id)
buy_price = client.get_price(token_id, "BUY")
sell_price = client.get_price(token_id, "SELL")

print(f"   Mid Price: ${mid:.4f}")
print(f"   Best Bid (BUY): ${buy_price:.4f}")
print(f"   Best Ask (SELL): ${sell_price:.4f}")
print(f"   Spread: ${sell_price - buy_price:.4f}\n")

# Obtener order book completo
print("🔹 Order Book:")
book = client.get_order_book(token_id)

bids = book.get('bids', [])
asks = book.get('asks', [])

print(f"\n   📗 Top 5 BIDS (Compra):")
for i, bid in enumerate(bids[:5], 1):
    print(f"   {i}. Price: ${float(bid['price']):.4f}, Size: {float(bid['size']):.2f}")

print(f"\n   📕 Top 5 ASKS (Venta):")
for i, ask in enumerate(asks[:5], 1):
    print(f"   {i}. Price: ${float(ask['price']):.4f}, Size: {float(ask['size']):.2f}")

# Calcular profundidad del mercado
total_bid_size = sum(float(bid['size']) for bid in bids)
total_ask_size = sum(float(ask['size']) for ask in asks)

print(f"\n   📊 Profundidad del Mercado:")
print(f"      Total Bid Size: ${total_bid_size:.2f}")
print(f"      Total Ask Size: ${total_ask_size:.2f}")

print("\n✅ Análisis completado!")
