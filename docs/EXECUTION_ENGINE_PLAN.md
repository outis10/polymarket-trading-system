# Execution Engine Plan

Fecha inicio: 2026-03-13

---

## Estado actual

**`>> EN PAUSA DE VALIDACION — esperando datos paper/live para v1.1-c <<`**

| Version | Descripcion | Estado |
|---|---|---|
| `v1.1-a` | Observabilidad de ejecucion | ✅ Implementado |
| `v1.1-b` | Fill Simulator + Execution EV Gate | ✅ Implementado |
| `v1.1-c` | Execution Mode Selector | ⏳ Pendiente (requiere datos) |
| `v1.2-pre` | Order Monitor Loop | ⏳ Pendiente |
| `v1.2` | Lifecycle maker-first + Opportunity Cost | ⏳ Pendiente |
| `v1.3` | Sizing depth-aware | ⏳ Pendiente |
| `v1.4` | Anti-adverse-selection | ⏳ Investigacion futura |

---

## Resumen de como llegamos a este plan

Se reviso el estado actual del bot y la conclusion tecnica fue:

- El sistema actual tiene buen `decision engine`:
  - modelo cuantitativo,
  - tiempo real,
  - lectura multinivel del order book,
  - guardrails de riesgo,
  - sizing con Kelly.
- Pero el bot todavia no es un `execution engine` profesional.
- En la practica actual funciona como un `smart taker`:
  - el flujo automatico dominante usa `FAK` / agresion con tolerancia y retries,
  - no hay ciclo completo de `maker-first`,
  - no hay `cancel/replace` sistematico,
  - no hay seleccion explicita entre maker / aggressive limit / taker / no-trade,
  - no hay gating fuerte por costo esperado de fill multinivel.

Insight principal:

- En Polymarket intradia, especialmente BTC 5m-15m, el edge bruto suele ser chico.
- Si la ejecucion paga demasiado spread, slippage o adverse selection, el edge se evapora.
- Por eso el siguiente salto no es necesariamente mejorar prediccion, sino pasar de:
  - `decision engine + taker`
  - a `decision engine + execution engine hibrido maker/taker`.

### Hallazgo relevante sobre el capital actual

Con ordenes de $10-$20 (capital actual):

- `slippage_vs_ask = 0 bps` — la orden entra completa en el primer nivel, sin slippage adicional.
- `levels_consumed = 1` — no se cruzan niveles.
- `book_consumption_pct = 2-3%` — no se mueve el mercado.
- `slippage_vs_mid ≈ 189 bps` — costo inevitable del half-spread como taker.

Implicacion: el fill simulator confirma que el problema no es market impact sino el spread. El valor de maker-first es capturar ese spread, no evitar impacto.

---

## Hallazgos concretos en el repo

- El bot si puede colocar ordenes `limit` y cancelarlas.
- El repo ya tiene endpoint para cancelar ordenes y wrapper para `place_order` / `cancel_order`.
- El bot automatico hoy no usa un flujo maker-first real; el path dominante sigue siendo agresivo/FAK.
- El order book no es solo top-of-book:
  - se consume profundidad multinivel,
  - actualmente con `order_book_max_levels = 8` por default.
- Ya existe una base de observabilidad parcial:
  - `fill_price_real`,
  - `edge_at_fill_pct`,
  - logs de bloqueos,
  - logs de ordenes del bot.

---

## Decision operativa antes de cambiar execution

Antes de tocar el motor de ejecucion, conviene congelar la version actual con un tag para tener una referencia limpia del bot actual `smart taker`.

Comandos sugeridos:

```bash
git checkout main
git pull --ff-only
git tag -a v1.1-execution-baseline -m "Baseline before execution engine redesign"
git push origin v1.1-execution-baseline
git checkout -b feat/execution-engine-v1
git push -u origin feat/execution-engine-v1
```

---

## Objetivo del rediseño

Construir un `Execution Engine v1` sobre la arquitectura actual, sin reescribir todo de cero, para que el bot pueda:

- estimar mejor el costo real de fill,
- decidir si vale la pena ejecutar despues de execution costs,
- elegir entre maker / aggressive limit / taker tactico / no-trade,
- gestionar ordenes vivas con cancel/replace,
- limitar sizing por liquidez visible y no solo por Kelly.

