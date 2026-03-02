# Bot Auto-Order System — Documentación Técnica

## 1. Descripción General

El sistema de auto-orden del bot es un módulo de `event_manager.py` que monitorea el **Quant Gate** en tiempo real. Cuando detecta que el gate pasa de **deshabilitado → habilitado** para un evento/lado, coloca automáticamente una orden de compra en Polymarket sin intervención del usuario.

---

## 2. Componentes Principales

| Componente | Archivo | Rol |
|---|---|---|
| `_bot_maybe_place_order` | `event_manager.py` | Lógica principal — gate, guards, pre-log, CLOB |
| `_update_live` | `event_manager.py` | Loop que dispara el bot cada tick |
| `_bot_prev_gate_enabled` | `event_manager.py` | Estado previo del gate por `(event_id, side)` |
| `_bot_pending_orders` | `event_manager.py` | Set de órdenes en vuelo (anti-duplicados) |
| `_no_fill_cooldown_until` | `event_manager.py` | Cooldown post no_fill por `(event_id, side)` |
| `_order_guard_records` | `event_manager.py` | Historial in-memory de fills para risk guards |
| `_last_claimable_usd` | `event_manager.py` | Claimable USD actualizado por auto-redeem loop |
| `validate_order_risk_guards` | `event_manager.py` | Validaciones de riesgo previas a la orden |
| `register_order_fill` | `event_manager.py` | Registra la orden para futuros controles de exposición |
| `place_fok_order` | `core/client_wrapper.py` | FAK order vía Polymarket CLOB API |
| `_update_bot_order_log_row` | `event_manager.py` | Actualización atómica de fila en CSV |

---

## 3. Flujo Completo

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  _update_loop() → _update_live() — cada refresh_rate segundos (default: 1s) │
│                                                                              │
│  Para cada event_id en self.events:                                          │
│    ├── Actualiza precios (Binance / Chainlink / Kraken REST)                 │
│    ├── Calcula quant_prob_up / quant_prob_down                               │
│    ├── Evalúa Quant Gate → quant_buy_gate.up / .down                        │
│    └── Si trading_mode == "bot":                                             │
│          └── asyncio.create_task(_bot_maybe_place_order())  [fire-forget]   │
└─────────────────────────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  _bot_maybe_place_order(event_id, event_dict, side)                          │
│                                                                              │
│  [GATE CHECK]                                                                │
│  1. ¿Transición disabled→enabled? (prev=False AND now=True) → SI/NO         │
│  2. ¿Key en _bot_pending_orders?                             → SI/NO         │
│  3. ¿Cooldown activo? (no_fill reciente < 20s)               → SI/NO         │
│     SI cualquiera → return (sin acción)                                      │
│                                                                              │
│  [COMPUTE ORDER]                                                             │
│  4. _compute_bot_order(): Kelly sizing + risk guards                         │
│       ├── Drawdown circuit breaker                                           │
│       ├── Event exposure cap                                                 │
│       └── Hard cap USD                                                       │
│     blocked → log opportunity_blocked.csv + return                          │
│                                                                              │
│  [PRE-LOG — antes de tocar el CLOB]                                         │
│  5. _append_bot_order_log(status="sending")                                 │
│  6. register_order_fill()  → _order_guard_records                           │
│  7. _bot_prev_gate_enabled[key] = True  (lockea gate)                       │
│                                                                              │
│  [CLOB]                                                                      │
│  8. asyncio.to_thread(client.place_fok_order,                               │
│          token_id, "BUY", notional_usd, hint_price=ask_price)               │
│       └── MarketOrderArgs(price=ask_price)  → salta get_order_book() extra  │
│                                                                              │
│  [POST-CLOB — happy path]                                                   │
│  9.  _clob_confirmed = True                                                  │
│  10. Extrae fill_price, filled_shares, fills_detail_json                    │
│  11. _update_bot_order_log_row(status="placed", fill data)                  │
│  12. record_position_buy()                                                   │
│  13. Broadcast WS: bot_order_placed + balance_update                        │
│                                                                              │
│  [EXCEPT — error / no liquidez]                                              │
│  Si error == "no orders found" / "no match" / "no orderbook":               │
│       status = "no_fill"                                                     │
│       → _bot_prev_gate_enabled[key] = False  (desbloquea gate)              │
│       → _no_fill_cooldown_until[key] = now + bot_no_fill_cooldown_secs      │
│       → elimina entrada de _order_guard_records                              │
│  Si otro error:                                                              │
│       status = "placed" (si _clob_confirmed) o "failed"                     │
│  → _update_bot_order_log_row(status, fills_detail_json="error:...")         │
│                                                                              │
│  [FINALLY]                                                                   │
│  _bot_pending_orders.discard(key)                                            │
└─────────────────────────────────────────────────────────────────────────────┘
        │
        ▼  (WebSocket)
