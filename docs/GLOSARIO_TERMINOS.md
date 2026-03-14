# Glosario de Terminos - Polymarket Trading System

Este glosario resume los terminos operativos usados en backend, frontend, logs y analytics.

## 1) Mercado y evento

- **Evento**: mercado binario de Polymarket que resuelve en `UP` o `DOWN`.
- **Ticker**: activo subyacente (ej. `BTC`, `ETH`, `SOL`, `XRP`).
- **Timeframe**: duracion del evento (ej. `5m`, `15m`, `1h`).
- **Price To Beat (PTB)**: precio objetivo/referencia contra el cual se decide `UP` o `DOWN`.
- **Diff vs PTB**: diferencia entre precio actual del subyacente(del ticker) y `price_to_beat`.
- **Slot**: sub-bloque temporal dentro del evento (en 5m/10s hay 30 slots).
- **Range**: bin/rango de diferencia de precio usado por el modelo quant.

## 2) Probabilidades y edge

- **Prob Up**: probabilidad estimada por el modelo de que el evento cierre `UP`.
- **Prob Down**: probabilidad estimada de `DOWN` (`1 - Prob Up`).
- **Market Prob**: probabilidad implicita de mercado, aproximada por el precio.
- **Side**: direccion tomada en la orden/decision (`UP` o `DOWN`).
- **QE (Quantum Edge)**: ventaja del modelo frente al mercado en el momento de decision/envio.
- **edge_pct**: edge al enviar la orden (benchmark de envio).
- **edge_at_fill_pct**: edge recalculado contra precio real de fill.
- **delta_edge_pct**: cambio de edge por ejecucion (`edge_at_fill_pct - edge_pct`).

## 3) Ejecucion y order book

- **Best Bid**: mejor precio comprador disponible.
- **Best Ask**: mejor precio vendedor disponible.
- **Mid**: punto medio entre best bid y best ask.
- **Spread**: diferencia `ask - bid`.
- **Spread %**: spread relativo en porcentaje.
- **Arrival Price**: precio de referencia al momento de enviar la orden.
- **Fill Price**: precio real al que se ejecuto la orden.
- **Shares**: cantidad de contratos/participaciones.
- **Stake $ / Notional USD**: monto en USD asignado a una orden.
- **Fill Count**: numero de fills parciales que compusieron la ejecucion total.
- **No Fill**: orden enviada que no encontro contrapartida ejecutable.

## 4) Slippage y friccion

- **Slippage**: diferencia entre precio esperado (arrival) y precio real (fill).
- **Slippage Signed (convencion TCA)**:
  - Buy: `fill - arrival`
  - Sell: `arrival - fill`
  - Positivo = peor ejecucion/coste.
- **Slippage %**: slippage expresado en porcentaje.
- **Slippage bps**: slippage en puntos base (`1 bps = 0.01%`).
- **Implementation Shortfall**: costo monetario total de ejecucion vs benchmark.
- **Friccion**: costo agregado por spread, slippage, fees y latencia.

## 5) Kelly y sizing

- **Kelly**: metodo de sizing basado en ventaja estimada y odds/precio.
- **kelly_pct**: fraccion de bankroll sugerida para la apuesta.
- **Kelly Fraction**: multiplicador sobre Kelly crudo (ej. `0.25x`, `0.5x`, `1x`).
- **Bankroll**: capital base para calcular tamano de posicion.
- **kelly_live_bankroll_usd**: bankroll usado en modo live.
- **kelly_paper_bankroll_usd**: bankroll usado en modo paper.
- **bot_order_notional_cap_usd**: tope fijo por orden en USD.
- **pm_min_shares**: minimo de shares exigido por exchange.
- **pm_min_notional_usd**: minimo de notional USD exigido por exchange.

## 6) Quant Gate

- **Quant Gate**: filtro de elegibilidad antes de habilitar compra bot.
- **quant_gate_min_sample**: muestra historica minima para validar bin.
- **quant_gate_min_edge_pct**: edge minimo requerido para habilitar orden.
- **quant_gate_edge_vs_ask_enabled**: exige edge contra `best_ask`.
- **quant_gate_min_edge_vs_ask_pct**: umbral minimo de edge contra ask.
- **ask_is_proxy**: indica que no hay ask real y se uso precio proxy.
- **strong signal threshold**: umbral de probabilidad para tratar senal como fuerte.
- **quant_gate_min_sample_strong_signal**: muestra minima reducida para senal fuerte.
- **early/late window**: overrides del gate al inicio/final del evento.
- **min_diff_pct**: filtro minimo porcentual de distancia vs PTB.

## 7) Risk guardrails del bot

