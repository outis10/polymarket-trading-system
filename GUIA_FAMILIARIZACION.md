# Guía de Familiarización - Polymarket Trading System

Esta guía te ayudará a familiarizarte con el sistema de trading de Polymarket paso a paso.

## 📚 Estructura del Proyecto

```
polymarket-trading-system/
├── config/              # Configuración
│   └── settings.py      # Tu configuración (límites, API keys, etc.)
│
├── core/                # Cliente principal
│   └── client_wrapper.py  # Wrapper de Polymarket API
│
├── risk/                # Gestión de riesgo
│   └── position_manager.py  # Stop-loss, take-profit, límites
│
├── execution/           # Ejecución de órdenes
│   └── order_executor.py    # Ejecuta y gestiona órdenes
│
├── strategy/            # Estrategias de trading
│   ├── base_strategy.py     # Clase base para estrategias
│   └── arbitrage.py         # Ejemplo: estrategia de arbitraje
│
├── examples/            # Ejemplos para aprender
│   ├── 01_explore_basics.py
│   ├── 02_analyze_orderbook.py
│   ├── 03_find_arbitrage.py
│   └── 04_price_monitor.py
│
└── main.py              # Bot principal
```

## 🎯 Fase 1: Exploración Básica (SIN Riesgo)

### Paso 1.1: Explorar mercados disponibles

```bash
python examples/01_explore_basics.py
```

**Qué hace:**
- Muestra mercados activos
- No requiere credenciales
- Solo lectura de datos públicos

### Paso 1.2: Analizar order books

```bash
python examples/02_analyze_orderbook.py
```

**Qué hace:**
- Muestra bids (compradores) y asks (vendedores)
- Calcula spreads (diferencia entre compra/venta)
- Identifica oportunidades de precio

### Paso 1.3: Buscar oportunidades de arbitraje

```bash
python examples/03_find_arbitrage.py
```

**Qué hace:**
- Busca mercados con spreads grandes
- Identifica posibles oportunidades
- Solo observación (no ejecuta trades)

### Paso 1.4: Monitorear precios en tiempo real

```bash
python examples/04_price_monitor.py
```

**Qué hace:**
- Monitorea un mercado específico
- Actualiza precios cada pocos segundos
- Muestra cambios de precio

## 🔧 Fase 2: Entender el Bot Principal

### Paso 2.1: Ejecutar demo rápida

```bash
python demo_bot_quick.py
```

**Qué muestra:**
- Una iteración completa del bot
- Mercados activos
- Tus órdenes y posiciones
- Métricas de riesgo

### Paso 2.2: Ejecutar bot en modo observación

```bash
python main.py
```

**Qué hace:**
- Se ejecuta continuamente (cada 60 segundos)
- Monitorea mercados
- Revisa posiciones
- Aplica stop-loss/take-profit si tienes posiciones
- NO hace trades automáticos (estrategia vacía)

**Cómo detenerlo:** Presiona `Ctrl+C`

### Paso 2.3: Entender el ciclo del bot

El bot ejecuta estos pasos cada 60 segundos:

```python
while bot_activo:
    1. Mostrar status (cada 10 iteraciones)
       → Balance, posiciones, exposición, P&L

    2. Monitorear posiciones
       → Actualizar precios
       → Aplicar stop-loss si pérdida > 5%
       → Aplicar take-profit si ganancia > 15%

    3. Escanear mercados
       → Buscar oportunidades (VACÍO - para implementar)

    4. Esperar 60 segundos

    5. Repetir
```

## ⚙️ Fase 3: Configuración y Límites

### Archivo `.env` - Tu configuración

```env
# Límites de trading (ajusta según tu tolerancia al riesgo)
MAX_POSITION_SIZE=10.0      # Máximo $10 por posición individual
MAX_TOTAL_EXPOSURE=50.0     # Máximo $50 en todas las posiciones

# Gestión de riesgo automática
STOP_LOSS_PCT=0.05          # Cerrar si pérdida > 5%
TAKE_PROFIT_PCT=0.15        # Cerrar si ganancia > 15%

# Estrategia
MIN_CONFIDENCE=0.7          # Confianza mínima para ejecutar trade (70%)
```

### ¿Qué significan estos límites?

**MAX_POSITION_SIZE ($10)**
- Si encuentras una oportunidad, el bot NO arriesgará más de $10
- Ejemplo: Si quieres comprar "Sí" a $0.65, máximo 15 shares ($10 / $0.65)

**MAX_TOTAL_EXPOSURE ($50)**
- Suma de todas tus posiciones abiertas
- Si ya tienes $40 en posiciones, solo puedes abrir $10 más
- Protege contra sobre-exposición

**STOP_LOSS_PCT (5%)**
- Si una posición pierde 5%, se cierra automáticamente
- Ejemplo: Compraste a $0.65, si baja a $0.6175 → vende
- Limita pérdidas máximas

**TAKE_PROFIT_PCT (15%)**
- Si una posición gana 15%, se cierra automáticamente
- Ejemplo: Compraste a $0.65, si sube a $0.7475 → vende
- Asegura ganancias

## 🎨 Fase 4: Entender las Estrategias

### Estructura de una estrategia

