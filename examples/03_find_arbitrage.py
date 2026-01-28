"""
Buscar oportunidades de arbitraje simples
Detecta cuando YES + NO ≠ 1.0
"""
from py_clob_client.client import ClobClient

client = ClobClient("https://clob.polymarket.com")

print("🔍 Buscando oportunidades de arbitraje...\n")

markets = client.get_markets(closed=False, active=True)
opportunities = []

for market in markets[:50]:  # Revisar primeros 50 mercados
    tokens = market.get('tokens', [])
    
    if len(tokens) != 2:
        continue
    
    # Obtener precios de YES y NO
    yes_token = next((t for t in tokens if t.get('outcome') == 'Yes'), None)
    no_token = next((t for t in tokens if t.get('outcome') == 'No'), None)
    
    if not yes_token or not no_token:
        continue
    
    try:
        yes_price = client.get_midpoint(yes_token['token_id'])
        no_price = client.get_midpoint(no_token['token_id'])
        
        if yes_price is None or no_price is None:
            continue
        
        total = yes_price + no_price
        spread = abs(1.0 - total)
        
        # Oportunidad si spread > 2%
        if spread > 0.02:
            opportunities.append({
                'question': market.get('question'),
                'yes_price': yes_price,
                'no_price': no_price,
                'total': total,
                'spread': spread,
                'type': 'underpriced' if total < 1.0 else 'overpriced'
            })
    except:
        continue

# Ordenar por spread (mayor a menor)
opportunities.sort(key=lambda x: x['spread'], reverse=True)

print(f"📊 Encontradas {len(opportunities)} oportunidades\n")

for i, opp in enumerate(opportunities[:5], 1):  # Top 5
    print(f"{i}. {opp['question'][:70]}...")
    print(f"   YES: ${opp['yes_price']:.4f}, NO: ${opp['no_price']:.4f}")
    print(f"   Total: ${opp['total']:.4f} ({'<' if opp['total'] < 1.0 else '>'} 1.0)")
    print(f"   Spread: {opp['spread']:.4f} ({opp['spread']*100:.2f}%)")
    print(f"   Tipo: {opp['type']}\n")

print("✅ Búsqueda completada!")