- **bot_risk_enabled**: activa/desactiva guardrails de riesgo.
- **bot_max_buys_per_event_side**: limite de compras por evento (actualmente aplicado a evento total).
- **bot_cooldown_seconds_per_event_side**: cooldown por evento/side.
- **bot_global_min_seconds_between_orders**: enfriamiento global entre ordenes.
- **bot_max_event_exposure_pct**: exposicion maxima por evento.
- **bot_max_ticker_exposure_pct**: exposicion maxima por ticker.
- **bot_enforce_timeframe_filter**: obliga al bot a respetar timeframe seleccionado.
- **Risk guard blocked**: rechazo de orden por reglas de riesgo.

## 8) Tracking, resultados y analytics

- **Signal detected**: oportunidad identificada por el sistema.
- **Signal registered**: oportunidad registrada como ejecutable.
- **Blocked opportunity**: oportunidad detectada pero no registrada por bloqueos.
- **WON**: resultado binario al resolver el evento para la direccion tomada.
- **PnL Sim**: resultado simulado bruto.
- **PnL Adj**: PnL simulado ajustado por friccion.
- **Win Rate**: porcentaje de operaciones ganadoras.
- **Max Drawdown**: caida maxima acumulada de equity.
- **Pipeline EV Curve (In-Sample)**: curva de ventaja modelada en muestra de entrenamiento.
- **Out-of-Sample (Walk-Forward)**: evaluacion con ventanas train/test sin leakage temporal.

## 9) Modos de operacion

- **Paper Mode**: simulacion sin enviar orden real a mercado.
- **Live Mode**: ejecucion real contra mercado.
- **Fallback Binance**: uso de Binance como fuente de precio cuando aplica fallback.
- **Quant Source**: fuente del modelo quant usado por evento (`pm_5m_slot_ranges` o fallback legado).

## 10) Seguridad y acceso

- **Login Password (frontend)**: barrera de acceso visual a la UI.
- **API Key (backend)**: autenticacion para REST y WebSocket.
- **X-API-Key**: header de autenticacion en llamadas REST.
- **WS api_key query param**: clave para autenticacion en WebSocket.
- **CORS / ALLOWED_ORIGINS**: origenes permitidos para el frontend.

## 11) Archivos operativos frecuentes

- `config/runtime_settings.json`: fuente de verdad de settings en runtime.
- `backtest_output/paper_trades.csv`: decisiones/resultado paper.
- `backtest_output/bot_orders_YYYY-MM-DD.csv`: ordenes bot live/paper fallback.
- `backtest_output/order_blocked_log.csv`: bloqueos de orden por reglas.
- `backtest_output/opportunities_log.csv`: oportunidades registradas.
- `backtest_output/opportunity_outcomes.csv`: outcomes de oportunidades.

## 12) Convenciones recomendadas

- En slippage/TCA: **positivo = peor ejecucion**.
- Mantener en tablas al menos: `Prob Up`, `Prob Down`, `Market Prob`, `Side`, `WON`.
- Usar `edge_at_fill_pct` para evaluar calidad real post-ejecucion.

Ventanas con buena liquidez en BTC Polymarket

 ┌──────────────────────────┬─────────────────┬────────────────────────────────────────────────────────┐
 │         Ventana          │ Hora local (MX) │                        Por qué                         │
 ├──────────────────────────┼─────────────────┼────────────────────────────────────────────────────────┤
 │ US pre-market + apertura │ 6:30 – 10:00 AM │ Mayor volumen BTC, book más profundo, spreads angostos │
 ├──────────────────────────┼─────────────────┼────────────────────────────────────────────────────────┤
 │ Overlap US + Europa      │ 6:00 – 9:00 AM  │ El mejor momento del día para BTC                      │
 ├──────────────────────────┼─────────────────┼────────────────────────────────────────────────────────┤
 │ Tarde US                 │ 12:00 – 2:00 PM │ Segunda ola de liquidez                                │
 └──────────────────────────┴─────────────────┴────────────────────────────────────────────────────────┘

 Ventanas a evitar para pruebas limpias

 ┌───────────┬───────────────────────────────┬───────────────────────────────────────────────────────────────────────────────────────────────────────────┐
 │  Evento   │            Cuándo             │                                                  Por qué                                                  │
 ├───────────┼───────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────────┤
 │ FOMC      │ Miércoles ~6:00 AM MX         │ Book se vacía antes del anuncio                                                                           │
 ├───────────┼───────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────────┤
 │ NFP       │ Primer viernes ~5:30 AM MX    │ Spike de volatilidad, fills atípicos                                                                      │
 ├───────────┼───────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────────┤
 │ CPI       │ Segundo miércoles ~5:30 AM MX │ Igual que NFP                                                                                             │
 ├───────────┼───────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────────┤
 │ Madrugada │ 12 AM – 5 AM MX               │ Liquidez thin, fill simulator va a ver books muy delgados — los datos no representan condiciones normales │
 └───────────┴───────────────────────────────┴───────────────────────────────────────────────────────────────────────────────────────────────────────────┘