┌──────────────────────────────────────┐
│  FRONTEND — useWebSocket.ts          │
│  "bot_order_placed" →                │
│    bankrollReal update (accountStore)│
│    updateEvent(_bot_last_order)      │
└──────────────────────────────────────┘
        │
        ▼  (React re-render)
┌──────────────────────────────────────┐
│  EventCard.tsx                        │
│  Toast "⚡ Bot: BUY UP 2.34 sh @ 0.42│
│  visible 6 segundos                  │
└──────────────────────────────────────┘
```

---

## 4. Detección de Transición de Gate

El bot **solo dispara en la transición** disabled→enabled, no en cada tick activo:

```
Tick N-1:  gate=false  prev=false  →  sin acción
Tick N:    gate=true   prev=false  →  ✓ DISPARA ORDEN
Tick N+1:  gate=true   prev=true   →  sin acción (ya disparado)
Tick N+2:  gate=false  prev=false  →  resetea
Tick N+3:  gate=true   prev=false  →  ✓ DISPARA ORDEN (nueva señal)
```

---

## 5. Pre-Log Pattern (resiliencia ante hot-reloads)

El CSV se escribe **antes** de llamar al CLOB para sobrevivir reinicios del servidor:

```
1. _append_bot_order_log(status="sending")   ← CSV escrito
2. register_order_fill()                      ← guards actualizados
3. place_fok_order()                          ← CLOB call
4. _update_bot_order_log_row(status="placed") ← CSV actualizado
```

Si el servidor se reinicia entre los pasos 1 y 4:
- La fila `"sending"` persiste en el CSV
- Al reiniciar, `_load_order_guard_records_from_csv()` carga las filas `placed` y `sending` para reconstruir los guards
- El operador puede revisar manualmente las filas `"sending"` para confirmar si la orden llegó al CLOB

---

## 6. Optimización: hint_price (single round-trip)

**Problema original:** el SDK de Polymarket hacía dos llamadas REST al orderbook por orden:

```
1. fetch_real_prices()              ← REST → best_ask = 0.53
   [200-500ms de procesamiento]
2. create_market_order()
     └─ get_order_book() interno    ← 2do REST call (innecesario)
     └─ post_order()                ← envía la orden
```

**Solución:** `place_fok_order` acepta `hint_price` y lo pasa a `MarketOrderArgs(price=hint_price)`. `create_market_order` omite `get_order_book()` si `price > 0`:

```
1. fetch_real_prices()              ← REST → best_ask = 0.53
   [200-500ms de procesamiento]
2. create_market_order(price=0.53)  ← salta get_order_book()
   post_order()                     ← envía la orden
```

**Resultado:** un round-trip menos, la ventana de race-condition con market makers se reduce ~50%.

El parámetro es opcional (`hint_price=0.0`). Si no se pasa o es 0, el SDK hace el fetch interno como antes.

---

## 7. Manejo de no_fill

Cuando el CLOB devuelve `400 "no orders found to match with FAK order"`, no se gastó USDC. El bot distingue este caso de un error real:

| Status | Causa | USDC gastado | Gate | Retry |
|---|---|---|---|---|
| `placed` | Orden ejecutada | Sí | Bloqueado | N/A |
| `no_fill` | Sin liquidez en orderbook | No | Desbloqueado | Sí, tras cooldown |
| `failed` | Error de código / API error | No | Bloqueado | No |
| `sending` | Servidor reiniciado mid-order | Desconocido | — | Verificar manual |

**Ciclo de retry con cooldown:**

```
no_fill ocurre
  → gate desbloqueado (prev=False)
  → cooldown_until = now + bot_no_fill_cooldown_secs (default: 20s)
  → _order_guard_records limpiado

ticks siguientes (< 20s):
  → cooldown activo → skip

