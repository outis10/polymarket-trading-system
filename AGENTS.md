# AGENTS

## Continuidad de contexto

Este archivo guarda contexto operativo para futuras conversaciones.
Actualízalo cuando cambien decisiones, scripts o flujos importantes.

## Estado actual (2026-02-13)

- Script de agregación vigente: `aggregate_pm_15m_ranges.py`.
- Uso documentado en `README.md` (sección "Agregación de rangos PM (15m)").
- Guía de export Binance disponible en `GUIA_EXPORT_BINANCE.md`.

## Comandos clave

```bash
python3 aggregate_pm_15m_ranges.py \
  --input btcusdt_multiframe.xlsx \
  --sheet 1min \
  --output backtest_output/pm_ranges.csv
```

```bash
python3 aggregate_pm_15m_ranges.py \
  --input btcusdt_multiframe.xlsx \
  --sheet 1min \
  --output backtest_output/pm_ranges.csv \
  --range-step 10 \
  --min-count 20 \
  --prob-source event_outcome \
  --bayes-smoothing \
  --prior-alpha 1 \
  --prior-beta 1 \
  --exclude-minute-15
```

## Convención para nuevas sesiones

Cuando se pida "usar contexto previo", revisar primero:
1. `AGENTS.md`
2. `README.md`
3. `GUIA_EXPORT_BINANCE.md`

Si hay discrepancias, priorizar el código fuente y luego actualizar este archivo.

## Estado actual (2026-02-14)

- Frontend rediseñado a cards compactas tipo Polymarket.
- `Quick Trade` renombrado a `Manual Trade` con toggle `Hide/Show` por card.
- `Order Flow` movido debajo de `Manual Trade`.
- Filtro en UI por `timeframe` (`5m`, `15m`, `1h`) desde Sidebar.
- En `live`, UI muestra solo mercados activos (`start <= now < end`) y del timeframe seleccionado.
- Endpoint manual agregado: `POST /api/events/refresh-live`.
- Auto-discovery de eventos live desde Gamma implementado (`backend/services/event_discovery.py`).
- Stream de precios optimizado:
  - updates incrementales (`price_update`) en WS,
  - snapshot completo menos frecuente,
  - price history agregado con menor frecuencia.
- Integración base para Chainlink streams:
  - nuevo servicio `backend/services/chainlink.py`,
  - configuración `live_pricing` en `config/events.yaml`,
  - fallback a Binance si Chainlink no está configurado.
- Mientras llegan credenciales Chainlink, sistema operativo con Binance fallback.

## Pendientes para mañana

1. Configurar `live_pricing.chainlink_stream_url` y `live_pricing.chainlink_subscribe` con credenciales reales.
2. Validar formato exacto de payload del stream Chainlink (mapeo `symbol/price`) y ajustar parser si hace falta.
3. Medir latencia real end-to-end (`tick -> UI`) y ajustar `snapshot_every_n_ticks` / carga de order book.
4. (Opcional) Separar actualización de order book en un canal/ritmo distinto para más fluidez visual.

## Estado actualizado (2026-02-14, cierre del dia)

- `Manual Trade` se mantiene como panel normal.
- `Bot Trade` ahora muestra 2 subcards por evento:
  - `UP` (label + porcentaje en linea separada),
  - `DOWN` (label + porcentaje en linea separada).
- Cada subcard de `Bot Trade` incluye:
  - `KS 0.05% ($13.25)` con tooltip:
    `KS: Apuesta recomendada por Kelly segun probabilidad estimada y gestion de riesgo.`
  - boton `Buy At XXc` dinamico por lado.
- Orden de cards en UI:
  1. BTC
  2. ETH
  3. SOL
  4. XRP
  5. resto en su orden de llegada.
- Grid responsive:
  - en resoluciones `< 1600px`: 2 cards por fila,
  - en resoluciones grandes: layout automatico actual,
  - en `<= 1100px`: 1 card por fila.
