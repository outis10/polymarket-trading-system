# Bot Auto-Order System — Documentación Técnica

## 1. Descripción General

El sistema de auto-orden del bot es un módulo del backend (`event_manager.py`) que monitorea el estado del **Quant Gate** en tiempo real. Cuando detecta que el gate pasa de **deshabilitado → habilitado** para un evento/lado específico, coloca automáticamente una orden de compra en Polymarket sin intervención del usuario.

El frontend recibe el resultado vía WebSocket y muestra un toast de confirmación en el card del evento.

---

## 2. Componentes Principales

| Componente | Archivo | Rol |
|---|---|---|
| `_bot_maybe_place_order` | `event_manager.py` | Lógica principal de colocación de órdenes |
| `_update_live` | `event_manager.py` | Loop que dispara el bot cada tick |
| `_bot_prev_gate_enabled` | `event_manager.py` | Diccionario de estado previo del gate por `(event_id, side)` |
| `_bot_pending_orders` | `event_manager.py` | Set de órdenes en vuelo (anti-duplicados) |
| `validate_order_risk_guards` | `event_manager.py` | Validaciones de riesgo previas a la orden |
| `register_order_fill` | `event_manager.py` | Registra la orden ejecutada para futuros controles |
| `bot_order_placed` handler | `useWebSocket.ts` | Recibe resultado por WS e inyecta en el store |
| Bot toast | `EventCard.tsx` | Muestra el resultado al usuario por 6 segundos |

---

## 3. Flujo de Datos

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  BACKEND — Loop principal (cada `refresh_rate` segundos, default: 1s)       │
│                                                                              │
│  _update_loop()                                                              │
│       │                                                                      │
│       ▼                                                                      │
│  _update_live()                                                              │
│       │                                                                      │
│       ├── Para cada event_id en self.events:                                 │
│       │       │                                                              │
│       │       ├── Actualiza precios (Binance/Chainlink REST)                 │
│       │       ├── Calcula quant_prob_up / quant_prob_down                    │
│       │       ├── Evalúa Quant Gate → quant_buy_gate.up / .down             │
│       │       │       │                                                      │
│       │       │       └── _compute_quant_buy_gate_side()                    │
│       │       │               ├── Verifica min_prob                         │
│       │       │               ├── Verifica min_sample                       │
│       │       │               ├── Verifica min_edge_pct                     │
│       │       │               ├── Verifica min_diff_pct                     │
│       │       │               ├── Verifica price range (10–90¢)             │
│       │       │               └── Retorna { enabled: true/false, ... }      │
│       │       │                                                              │
│       │       └── Si trading_mode == "bot":                                 │
│       │               └── asyncio.create_task(_bot_maybe_place_order())     │
│       │                   (fire-and-forget, una tarea por side)             │
│       │                                                                      │
└───────┼──────────────────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  _bot_maybe_place_order(event_id, event_dict, side)                          │
│                                                                              │
│  1. Lee quant_buy_gate[side].enabled  (estado actual)                       │
│  2. Lee _bot_prev_gate_enabled[(event_id, side)]  (estado anterior)         │
│  3. Actualiza el estado anterior con el actual                              │
│                                                                              │
│  ┌─ ¿Transición disabled→enabled? ──────────────────────────────────────┐  │
│  │  ¿(prev=False AND now=True)?                                          │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│       │ NO → return (sin acción)                                            │
│       │ SI → continuar                                                      │
│       │                                                                      │
│  4. ¿Está en _bot_pending_orders? → return (anti-duplicado)                 │
│  5. Agrega key a _bot_pending_orders                                        │
│                                                                              │
│  6. Obtiene ask_price del order book (o side_price como fallback)           │
│  7. Calcula Kelly stake:                                                    │
│       edge = quant_prob - ask_price                                         │
│       kelly = edge / (1 - ask_price)  × fraction                           │
│       stake_usd = min(kelly × bankroll, max_bet_pct, hard_cap)             │
│       shares = stake_usd / ask_price                                        │
│                                                                              │
│  8. Obtiene balance live vía asyncio.to_thread(client.get_balance)          │
│  9. validate_order_risk_guards() ────────────────────────────────────────┐  │
│       ├── min_shares / min_notional                                       │  │
│       ├── global_cooldown (seg entre órdenes globales)                    │  │
│       ├── max_buys_per_event_side (por día)                               │  │
│       ├── event_side_cooldown (seg entre órdenes del mismo evento/side)   │  │
│       ├── bot_order_notional_cap_usd (hard cap en USD)                    │  │
│       ├── bot_max_event_exposure_pct (% bankroll por evento)              │  │
│       └── bot_max_ticker_exposure_pct (% bankroll por ticker)             │  │
│  ◄────────────────────────────────────────────────────────────────────────┘  │
│       │ blocked → log + return                                              │
│       │ allowed → continuar                                                 │
│                                                                              │
│  10. client.place_order(token_id, "BUY", ask_price, shares)                 │
│       (vía asyncio.to_thread para no bloquear el event loop)               │
│                                                                              │
│  11. register_order_fill() → guarda en _order_guard_records                 │
│  12. Broadcast WS: bot_order_placed                                         │
│  13. Broadcast WS: balance_update                                           │
│  14. finally: _bot_pending_orders.discard(key)                              │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
        │
        ▼  (WebSocket)
