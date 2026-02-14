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