```python
# strategy/mi_estrategia.py

from strategy.base_strategy import BaseStrategy, Signal, SignalAction

class MiEstrategia(BaseStrategy):
    def __init__(self, config):
        super().__init__("MiEstrategia", config)

    def analyze(self, market_data):
        """
        Analiza un mercado y retorna señal de trading

        Returns:
            Signal: BUY, SELL o None
        """
        # Tu lógica aquí

        # Ejemplo: Comprar si precio < 0.40
        price = market_data.get('price', 0)

        if price < 0.40:
            return Signal(
                action=SignalAction.BUY,
                token_id=market_data['token_id'],
                price=price,
                size=10.0,  # $10
                confidence=0.8,  # 80% confianza
                reason="Precio bajo detectado"
            )

        return None  # No hacer nada
```

### Estrategias de ejemplo incluidas

**1. Arbitraje (`strategy/arbitrage.py`)**
- Busca diferencias de precio en mercados relacionados
- Ejemplo: Si "Sí" está a $0.30 y "No" a $0.60 → comprar "Sí"
- Riesgo bajo, ganancias pequeñas

**2. Momentum (para implementar)**
- Sigue tendencias de precio
- Compra cuando sube rápido, vende cuando baja
- Riesgo medio, ganancias variables

## 🚀 Fase 5: Implementar Tu Primera Estrategia

### Opción A: Usar estrategia simple

Edita `main.py`, función `scan_markets()`:

```python
def scan_markets(self):
    """Scan markets for opportunities"""
    try:
        markets = self.client.get_markets()

        if not markets:
            return

        # Estrategia simple: Buscar precios muy bajos
        for market in markets[:20]:  # Solo primeros 20
            tokens = market.get('tokens', [])

            for token in tokens:
                token_id = token.get('token_id')

                # Obtener precio actual
                price = self.client.get_market_price(token_id, 'buy')

                if price and price < 0.30:  # Precio muy bajo
                    self.logger.info(f"🔔 Oportunidad: {market.get('question')}")
                    self.logger.info(f"   Precio: ${price:.2f}")

                    # IMPORTANTE: Por ahora solo logear
                    # Para ejecutar trades, descomentar:
                    # result = self.executor.execute_signal(...)

    except Exception as e:
        self.logger.error(f"Error scanning markets: {e}")
```

### Opción B: Usar estrategia modular

```python
# main.py
from strategy.arbitrage import ArbitrageStrategy

class TradingBot:
    def __init__(self):
        # ... código existente ...

        # Agregar estrategia
        self.strategy = ArbitrageStrategy({
            'min_spread': 0.10,  # Spread mínimo 10%
            'max_position_size': 10.0
        })

    def scan_markets(self):
        markets = self.client.get_markets()

        for market in markets[:50]:
            # Analizar mercado
            signal = self.strategy.analyze(market)

            if signal:
                self.logger.info(f"🎯 Señal: {signal.action}")
                self.logger.info(f"   Mercado: {market.get('question')}")
                self.logger.info(f"   Confianza: {signal.confidence:.1%}")

                # Ejecutar (cuando estés listo)
                # result = self.executor.execute_signal(signal)
```

## ⚠️ Recomendaciones de Seguridad

### Antes de hacer trading REAL:

1. **Empieza con límites MUY bajos**
   - MAX_POSITION_SIZE: $5-$10
   - MAX_TOTAL_EXPOSURE: $20-$50

2. **Observa el bot SIN trading automático**
   - Ejecuta `main.py` por días
   - Observa qué "oportunidades" detectaría
   - Ajusta tu estrategia

3. **Prueba manualmente primero**
   - Haz algunos trades manuales en polymarket.com
   - Entiende cómo funcionan los mercados
   - Aprende sobre gas fees, spreads, etc.

4. **Implementa logging extensivo**
   - Registra TODAS las decisiones del bot
   - Revisa logs diariamente
   - Ajusta estrategia basándote en resultados

5. **Usa un wallet separado**
   - NO uses tu wallet principal
   - Transfiere solo lo que estés dispuesto a perder
   - Mantén la mayoría de fondos en wallet segura

## 📊 Monitoreo y Ajustes

### Revisar logs

```bash
# Ver logs en tiempo real
tail -f trading_bot.log

# Buscar errores
grep ERROR trading_bot.log

# Ver decisiones de trading
grep "Signal" trading_bot.log
```

### Métricas a monitorear

- **Win rate**: % de trades ganadores
- **P&L promedio**: Ganancia/pérdida por trade
- **Max drawdown**: Peor racha de pérdidas
- **Sharpe ratio**: Retorno ajustado por riesgo

## 🎓 Próximos Pasos

1. **Ejecuta todos los ejemplos** (Fase 1)
2. **Ejecuta el bot en modo observación** por 1 semana
3. **Estudia las estrategias** de ejemplo
4. **Implementa una estrategia simple** (solo logging)
5. **Prueba con montos MÍNIMOS** ($5-10)
6. **Itera y mejora** basándote en resultados

## 📞 Recursos Adicionales

- Documentación Polymarket: https://docs.polymarket.com
- py-clob-client: https://github.com/Polymarket/py-clob-client
- Logs del bot: `trading_bot.log`

---

**Recuerda**: El trading automatizado conlleva riesgos. Empieza pequeño, aprende constantemente, y nunca arriesgues más de lo que puedes perder.