---

## Plan por fases

### ✅ Fase 1 — Observabilidad de ejecucion (`v1.1-a`)

**Objetivo:** medir si el edge se pierde realmente en execution antes de cambiar la logica.

**Implementado en:**
- `backend/services/event_manager.py` — nuevos campos en `_BOT_ORDERS_FIELDNAMES` + pre-log + post-fill update
- `frontend/src/components/analytics/OpportunitiesDashboard.tsx` — panel "Execution Quality" + tipos
- `frontend/src/components/analytics/OrderDiagnosticModal.tsx` — seccion 5. CLOB Result extendida

**Campos nuevos en CSV (se auto-migran):**

| Campo | Cuando se llena | Que mide |
|---|---|---|
| `realized_slippage_bps` | post-fill | `slippage_pct × 100` — extra pagado sobre ask |
| `implementation_shortfall_bps` | post-fill | `(fill − mid) / mid × 10000` — costo desde el mid |
| `implementation_shortfall_usd` | post-fill | `(fill − mid) × shares` — costo IS en dolares |
| `fill_ratio` | post-fill | `filled_shares / intended_shares` |
| `maker_vs_taker_mode` | pre-log | `"fak"` fijo por ahora |
| `cancel_count` | — | placeholder Fase 5 |
| `replace_count` | — | placeholder Fase 5 |
| `post_only_attempted` | — | placeholder Fase 4 |
| `adverse_selection_1s/3s/5s` | — | placeholder Fase 7 |

**Frontend — panel Execution Quality:**
- Aparece automaticamente cuando hay datos con `n=X` ordenes
- Muestra `Avg Slippage bps`, `Avg IS bps`, `Total IS cost $` con alertas de color

---

### ✅ Fase 2 — Fill Simulator multinivel (`v1.1-b`)

**Objetivo:** estimar el costo esperado real de una orden usando la profundidad actual del book.

**Implementado en:**
- `backend/services/execution_engine.py` — modulo nuevo, pura logica sin side-effects
- `backend/services/event_manager.py` — llamada al simulador antes del pre-log
- `frontend/src/components/analytics/OrderDiagnosticModal.tsx` — seccion 3. Fill Simulator

**Modulo `execution_engine.py`:**
- `estimate_fill(asks, notional_usd, mid)` — walk multinivel del order book
- `estimate_fill_from_event(event_dict, side, notional_usd, mid)` — wrapper sobre event_dict
- `fill_estimate_to_log(est)` — convierte a dict plano para CSV
- Funciona igual en paper mode y live mode (solo lee el book)

**Campos nuevos en CSV:**

| Campo | Que mide |
|---|---|
| `expected_avg_fill_price` | precio promedio estimado antes de enviar |
| `fill_sim_worst_price` | precio del nivel mas profundo tocado |
| `fill_sim_fillable_notional` | cuanto USD puede absorber el book |
| `fill_sim_fillable_shares` | shares recibibles |
| `fill_sim_levels_consumed` | niveles necesarios |
| `fill_sim_slippage_vs_ask_bps` | slippage estimado sobre best ask |
| `fill_sim_slippage_vs_mid_bps` | IS estimado vs mid |
| `fill_sim_book_consumption_pct` | % del book visible consumido |
| `fill_sim_fully_fillable` | 1 si el book puede absorber la orden completa |

**Frontend — modal seccion 3:**
- Muestra todos los campos del simulador por orden
- `Sim error` = `fill_real − expected` en bps — calibrador de precision del simulador

---

### ✅ Fase 3 — Execution EV Gate (`v1.1-b`)

**Objetivo:** bloquear trades cuyo edge desaparece despues de execution costs.

**Implementado en:** `backend/services/event_manager.py` — gate justo antes del pre-log

**Regla:**
```
si execution_enabled = true
y expected_avg_fill_price disponible
y quant_prob - expected_avg_fill_price < execution_min_net_edge_pct / 100
=> NO TRADE (gate desbloquea para re-trigger en siguiente tick)
```

**Settings nuevos con defaults conservadores:**
```json
"execution_enabled": false,
"execution_min_net_edge_pct": 2.0
```

