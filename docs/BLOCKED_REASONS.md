# Blocked Reasons Catalog

Guia rapida de codigos de bloqueo (`blocked_reason`) y su significado operativo.

## 1) Quant Gate (`quant_buy_gate.<side>.reasons`)
Estos codigos se generan en `_compute_quant_buy_gate_side(...)` y luego se empaquetan en:
`quant_gate_blocked:<reason_1> | <reason_2> ...`

- `no_quant_data`: no hay probabilidad quant para el lado.
- `prob<NN.NN`: la probabilidad del lado esta por debajo de `min_prob`.
- `sample<N`: el bin/slot no alcanza el minimo de muestra efectivo.
- `diff_pct<NN.NNN%`: la diferencia `%` entre `current_price` y `price_to_beat` es menor al minimo configurado.
- `edge<NN.NN%`: edge del lado por debajo de `min_edge_pct` del gate.
- `no_ask_price`: filtro `edge_vs_ask` activado pero no hay ask real (solo proxy/mid).
- `ask_edge<NN.NN%`: edge vs ask por debajo de `min_edge_vs_ask_pct`.
- `price_outside_X-Yc`: precio de mercado fuera de rango permitido en centavos.
- `no_percentile`: filtro por percentil activado pero no hay percentil.
- `percentile_inside_X-Y`: percentil dentro de zona bloqueada.

## 2) Elegibilidad Unificada (bot/paper/tracking)
Se devuelven desde `evaluate_bot_order_candidate(...)`.

- `timeframe_mismatch`: el evento no coincide con `timeframe_filter`.
- `too_close_to_end`: faltan menos segundos que `bot_min_seconds_before_end`.
- `quant_gate_blocked:...`: el quant gate del lado no esta habilitado (ver seccion 1).
- `ask_price_outside_range`: ask actual fuera de `quant_gate_min_price_c` / `quant_gate_max_price_c`.
- `kelly_disabled`: Kelly esta desactivado.
- `no_quant_prob`: no existe `quant_prob_up/down` para ese lado.
- `edge_below_min`: edge vs ask por debajo de `kelly_min_edge_pct`.
- `invalid_side_price`: precio del lado/ask invalido (`<= 0`).
- `stake_non_positive`: stake resultante no positivo.
- `risk_guard_blocked`: fallback generico cuando falla un risk guard sin codigo especifico.

Nota: normalmente, cuando falla risk guard, se retorna el codigo especifico de la seccion 3.

## 3) Risk Guards (`validate_order_risk_guards`)
Estos aplican a ordenes bot, paper y manuales (compra).

- `ticker_disabled_by_monitored_tickers`: ticker no habilitado en `monitored_tickers`.
- `invalid_shares`: `shares <= 0`.
- `invalid_notional`: `notional_usd <= 0`.
- `shares_below_min_<N>`: shares por debajo de `pm_min_shares`.
- `notional_below_min_<N>`: notional por debajo de `pm_min_notional_usd`.
- `global_order_cooldown_active`: cooldown global entre ordenes activo.
- `max_buys_per_event_reached`: se alcanzo el maximo de compras por evento del dia.
- `event_cooldown_active`: cooldown por evento activo.
- `already_bought_up_this_event` / `already_bought_down_this_event`: bloqueo por lado opuesto ya comprado en el evento.
- `order_notional_above_cap_<N>`: supera `bot_order_notional_cap_usd`.
- `event_exposure_cap_reached`: supera cap de exposicion por evento.
- `ticker_exposure_cap_reached`: supera cap de exposicion por ticker.

## 4) `/api/orders` (respuesta HTTP 403)
En ordenes manuales se envian razones normalizadas para logging/auditoria:

- `timeframe_mismatch`
- `too_close_to_end`
- `quant_gate_blocked`
- `risk_guard_blocked`

Ademas, en `detail` puede venir informacion enriquecida (ej. `quant_prob`, `ask`, `edge_pct`, `sample`, etc.).

## 5) Donde se registran
- Oportunidades bloqueadas (tracker): `backtest_output/opportunity_blocked.csv`
- Ordenes bloqueadas (REST): `backtest_output/order_blocked_log.csv`

## 6) Referencias de codigo
- `backend/services/event_manager.py`
  - `_compute_quant_buy_gate_side(...)`
  - `evaluate_bot_order_candidate(...)`
  - `validate_order_risk_guards(...)`
- `backend/routers/trading.py`
  - validaciones previas de `POST /api/orders`