a los 20s:
  → cooldown expirado → gate=True, prev=False → dispara de nuevo
  → si fill → placed ✓
  → si no_fill → nuevo ciclo de cooldown
  → si el evento terminó (gate=False) → nada
```

El motivo del error se guarda en `fills_detail_json` del CSV y es visible en la UI bajo la columna de estado.

---

## 8. Risk Guards

### 8.1 Drawdown Circuit Breaker

Bloquea nuevas órdenes si la equity efectiva cae demasiado respecto al inicio:

```
effective_equity = bankroll_actual + claimable_usd_pendiente
threshold        = start_bankroll × (1 - bot_drawdown_stop_pct / 100)

si effective_equity < threshold → orden bloqueada
```

`_last_claimable_usd` se actualiza cada 30 minutos por el auto-redeem loop en `main.py`.

### 8.2 Event Exposure Cap

Limita la exposición acumulada por evento (suma de todas las órdenes en ese event_id):

```
exposicion_actual = sum(notional_usd para órdenes placed/sending del mismo event_id)
cap_usd           = bankroll × bot_max_event_exposure_pct / 100

si exposicion_actual >= cap_usd → bloqueada
si exposicion_actual + stake > cap_usd → stake recortado al remainder
```

### 8.3 Tabla de Guards

| Guard | Setting | Default | Descripción |
|---|---|---|---|
| Min shares | `pm_min_shares` | 5 | Mínimo de shares por orden |
| Min notional | `pm_min_notional_usd` | $1 | Mínimo en USD por orden |
| Hard cap | `bot_order_notional_cap_usd` | $15 | Máximo en USD por orden |
| Global cooldown | `bot_global_min_seconds_between_orders` | 2s | Seg entre órdenes globales |
| Max buys/side | `bot_max_buys_per_event_side` | 2 | Compras máx por evento/side/día |
| Side cooldown | `bot_cooldown_seconds_per_event_side` | 60s | Seg entre compras mismo evento/side |
| Event exposure | `bot_max_event_exposure_pct` | 15% | % bankroll máx por evento |
| Drawdown stop | `bot_drawdown_stop_pct` | 50% | % de caída máxima desde start_bankroll |
| No-fill cooldown | `bot_no_fill_cooldown_secs` | 20s | Espera entre reintentos por no_fill |

---

## 9. Kelly Sizing

```
edge        = quant_prob - ask_price
kelly_raw   = edge / (1 - ask_price)
kelly_pct   = min(kelly_raw × kelly_fraction, kelly_max_bet_pct/100)
stake_usd   = kelly_pct × bankroll
stake_usd   = min(stake_usd, bot_order_notional_cap_usd)   ← hard cap
shares      = stake_usd / ask_price
notional    = stake_usd                                     ← lo que se pasa al CLOB
```

---

## 10. CSV de Órdenes (`bot_orders_YYYY-MM-DD.csv`)

Rota por día UTC. Columnas clave:

| Columna | Descripción |
|---|---|
| `status` | `sending` / `placed` / `no_fill` / `failed` |
| `fills_detail_json` | Fill detail JSON (placed) o `error:<msg>` (no_fill/failed) |
| `fill_price_real` | Precio real de fill (puede diferir del ask pre-order) |
| `filled_notional_usd_real` | USD realmente gastado |
| `bankroll_usd` | Balance on-chain en el momento de la orden |
| `resolution_status` | `pending` / `resolved` |
| `won` | `1` / `0` / vacío |
| `pnl_simulated` | PnL estimado en USD |

---

## 11. Archivos Involucrados

| Archivo | Función |
|---|---|
| `backend/services/event_manager.py` | Loop principal, gate, bot logic, risk guards, CSV |
| `core/client_wrapper.py` | `place_fok_order` con `hint_price` optimization |
| `backend/main.py` | Auto-redeem loop (actualiza `_last_claimable_usd`) |
| `backend/routers/trading.py` | Órdenes manuales (también usa `place_fok_order`) |
| `frontend/src/hooks/useWebSocket.ts` | Handler `bot_order_placed` |
| `frontend/src/components/EventCard.tsx` | Toast de resultado |
| `frontend/src/components/layout/Sidebar.tsx` | Controls de bot (mode, risk settings) |
| `config/runtime_settings.json` | Configuración persistida (fuente de verdad operativa) |