- Settings:
  - se agrego toggle `Show Probabilities Card` (oculta/muestra el card completo de probabilidades),
  - se eliminaron toggles sin efecto visible:
    - `Show Probability %`
    - `Show Price Change %`.
- Defaults de `chart_options` simplificados a `["show_chart"]` en frontend y backend.
- Diagnostico de balance/auth:
  - endpoint nuevo: `GET /api/diagnostics/auth`,
  - fix en `core/client_wrapper.py` para `get_balance_allowance` (ahora envia params explicitos requeridos por SDK).

## Proximo bloque (cuando se retome)

Implementar modulo Kelly configurable desde Settings:
1. `Enable Kelly`.
2. `Kelly Fraction` (0.1x/0.25x/0.5x/1x).
3. `Min Edge %`.
4. `Max Bet %`.
5. `Bankroll source` (API/manual) + `Manual bankroll`.
6. Reemplazar `KS` hardcodeado por calculo real `KS % ($)` por cada lado.

## Estado actualizado (2026-02-15)

- MVP de `Range Histogram Card` agregado por evento (basado en `merged_pm_ranges_4cryptos.csv` via `EventManager`).
- Nuevo payload runtime por evento: `quant_range_histogram` (bins por rango, `total_count`, `current_bin_index`, `current_percentile`, `current_diff`).
- Actualizacion de `quant_range_histogram` enviada en `price_update` WS.
- Nuevo toggle en Settings: `Show Range Histogram Card` (usa `hide_range_histogram_card` en `chart_options`).
- `Quant Buy Gate` implementado para botones `Buy At XXc` en `Bot Trade`:
  - backend calcula `quant_buy_gate.up/down` por evento,
  - frontend deshabilita botones cuando `enabled=false` y muestra motivo via tooltip.
- Parametros configurables en Settings:
  - `Enable Quant Gate`,
  - `Min Sample (n)`,
  - `Min Edge %`,
  - `Min/Max Price (c)`,
  - `Use Percentile Filter`,
  - `Percentile Low/High`.
- Filtro por ticker en Settings agregado:
  - `Monitored Tickers` con checkboxes por ticker detectado,
  - la grilla live muestra solo eventos de tickers marcados.
- Fix en discovery de eventos live:
  - para slugs tipo `*-updown-15m-<epoch>`, `<epoch>` se interpreta como `event_end_time` (cierre),
  - `event_start_time` ahora se calcula como `end - timeframe` para alinear `price_to_beat` con Polymarket.
- Quant Gate actualizado con presets de riesgo en Settings:
  - radio `Conservative / Balanced / Aggressive` que autocompleta parametros,
  - perfil por default: `Conservative` (`n=120`, `edge=4%`, `price=10c-90c`, `percentile=15/85`, gate ON),
  - si se editan parametros manualmente, UI muestra estado `Custom`.
- Tracking v1 de oportunidades quant habilitado (solo `live` + `bot`):
  - detecta señal cuando gate pasa `disabled -> enabled` por `event_id + side`,
  - persiste señales en `backtest_output/opportunities_log.csv`,
  - resuelve outcomes al cierre de evento y guarda en `backtest_output/opportunity_outcomes.csv`,
  - stake fijo para proxy PnL: `$100` por señal.
- Endpoints nuevos de estadisticas:
  - `GET /api/stats/opportunities?days=7&ticker=BTC` (resumen por ticker),
  - `GET /api/stats/opportunities/raw?limit=200&ticker=BTC` (filas crudas).
- Criterio actual de resultado (`win/loss`) para tracking v1:
  - se evalua al cierre con `actual_up = close_price >= price_to_beat`,
  - `UP` gana si `actual_up`, `DOWN` gana si `not actual_up`,
  - `close_price` usa `current_price` como proxy de cierre (no settlement oficial de Polymarket).
- Pendiente cuando se cambie de proveedor:
  - reemplazar `close_price` proxy por fuente oficial de resolucion/final price del proveedor activo,
  - mantener compatibilidad historica de metricas (versionar campo `outcome_source`).
