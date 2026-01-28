# 📂 Examples - Scripts de Ejemplo

Scripts prácticos para aprender a usar py-clob-client con Polymarket.

## 🚀 Cómo Usar

Todos estos scripts funcionan **SIN CREDENCIALES** (solo lectura de datos públicos).

```bash
# Activar entorno virtual
cd /home/desarrollo/dev/proyectos/polymarket-trading-system
source venv/bin/activate

# Ejecutar cualquier ejemplo
python examples/01_explore_basics.py
python examples/02_analyze_orderbook.py
python examples/03_find_arbitrage.py
python examples/04_price_monitor.py
```

## 📝 Lista de Ejemplos

### 01_explore_basics.py
**Exploración básica de Polymarket**

Qué hace:
- ✅ Health check del servidor
- ✅ Obtener todos los mercados
- ✅ Mostrar información de mercados
- ✅ Ver tokens disponibles

**Conceptos**: Markets, Tokens, API basics

---

### 02_analyze_orderbook.py
**Análisis del libro de órdenes**

Qué hace:
- ✅ Obtener precios (mid, bid, ask)
- ✅ Mostrar order book completo
- ✅ Calcular spread
- ✅ Analizar profundidad del mercado

**Conceptos**: Order Book, Bids, Asks, Spread, Liquidity

---

### 03_find_arbitrage.py
**Detector de oportunidades de arbitraje**

Qué hace:
- ✅ Escanear mercados
- ✅ Calcular YES + NO
- ✅ Detectar anomalías (YES + NO ≠ 1.0)
- ✅ Rankear por rentabilidad

**Conceptos**: Arbitrage, Pricing Inefficiencies, Market Opportunities

---

### 04_price_monitor.py
**Monitor de precios en tiempo real**

Qué hace:
- ✅ Actualizar precios cada 5 segundos
- ✅ Mostrar bid, ask, mid price
- ✅ Calcular spread en tiempo real
- ✅ Detección de cambios

**Conceptos**: Real-time monitoring, Price tracking

---

## 🎯 Orden Recomendado de Aprendizaje

1. **01_explore_basics.py** - Primero, entender la estructura
2. **02_analyze_orderbook.py** - Luego, aprender sobre precios
3. **03_find_arbitrage.py** - Después, detectar oportunidades
4. **04_price_monitor.py** - Finalmente, monitoreo en tiempo real

## 🔧 Modificaciones Sugeridas

### Para 01_explore_basics.py
```python
# Cambiar número de mercados a mostrar
for i, market in enumerate(markets[:10], 1):  # Mostrar 10 en vez de 3

# Filtrar por categoría
sports_markets = [m for m in markets if 'sports' in m.get('tags', [])]
```

### Para 02_analyze_orderbook.py
```python
# Analizar un mercado específico por su índice
market = markets[5]  # Cambiar el 0 por cualquier índice

# Mostrar más niveles del order book
for i, bid in enumerate(bids[:10], 1):  # Top 10 en vez de 5
```

### Para 03_find_arbitrage.py
```python
# Ajustar el umbral de spread
if spread > 0.01:  # 1% en vez de 2%

# Escanear más mercados
for market in markets[:100]:  # 100 en vez de 50
```

### Para 04_price_monitor.py
```python
# Cambiar frecuencia de actualización
time.sleep(10)  # 10 segundos en vez de 5

# Monitorear múltiples tokens
# (requiere modificar el script)
```

## 💡 Ideas para Nuevos Ejemplos

### 05_market_scanner.py
```python
# Escanear todos los mercados y generar reporte
# - Mercados más líquidos
# - Mercados con mayor volumen
# - Mercados cerca de 50/50
```

### 06_compare_markets.py
```python
# Comparar mercados similares
# - Encontrar mercados correlacionados
# - Detectar divergencias
```

### 07_liquidity_heatmap.py
```python
# Visualizar liquidez del order book
# - Profundidad a diferentes niveles de precio
# - Identificar "muros" de órdenes
```

### 08_volume_tracker.py
```python
# Trackear volumen de trading
# - Histórico de trades
# - Velocidad de ejecución
```

## 🐛 Troubleshooting

### Error: "Module not found: py_clob_client"
```bash
pip install py-clob-client
```

### Error: "Connection timeout"
```python
# Agregar retry logic
import time
for attempt in range(3):
    try:
        result = client.get_markets()
        break
    except:
        time.sleep(2)
```

### Los precios salen como None
```python
# Algunos mercados no tienen liquidez
# Siempre verificar:
if price is not None:
    print(f"Precio: ${price:.4f}")
else:
    print("Sin liquidez")
```

## 📚 Próximos Pasos

Después de dominar estos ejemplos:

1. **Modificar los scripts** con tus propias ideas
2. **Combinar funcionalidades** de varios ejemplos
3. **Agregar tus propios filtros** y análisis
4. **Crear visualizaciones** (matplotlib, plotly)
5. **Integrar con tu bot** de trading

## 🔗 Referencias

- Tutorial completo: `../POLYMARKET_TUTORIAL.md`
- Documentación oficial: https://github.com/Polymarket/py-clob-client
- Polymarket API: https://docs.polymarket.com/

---

**¡Empieza a experimentar y aprender!** 🚀
