# 🎓 Tutorial Interactivo: py-clob-client

**Guía práctica para explorar y entender la librería de Polymarket**

---

## 📚 Tabla de Contenidos

1. [Conceptos Básicos](#conceptos-básicos)
2. [Niveles de Autenticación](#niveles-de-autenticación)
3. [Tutorial Paso a Paso](#tutorial-paso-a-paso)
4. [Ejemplos Prácticos](#ejemplos-prácticos)
5. [Ejercicios para Practicar](#ejercicios-para-practicar)

---

## 🎯 Conceptos Básicos

### ¿Qué es CLOB?

**CLOB = Central Limit Order Book** (Libro de Órdenes de Límite Central)

Es el sistema que maneja todas las órdenes de compra/venta en Polymarket, similar a cómo funcionan las bolsas de valores tradicionales.

### Conceptos Clave de Polymarket

#### 1. **Markets (Mercados)**
Predicciones sobre eventos del mundo real.
- Ejemplo: "¿Ganará Trump las elecciones 2024?"

#### 2. **Tokens**
Cada mercado tiene 2 tokens:
- **YES token**: Vale $1 si el evento ocurre
- **NO token**: Vale $1 si el evento NO ocurre

#### 3. **Token ID**
Identificador único de cada token (string largo)
- Ejemplo: `"21742633143463906290569050155826241533067272736897614950488156847949938836455"`

#### 4. **Precios**
Los precios van de 0.00 a 1.00 (representando probabilidad)
- YES a $0.60 = mercado cree 60% de probabilidad
- NO a $0.40 = mercado cree 40% de probabilidad
- **YES + NO siempre ≈ $1.00**

#### 5. **Order Book (Libro de Órdenes)**
- **Bids**: Órdenes de compra
- **Asks**: Órdenes de venta
- **Spread**: Diferencia entre mejor bid y mejor ask

---

## 🔐 Niveles de Autenticación

py-clob-client tiene **3 niveles** de acceso:

### Level 0: Público (Sin autenticación)
**Solo lectura de datos públicos**

```python
from py_clob_client.client import ClobClient

# Cliente público (no necesita credenciales)
client = ClobClient("https://clob.polymarket.com")

# Métodos disponibles:
client.get_ok()                    # Health check
client.get_server_time()           # Hora del servidor
client.get_markets()               # Lista de mercados
client.get_order_book(token_id)    # Libro de órdenes
client.get_price(token_id, "BUY")  # Precio actual
client.get_midpoint(token_id)      # Precio medio
```

### Level 1: Con Signer (Private Key)
**Crear/derivar API keys**

```python
from py_clob_client.client import ClobClient

HOST = "https://clob.polymarket.com"
CHAIN_ID = 137  # Polygon mainnet
PRIVATE_KEY = "tu_private_key"

client = ClobClient(
    HOST,
    key=PRIVATE_KEY,
    chain_id=CHAIN_ID
)

# Crear o derivar credenciales API
creds = client.create_or_derive_api_creds()
client.set_api_creds(creds)
```

### Level 2: Con API Creds (Full Trading)
**Crear, modificar, cancelar órdenes**

```python
# Configuración completa para trading
client = ClobClient(
    HOST,
    key=PRIVATE_KEY,
    chain_id=CHAIN_ID,
    signature_type=0,  # 0: EOA, 1: Email/Magic, 2: Browser wallet
    funder=FUNDER_ADDRESS  # Tu dirección que tiene fondos
)

client.set_api_creds(creds)

# Ahora puedes crear órdenes
```

---

## 📖 Tutorial Paso a Paso

### Paso 1: Exploración Básica (Sin Credenciales)

**Script: `explore_basics.py`**

```python
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
markets = client.get_markets()
print(f"   Total mercados: {len(markets)}")

# Mostrar primeros 3 mercados
print("\n   📊 Primeros 3 mercados:")
for i, market in enumerate(markets[:3], 1):
    print(f"\n   {i}. {market.get('question', 'N/A')}")
    print(f"      Market ID: {market.get('condition_id', 'N/A')[:20]}...")
    print(f"      Active: {market.get('active', False)}")
    
    # Mostrar tokens
    tokens = market.get('tokens', [])
    if tokens:
        print(f"      Tokens: {len(tokens)}")
        for token in tokens:
            print(f"         - {token.get('outcome')}: {token.get('token_id', 'N/A')[:20]}...")

print("\n✅ Exploración básica completada!")
```

### Paso 2: Analizar Order Books

**Script: `analyze_orderbook.py`**

```python
"""
Analizar el libro de órdenes de un mercado específico
"""
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import BookParams

client = ClobClient("https://clob.polymarket.com")

# Obtener un mercado activo
markets = client.get_markets(closed=False, active=True)
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
```

### Paso 3: Buscar Oportunidades de Arbitraje

**Script: `find_arbitrage.py`**

```python
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
```

### Paso 4: Monitorear Precios en Tiempo Real

**Script: `price_monitor.py`**

```python
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
```

---

## 🎮 Ejemplos Prácticos

### Ejemplo 1: Encontrar Mercados por Categoría

```python
from py_clob_client.client import ClobClient

client = ClobClient("https://clob.polymarket.com")

# Buscar mercados de deportes
markets = client.get_markets()

sports_markets = [m for m in markets if 'sports' in m.get('tags', [])]
crypto_markets = [m for m in markets if 'crypto' in m.get('tags', [])]
politics_markets = [m for m in markets if 'politics' in m.get('tags', [])]

print(f"Deportes: {len(sports_markets)}")
print(f"Crypto: {len(crypto_markets)}")
print(f"Política: {len(politics_markets)}")
```

### Ejemplo 2: Calcular Probabilidad Implícita

```python
def calculate_implied_probability(price):
    """
    Precio de $0.60 = 60% de probabilidad
    """
    return price * 100

token_id = "..."  # Tu token ID
price = client.get_midpoint(token_id)
probability = calculate_implied_probability(price)

print(f"Precio: ${price:.2f}")
print(f"Probabilidad implícita: {probability:.1f}%")
```

### Ejemplo 3: Comparar Múltiples Tokens

```python
from py_clob_client.clob_types import BookParams

# Comparar precios de múltiples tokens a la vez
token_ids = ["token1", "token2", "token3"]

params = [BookParams(token_id=tid) for tid in token_ids]
books = client.get_order_books(params)

for token_id, book in zip(token_ids, books):
    best_bid = book['bids'][0]['price'] if book.get('bids') else None
    best_ask = book['asks'][0]['price'] if book.get('asks') else None
    print(f"{token_id[:10]}... | Bid: ${best_bid} | Ask: ${best_ask}")
```

---

## 🏋️ Ejercicios para Practicar

### Ejercicio 1: Explorer de Mercados
**Objetivo**: Crear un script que muestre información detallada de mercados

```python
# TODO: 
# 1. Obtener todos los mercados activos
# 2. Filtrar por categoría (deportes, política, crypto)
# 3. Mostrar top 10 por volumen
# 4. Calcular probabilidades implícitas
```

### Ejercicio 2: Detector de Arbitraje Avanzado
**Objetivo**: Encontrar oportunidades con filtros avanzados

```python
# TODO:
# 1. Escanear mercados
# 2. Calcular YES + NO
# 3. Filtrar por:
#    - Spread > umbral
#    - Volumen mínimo
#    - Liquidez suficiente
# 4. Rankear por rentabilidad potencial
```

### Ejercicio 3: Análisis de Liquidez
**Objetivo**: Evaluar la profundidad del mercado

```python
# TODO:
# 1. Obtener order book completo
# 2. Calcular profundidad (total de órdenes)
# 3. Analizar distribución de precios
# 4. Identificar "muros" de compra/venta
```

### Ejercicio 4: Dashboard de Precios
**Objetivo**: Crear un dashboard en terminal

```python
# TODO:
# 1. Monitorear 5 mercados simultáneamente
# 2. Actualizar cada 10 segundos
# 3. Mostrar cambios de precio
# 4. Alertar si precio cambia > 5%
```

---

## 🔧 Tips y Mejores Prácticas

### 1. Rate Limiting
```python
import time

# Esperar entre requests para no exceder límites
for market in markets:
    # hacer algo
    time.sleep(0.1)  # 100ms entre requests
```

### 2. Manejo de Errores
```python
try:
    price = client.get_price(token_id, "BUY")
except Exception as e:
    print(f"Error obteniendo precio: {e}")
    price = None
```

### 3. Validación de Datos
```python
# Siempre validar que los datos existen
if book and book.get('bids'):
    best_bid = float(book['bids'][0]['price'])
else:
    print("No hay bids disponibles")
```

### 4. Logging
```python
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

logger.info(f"Procesando mercado: {market_id}")
logger.warning(f"Spread anormal detectado: {spread}")
```

---

## 📚 Recursos Adicionales

### Documentación Oficial
- **py-clob-client**: https://github.com/Polymarket/py-clob-client
- **API Docs**: https://docs.polymarket.com/
- **Gamma Markets API**: https://docs.polymarket.com/developers/gamma-markets-api

### Conceptos Importantes
- **Token Allowances**: Permisos necesarios para trading
- **Signature Types**: Tipos de wallets (EOA, Magic, Browser)
- **Chain ID**: 137 para Polygon mainnet, 80002 para testnet
- **Funder Address**: Dirección que tiene los fondos

---

## 🎯 Siguiente Paso

Una vez que domines estos conceptos:

1. **Obtén credenciales** de Polymarket
2. **Practica con testnet** primero
3. **Implementa estrategias** simples
4. **Añade risk management** a tu código

---

**¡Empieza con `explore_basics.py` y ve avanzando!** 🚀

¿Tienes preguntas? Revisa la documentación oficial o experimenta con los scripts.
