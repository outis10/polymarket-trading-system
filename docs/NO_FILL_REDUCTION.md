# No-Fill Reduction Strategy

## Diagnóstico

Análisis del CSV `bot_orders_*.csv` (577 filas, 2026-03-04 a 2026-03-05):

| Métrica | No_fill (317) | Placed (264) |
|---|---|---|
| Avg Edge | **13.44%** | 9.86% |
| Avg Ask | **0.5475** | 0.6108 |
| Slots concentrados | 3–7 (early) | distribuido |
| order_id vacío | **100%** | 0% |

### Hallazgo clave

El `order_id` está **vacío en el 100% de los no_fills**, lo que confirma que las órdenes **sí llegan al CLOB** pero éste responde con error de liquidez (`"no orders found to match"`). No es un problema de red ni de conexión.

Las órdenes con mayor edge (13.44% promedio) ocurren en contratos con ask más bajo (0.55 vs 0.61), que tienen order books más delgados. La tolerancia de precio original (`+0.02`) no era suficiente para cruzar el spread y encontrar contraparte.

### Por qué múltiples VPS no ayudaron

El cliente `py_clob_client` ya usa `httpx.Client(http2=True)` con conexión persistente (singleton a nivel de módulo) y `Connection: keep-alive`. Los 1716ms de latencia promedio son tiempo de procesamiento del CLOB, no latencia de red. Mover el bot a us-east-1 ahorraría ~60ms de los 1716ms.

---

## Solución implementada (3 capas)

### 1. Mayor tolerancia de precio (default 0.03 → antes 0.02)

**Archivo:** `backend/services/event_manager.py`
**Config:** `fak_price_tolerance` en `config/runtime_settings.json`

```python
_fak_tolerance = float(self.settings.get("fak_price_tolerance", 0.03))
```

El `order_price` que llega al CLOB es `ask_price + tolerance`. Con 0.03, la orden acepta pagar hasta 3 centavos más del ask actual, dando más margen para cruzar el spread en books delgados.

**Trade-off:** ~0.5–1pp más de slippage en fills exitosos. Con edge promedio de 13.44% en no_fills, hay margen amplio para absorberlo.

---

### 2. Retry automático en no_fill

**Config:** `bot_fak_retry_on_no_fill` (bool, default `true`), `bot_fak_retry_extra_tolerance` (float, default `0.01`)

Si el CLOB rechaza con "no orders found to match", el bot hace **un segundo intento** con `tolerance + retry_extra` (default `0.04` total) antes de registrar como no_fill.

```
Intento 1: order_price = ask + 0.03
  → no_fill
Intento 2: order_price = ask + 0.04
  → fill ✓  (o no_fill → se registra)
```

La latencia total (`fill_latency_ms`) se mide desde el primer intento hasta el fill final.

**Para desactivar el retry:**
```json
{ "bot_fak_retry_on_no_fill": false }
```

---

### 3. Filtro de profundidad mínima de book

**Config:** `bot_min_ask_depth_usd` (float, default `0.0` = desactivado)

Antes de enviar la orden, verifica que la liquidez acumulada en el ask del book sea suficiente. Si no alcanza el mínimo, saltea la orden sin consumir el intento ni el cooldown.

```python
# Activa con un mínimo de $5 USD de liquidez en el ask
{ "bot_min_ask_depth_usd": 5.0 }
```

Cuando el filtro activa, resetea `_bot_prev_gate_enabled[key] = False` para permitir re-trigger en el siguiente tick si el book mejora.

**Cuándo usar:** útil si hay muchos no_fills incluso con retry. Evita gastar el RTT al CLOB (~1.7s) en oportunidades con liquidez structuralmente insuficiente.

---

## Flujo combinado

```
señal detectada
  ↓
¿book depth >= bot_min_ask_depth_usd?
  → NO  → skip silencioso, gate reset (sin CSV row)
  → SÍ  ↓
enviar FAK con ask + 0.03
  → fill ✓  → registrar "placed"
  → no_fill → retry con ask + 0.04
      → fill ✓  → registrar "placed"
      → no_fill → registrar "no_fill" + cooldown
```

---

## Parámetros configurables

| Parámetro | Default | Descripción |
|---|---|---|
| `fak_price_tolerance` | `0.03` | Tolerancia base sobre ask (era 0.02) |
| `bot_fak_retry_on_no_fill` | `true` | Activa el retry automático |
| `bot_fak_retry_extra_tolerance` | `0.01` | Extra de precio en el retry |
| `bot_min_ask_depth_usd` | `0.0` | Profundidad mínima de ask en USD (0 = desactivado) |
| `bot_no_fill_cooldown_secs` | `2` | Cooldown tras no_fill antes de reintentar la señal |

Todos se configuran en `config/runtime_settings.json` y se aplican en caliente sin reiniciar el bot.

---

## Resultados esperados

Con los datos históricos (317 no_fills con avg edge 13.44%):

- La mayoría de no_fills ocurren en ask 0.4–0.6 con spreads de 0.015–0.022 (1.5–2.2%)
- La tolerancia original (0.02) apenas cubría el spread en esos niveles
- Con 0.03 base + retry a 0.04, se cubren spreads de hasta 4% que son los más frecuentes
- Conversión estimada: 40–60% de no_fills → placed, dependiendo de la liquidez real del book