┌─────────────────────────────────────────────────────────────────────────────┐
│  FRONTEND — useWebSocket.ts                                                  │
│                                                                              │
│  case "bot_order_placed":                                                    │
│       ├── Actualiza bankrollReal en accountStore (si hay balance)           │
│       └── updateEvent(event_id, { _bot_last_order: data })                  │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
        │
        ▼  (React re-render)
┌─────────────────────────────────────────────────────────────────────────────┐
│  FRONTEND — EventCard.tsx                                                    │
│                                                                              │
│  useEffect detecta cambio en event._bot_last_order (via useRef)             │
│       └── setBotTradeResult("⚡ Bot: BUY UP 2.34 sh @ 0.4200 ($0.98)")      │
│                                                                              │
│  Toast visible 6 segundos → se limpia automáticamente                       │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Detección de Transición de Gate

El mecanismo clave del bot es detectar **únicamente** el momento en que el gate cambia de estado:

```
Tick N-1:  gate.enabled = false  →  prev = false
Tick N:    gate.enabled = true   →  prev = false  ✓ DISPARA ORDEN
Tick N+1:  gate.enabled = true   →  prev = true   ✗ Ya disparado, no repite
Tick N+2:  gate.enabled = false  →  prev = false  ← Resetea
Tick N+3:  gate.enabled = true   →  prev = false  ✓ DISPARA ORDEN (nueva señal)
```

Esto garantiza que el bot **no envíe órdenes repetidas** mientras el gate sigue activo.

---

## 5. Soporte Multi-Evento

El bot escala linealmente con el número de eventos activos. Por cada tick:

- Se lanza `2 × N` tareas asíncronas (N eventos × 2 sides)
- Cada tarea es completamente independiente gracias a que las claves del estado incluyen `event_id`:

```python
_bot_prev_gate_enabled: dict[tuple[str, str], bool]
# Ejemplos de claves:
# ("btc_5m_event_abc123", "up")
# ("btc_5m_event_abc123", "down")
# ("eth_5m_event_xyz789", "up")
```

- Las órdenes de un evento no afectan los guards de otro evento (salvo `ticker_exposure` y `global_cooldown`)

---

## 6. Risk Guards — Resumen

| Guard | Setting | Descripción |
|---|---|---|
| Min shares | `pm_min_shares` | Mínimo de shares por orden (default: 5) |
| Min notional | `pm_min_notional_usd` | Mínimo en USD por orden (default: $1) |
| Hard cap | `bot_order_notional_cap_usd` | Máximo en USD por orden (default: $5) |
| Global cooldown | `bot_global_min_seconds_between_orders` | Segundos entre órdenes de cualquier tipo (default: 2s) |
| Max buys/side | `bot_max_buys_per_event_side` | Máximo de compras por evento/side por día (default: 2) |
| Side cooldown | `bot_cooldown_seconds_per_event_side` | Segundos entre compras del mismo evento/side (default: 60s) |
| Event exposure | `bot_max_event_exposure_pct` | % del bankroll máximo por evento (default: 15%) |
| Ticker exposure | `bot_max_ticker_exposure_pct` | % del bankroll máximo por ticker (default: 25%) |

---

## 7. Kelly Sizing

```
edge  = quant_prob - ask_price
kelly = edge / (1 - ask_price)          ← Kelly crudo
kelly_fracc = kelly × kelly_fraction    ← Fracción configurada (default: 25%)
kelly_final = min(kelly_fracc, max_bet_pct/100, max_event_pct/100)
stake_usd   = kelly_final × bankroll
shares      = min(stake_usd, hard_cap) / ask_price
```

Si `kelly_enabled=false`, usa directamente `bot_order_notional_cap_usd` como stake.

---

## 8. Archivos Involucrados

| Archivo | Función |
|---|---|
| `backend/services/event_manager.py` | Loop principal, gate evaluation, bot logic, risk guards |
| `backend/core/client_wrapper.py` | `place_order`, `get_balance` via Polymarket CLOB API |
| `frontend/src/hooks/useWebSocket.ts` | Handler `bot_order_placed` |
| `frontend/src/components/EventCard.tsx` | Toast de resultado de orden bot |
| `frontend/src/components/layout/Sidebar.tsx` | Control `trading_mode` (bot/manual) |
| `backtest_output/runtime_settings.json` | Configuración en runtime (persiste entre reinicios) |