**Para activar** cuando haya >= 100 ordenes con `fill_sim_*` logueados y el `Sim error` sea consistentemente bajo:
```json
"execution_enabled": true,
"execution_min_net_edge_pct": 2.0
```

**Validado:** con book normal y $15 de notional el gate siempre pasa (slippage = 0 bps sobre ask). Solo bloquea cuando el book esta thin y el fill price sube.

---

### ⏳ Fase 4 — Execution Mode Selector (`v1.1-c`)

**Objetivo:** decidir explicitamente como ejecutar cada oportunidad.

**Prerequisito:** >= 100 ordenes con observabilidad activa + `Sim error` calibrado.

Modos propuestos:

- `maker_limit` — spread ancho + edge estable
- `aggressive_limit` — edge bueno pero poco tiempo hasta cierre
- `price_capped_fak` — liquidez visible en best ask, ejecutar directo
- `no_trade` — edge no sobrevive a execution costs

Idea de seleccion:

- spread ancho + edge estable => `maker_limit`
- edge bueno pero poco tiempo => `aggressive_limit`
- liquidez gift visible => `price_capped_fak`
- si no cierra neto => `no_trade`

Resultado esperado:

- `FAK` deja de ser el modo principal y pasa a ser herramienta tactica.
- `maker_vs_taker_mode` en CSV empieza a tener valores reales.

---

### ⏳ Fase 5 prerequisito — Order Monitor Loop (`v1.2-pre`)

Antes de implementar lifecycle de ordenes vivas, se necesita un loop dedicado en `event_manager.py`.

Hoy no existe un loop que monitoree ordenes abiertas en background.

Agregar:

- `_order_monitor_loop()` — tarea asyncio que corre en background,
- registra ordenes abiertas por `order_id`,
- cancela si el edge desaparece o el precio se mueve fuera de umbral,
- envia evento interno para reponer si conviene.

Sin esto, la Fase 5 no es implementable de forma robusta.

---

### ⏳ Fase 5 — Lifecycle de ordenes vivas (`v1.2`)

**Prerequisito:** Fase 4 implementada + Order Monitor Loop.

**Objetivo:** gestionar ordenes abiertas como un execution engine real.

Capacidades:

- publicar limit,
- esperar ventana corta,
- cancelar si desaparece el edge,
- cancelar si el mercado se mueve,
- reponer a mejor precio si conviene,
- expirar sin trade si ya no cierra EV.

Resultado esperado:

- captura parcial de spread,
- menos agresion innecesaria,
- menos adverse selection.

---

### ⏳ Fase 6 — Sizing depth-aware (`v1.3`)

**Objetivo:** que el sizing no dependa solo de Kelly y caps, sino tambien del costo real de liquidez.

Reglas sugeridas:

- limitar stake por `avg_fill_price`,
- limitar stake por `worst_fill_price`,
- limitar stake por porcentaje maximo del book consumido,
- evitar que el bot se auto-destruya cruzando demasiada profundidad.

**Nota:** con capital actual ($10-$20) este sizing es practicamente irrelevante (book_consumption_pct < 3%). Aplica cuando el capital crezca.

---

### ⏳ Fase 7 — Heuristicas anti-adverse-selection (`v1.4`)

**Objetivo:** evitar fills que solo llegan cuando el mercado va en contra.

Ideas iniciales:

- abortar si el mid empeora inmediatamente despues del fill,
- bajar agresion si el fill rate ocurre solo en micro-movimientos adversos,
- evitar repostear cuando el top-of-book se retira sistematicamente,
- medir deterioro del precio a 1s, 3s y 5s post-fill.

**Nota de complejidad:** esta fase requiere timers concurrentes dentro del event loop asyncio para medir deterioro post-fill. Es la fase mas compleja tecnicamente. Tratar como `v1.4` o investigacion separada, no bloquear fases anteriores por esto.

---

### ⏳ Fase 8 — Opportunity Cost de no-fills (`v1.2`)

**Objetivo:** medir el costo real de no ejecutar cuando habia edge.

Contexto:

- pasar a maker-first reduce slippage pero aumenta riesgo de non-fill,
- sin medir opportunity cost, el rediseño puede parecer exitoso en slippage pero perder PnL neto por oportunidades no capturadas.

Metricas a agregar:

- `order_expired_without_fill` — orden limit que vencio sin llenarse,
- `edge_at_expiry` — edge estimado al momento de cancelar,
- `opportunity_cost_usd` — edge_at_expiry * notional_usd (lo que se dejo sobre la mesa),
- `non_fill_rate` — porcentaje de intentos maker que no llenaron.

Resultado esperado:

- poder comparar: `slippage_ahorrado_maker` vs `opportunity_cost_non_fill`,
- validar que el modo maker tiene PnL neto superior, no solo slippage inferior.

---

## Archivos tocados

Backend:

- `backend/services/event_manager.py` — campos nuevos, fill simulator, EV gate, defaults
- `backend/services/execution_engine.py` — modulo nuevo (fill simulator)

Frontend:

- `frontend/src/components/analytics/OpportunitiesDashboard.tsx` — tipos + panel Execution Quality
- `frontend/src/components/analytics/OrderDiagnosticModal.tsx` — tipos + seccion Fill Simulator + metricas CLOB

## Archivos pendientes de tocar

Backend:

- `backend/routers/trading.py`
- `core/client_wrapper.py`
- `backend/models/schemas.py`

Frontend:

- `frontend/src/types/events.ts`
- `frontend/src/components/layout/Sidebar.tsx`

---

## Settings nuevos implementados

Planos en `runtime_settings.json` (opt-in, defaults = comportamiento actual):

```json
"execution_enabled": false,
"execution_min_net_edge_pct": 2.0
```

Settings pendientes para fases futuras:

```json
"execution_mode": "fak",
"maker_max_wait_ms": 3000,
"maker_reprice_interval_ms": 1000,
"maker_max_replaces": 2,
"maker_post_only_enabled": false,
"aggressive_limit_tolerance_pct": 0.01,
"fak_price_cap_pct": 0.02,
"depth_sizing_enabled": false,
"max_book_consumption_pct": 0.20,
"adverse_selection_abort_enabled": false
```

---

## Orden de implementacion

| # | Version | Descripcion | Estado |
|---|---|---|---|
| 1 | `v1.1-a` | Observabilidad + analytics de execution | ✅ Listo |
| 2 | `v1.1-b` | Fill simulator + Execution EV Gate | ✅ Listo |
| 3 | `v1.1-c` | Execution Mode Selector | ⏳ Requiere >= 100 ordenes observadas |
| 4 | `v1.2-pre` | Order Monitor Loop | ⏳ Prerequisito de v1.2 |
| 5 | `v1.2` | Lifecycle maker-first + Opportunity Cost | ⏳ Requiere v1.2-pre + v1.1-c |
| 6 | `v1.3` | Sizing depth-aware | ⏳ Requiere capital mayor |
| 7 | `v1.4` | Anti-adverse-selection | ⏳ Investigacion separada |

**Pausa de validacion obligatoria entre v1.1-b y v1.1-c:**

- Correr en paper mode preferentemente lunes-miercoles 7-10 AM MX.
- Esperar >= 100 ordenes con `fill_sim_*` logueados.
- Verificar que `Sim error` (fill_real - expected) sea consistentemente < 5 bps.
- Solo entonces activar `execution_enabled: true` y avanzar a v1.1-c.

---

## Criterio de exito

El rediseño va bien si se cumplen **todos** estos criterios medidos sobre un minimo de 200 ordenes resueltas en produccion:

| Metrica | Condicion de exito |
|---|---|
| `realized_slippage_bps` promedio | baja al menos 20 bps vs baseline |
| `implementation_shortfall_bps` promedio | baja al menos 15 bps vs baseline |
| `non_fill_rate` (maker) | menor al 30% de intentos |
| PnL neto | igual o superior al baseline con misma cantidad de trades |
| `opportunity_cost_usd` acumulado | no supera el `slippage_ahorrado` acumulado |

Si al llegar a 200 ordenes el PnL neto es inferior al baseline aunque el slippage sea menor, el modo maker no se valida y se revierte a FAK por defecto.

---

## Nota final

No intentar hacer todo en una sola iteracion.

La mejora mas rentable y menos riesgosa al inicio es:

- medir mejor,
- simular fill real,
- y bloquear trades cuyo edge ya no sobrevive a execution.

Ese es el camino mas corto desde el bot actual a un execution engine serio.
