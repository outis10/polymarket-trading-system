# AGENTS

## Continuidad de contexto

Este archivo guarda contexto operativo para futuras conversaciones.
Actualízalo cuando cambien decisiones, scripts o flujos importantes.

## Pendientes para próxima sesión

### HTTPS + Nginx (pendiente para cuando se pase a servidor)
- Configurar reverse proxy con Certbot (Let's Encrypt) en EC2/VPS.
- Con HTTPS activo, cambiar WS URL de `ws://` a `wss://` (ya está automático en el código).

### Analytics KPI pendiente (paper vs live sizing)
- Agregar KPI en Analytics para comparar sizing entre modos:
  - `avg stake paper` (desde `paper_trades.csv`)
  - `avg stake live fallback` (estimado por settings/órdenes)
- Objetivo: detectar divergencias de stake entre simulación paper y ejecución live fallback.

### TODO técnico (deuda de compatibilidad bankroll)
- Evaluar remover fallback legado `kelly_bankroll` después de validar que:
  - `kelly_live_bankroll_usd` y `kelly_paper_bankroll_usd` ya están presentes en runtime/settings,
  - no hay clientes/UI antiguos enviando solo `kelly_bankroll`.

### TODO Analytics (Out-of-Sample / Walk-Forward) — pendiente
- Objetivo: validar si hay negocio real del modelo quant sin sesgo in-sample.
- Alcance:
  1. Agregar endpoint backend para curva `pipeline_oos` (walk-forward).
  2. Calcular `train/test` por ventanas temporales usando solo CSV del pipeline.
  3. Exponer en frontend chart separado de `Pipeline EV Curve (In-Sample)`.
- Reglas mínimas propuestas:
  - `train_days=14`, `test_days=1`, rolling diario.
  - Entrenar solo con pasado, evaluar solo en bloque futuro inmediato.
  - Unir todos los bloques test y graficar equity/drawdown OOS.
- Input esperado:
  - `backtest_output/merged_pm_5m_slot_ranges_4cryptos.csv`
- Criterios de aceptación:
  - El chart OOS no reutiliza filas del mismo bloque para entrenar y evaluar.
  - UI muestra claramente etiqueta `Out-of-Sample (Walk-Forward)`.
  - Incluye KPIs: `final_equity`, `max_drawdown`, `avg_ev_per_trade`.

### TODO discusión mañana (métrica EV de pipeline) — pendiente
- Aclaración: la curva `Pipeline EV Curve (In-Sample)` actual (con `2*p-1`) no representa EV de trading real contra mercado.
- Propuesta para discutir/implementar:
  1. Renombrar curva actual a `Model Confidence Curve (In-Sample)`.
  2. Nueva curva `Market-Anchored EV` usando precio de mercado `q`:
     - `EV_yes = p_up - q_yes`
     - `EV_no = (1 - p_up) - q_no`
     - operar solo si `max(EV_yes, EV_no) > 0`.
  3. Backtest real por trade con payoff de precio:
     - YES: `+(1-q_yes)` / `-q_yes`
     - NO:  `+(1-q_no)` / `-q_no`
- Bloqueo actual: el CSV del pipeline no trae `q`; hay que definir fuente de `marketProb` (logs/snapshots/ask histórico por evento-slot).

## Seguridad implementada (2026-02-22)

### Arquitectura de seguridad
Dos capas independientes:
1. **Login de password** — protege el frontend (UI). Cualquiera con la URL ve un login, no la app.
2. **API Key** — protege el backend. Sin la key, ningún REST ni WebSocket funciona.

### Archivos nuevos
- `backend/middleware/auth.py` — `APIKeyMiddleware` (REST) + `verify_ws_api_key()` (WebSocket)
- `frontend/src/auth/useAuth.ts` — `isAuthenticated()`, `login()`, `logout()`, exporta `API_KEY`
- `frontend/src/auth/LoginScreen.tsx` — pantalla de login con password
- `frontend/src/auth/apiFetch.ts` — wrapper de `fetch()` que inyecta `X-API-Key` automáticamente
- `frontend/.env.example` — documenta `VITE_APP_PASSWORD` y `VITE_API_KEY`

### Archivos modificados
- `backend/main.py` — registra `APIKeyMiddleware`, CORS desde `ALLOWED_ORIGINS` en `.env`
- `backend/ws/handlers.py` — WebSocket cierra con código 4401 si key inválida
- `frontend/src/main.tsx` — muestra `LoginScreen` si no autenticado
- `frontend/src/hooks/useWebSocket.ts` — URL del WS incluye `?api_key=...`
- 7 archivos con `fetch()` → reemplazados por `apiFetch()`:
  `Header.tsx`, `Sidebar.tsx`, `EventCard.tsx`, `PositionDisplay.tsx`,
  `TradingPanel.tsx`, `App.tsx`, `OpportunitiesDashboard.tsx`

### Configuración requerida

**Generar API Key:**
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

**Backend — `.env`:**
```
API_KEY=<key generada>
ALLOWED_ORIGINS=https://mi-dominio.com  # o http://localhost:5173 en dev
```

**Frontend — `frontend/.env.local`** (NO commitear):
```
VITE_APP_PASSWORD=<password de acceso a la UI>
VITE_API_KEY=<misma key que el backend>
```

### Comportamiento en dev (sin variables configuradas)
- Sin `VITE_APP_PASSWORD` → no muestra login, acceso directo
- Sin `API_KEY` en backend → no valida headers, acepta todo
- Sin `VITE_API_KEY` → no manda header, funciona igual que antes

### Pendiente
- HTTPS + Nginx en producción (ver sección arriba)

## Actualización Quant diaria (2026-02-22)

### Flujo
Al finalizar cada día de trading correr el pipeline para regenerar el CSV de rangos
con los datos más frescos de Binance (últimos 7 días).

### Comando rápido
```bash
cd /home/narciso/dev/projects/polymarket-trading-system
bash scripts/update_quant.sh
```

El script hace:
1. Corre `run_pm_pipeline_4cryptos_5m_10s.py` con lookback 7 días
2. Llama a `POST /api/quant/reload` — hot-reload sin reiniciar el backend

### Variables opcionales
```bash
LOOKBACK_DAYS=14 bash scripts/update_quant.sh   # más historial
API_KEY=<tu-key> bash scripts/update_quant.sh   # si la seguridad está activa
```

### Endpoint de reload
`POST /api/quant/reload` — recarga `merged_pm_5m_slot_ranges_4cryptos.csv` en caliente.
Implementado en `backend/routers/events.py` + `event_manager.reload_quant_ranges()`.

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
python3 export_binance_klines.py \
  --four-cryptos \
  --interval 1m \
  --months 3 \
  --output-dir backtest_output
```

```bash
python3 export_pm_5m_last_window_1s.py \
  --tickers BTC,ETH,SOL,XRP \
  --lookahead-days 14 \
  --window-seconds 180 \
  --output backtest_output/pm_5m_last180s_1s.csv
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

```bash
python3 run_pm_pipeline_4cryptos_5m_10s.py \
  --lookback-days 7 \
  --slot-seconds 10 \
  --range-step 10 \
  --min-count 20 \
  --output-dir backtest_output
```

## Estado actualizado (2026-02-20, min_diff_pct ticker-agnóstico)

- Reemplazado `early/late_quant_gate_min_abs_diff_usd` por `early/late_quant_gate_min_diff_pct`.
- El nuevo filtro calcula `|current_price - price_to_beat| / price_to_beat * 100`.
  - BTC: $27 diff en $67800 PTB = 0.04%
  - ETH: $0.44 diff en $1964 PTB = 0.022%
  - Ambos comparables con el mismo umbral porcentual.
- Default: `0.0` (desactivado) para early y late — no bloquea por defecto.
- Expuesto en Sidebar: `Early Min Diff (%)` y `Late Min Diff (%)`.
- `reason` en gate: `diff_pct<0.030%` en vez de `diff_abs<15.00`.

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
- Exportador Binance actualizado:
  - `export_binance_klines.py` soporta multi-ticker via `--symbols` y `--four-cryptos`,
  - mantiene formato de CSV compatible con `resample_klines_to_excel.py`,
  - soporta naming por template (`--output-template`) y salida por carpeta (`--output-dir`).
- Script nuevo para hipotesis 5m M3-M4:
  - `export_pm_5m_last_window_1s.py`,
  - descubre eventos PM de 5m y exporta velas Binance `1s` solo en la ventana final (`--window-seconds`),
  - salida consolidada lista para analisis/feature engineering de cierre.
- Criterio actual de resultado (`win/loss`) para tracking v1:
  - se evalua al cierre con `actual_up = close_price >= price_to_beat`,
  - `UP` gana si `actual_up`, `DOWN` gana si `not actual_up`,
  - `close_price` usa `current_price` como proxy de cierre (no settlement oficial de Polymarket).
- Pendiente cuando se cambie de proveedor:
  - reemplazar `close_price` proxy por fuente oficial de resolucion/final price del proveedor activo,
  - mantener compatibilidad historica de metricas (versionar campo `outcome_source`).

## Estado actualizado (2026-02-16)

- Hardening de tracking quant en backend:
  - guardrail temporal para no crear señales cerca/cierre de evento (`close_guard_seconds`),
  - dedupe por `event_id+side` con cooldown (`signal_cooldown_seconds`) y bloqueo de duplicados abiertos,
  - hidratación de estado desde CSV al iniciar para continuidad tras reinicios.
- Reconciliación automática de outcomes:
  - nuevo backfill periódico desde `opportunities_log.csv` -> `opportunity_outcomes.csv`,
  - resuelve señales cerradas pendientes (evita huecos al reiniciar o perder tick de cierre),
  - `minutes_to_close` ahora se clampa a `>= 0`.
- Filtro estricto de universo para tracking:
  - `EventManager` solo trackea oportunidades en eventos cripto válidos,
  - valida consistencia entre ticker (símbolo) y texto del evento (slug/nombre),
  - bloquea mercados no cripto que entren por discovery.

## Estado actualizado (2026-02-16, dashboard analytics)

- Frontend ahora tiene vista separada de analytics de oportunidades:
  - ruta: `/analytics/opportunities`,
  - home live se mantiene en `/`.
- Navegación agregada en header:
  - tabs `Live` y `Analytics` con `history.pushState`.
- Nuevo componente:
  - `frontend/src/components/analytics/OpportunitiesDashboard.tsx`.
  - Consume:
    - `GET /api/stats/opportunities?days=...&ticker=...`
    - `GET /api/stats/opportunities/raw?limit=200&ticker=...`
  - Muestra:
    - KPIs globales (`signals`, `hit rate`, `total pnl`, `avg pnl`),
    - tablas por ticker, lado y timeframe,
    - tabla de outcomes recientes.
- Estilos nuevos en `frontend/src/styles/global.css` para:
  - navegación de páginas en header (`.nav-btn*`),
  - layout/cards/tablas del dashboard analytics.

## Convención entorno Node (NVM)

- En este proyecto, usar Node `v22.19.0` via `nvm`.
- Antes de correr comandos de frontend (`npm run dev`, `npm run build`, etc.):
  1. `export NVM_DIR="$HOME/.nvm"`
  2. `. "$NVM_DIR/nvm.sh"`
  3. `cd frontend && nvm use` (usa `.nvmrc`), o `nvm use 22.19.0`.
- `.nvmrc` creado en `frontend/.nvmrc` con `22.19.0`.

## Estado actualizado (2026-02-16, latencia/order book)

- Diagnóstico confirmado:
  - frontend ya soportaba `orderbook_update`, pero backend no lo emitía en el loop live,
  - el libro se veía lento por dependencia de snapshot completo + polling round-robin.
- Fix aplicado:
  - `backend/services/event_manager.py` ahora emite `orderbook_update` incremental por evento al refrescar libros.
- Mejora adicional aplicada:
  - stream realtime de order book via `PolymarketStreamer` conectado en `EventManager` (`on_book`),
  - mapeo `asset_id -> event_id/side` para actualizar `order_book_yes/no` en caliente,
  - fallback REST de order book se mantiene activo.
- Recomendación operativa:
  - para bot en vivo, mantener foco en baja latencia/predictibilidad (p95/p99),
  - medir y monitorear al menos:
    1. `tick_to_signal_ms`
    2. `signal_to_order_sent_ms`
    3. `order_sent_to_ack_ms`
    4. `book_age_ms`
    5. `slippage_bps`
- Próximo bloque técnico sugerido:
  - parametrizar `polymarket_events_per_tick`,
  - separar ritmo de actualización de order book,
  - evaluar integrar `PolymarketStreamer` (`on_book`) como canal realtime y REST como fallback.

## Estado actualizado (2026-02-17, pipeline subminuto 5m)

- Nuevo flujo paralelo (sin reemplazar el pipeline actual 1m/15m):
  - objetivo: research de eventos 5m con base `1s` y slots `10s`.
- Scripts nuevos:
  1. `resample_klines_to_excel_subminute.py`
     - soporta resample con segundos (`10s`, `30s`, etc.).
  2. `aggregate_pm_5m_slot_ranges.py`
     - agrega por `slot` dentro de bloque de 5m (ej. 30 slots para 10s).
     - salida: `slot, inf_range, sup_range, prob_up, prob_down, count_of_klines_inside_range`.
  3. `run_pm_pipeline_4cryptos_5m_10s.py`
     - pipeline end-to-end 4 cryptos: `1s -> Excel subminuto -> agregación 5m slots -> merge`.
- Salida consolidada nueva:
  - `backtest_output/merged_pm_5m_slot_ranges_4cryptos.csv`.

## Estado actualizado (2026-02-17, conexión bot 5m/10s)

- `EventManager` ya conecta automáticamente la tabla subminuto para eventos de 5m:
  - source preferido: `backtest_output/merged_pm_5m_slot_ranges_4cryptos.csv`,
  - fallback: modelo anterior `merged_pm_ranges_4cryptos.csv` si falta data subminuto.
- Nuevo campo runtime por evento:
  - `quant_source` (`pm_5m_slot_ranges` o `pm_15m_minute_ranges`).
- `quant_source` se envía en WS (`price_update`, `quant_metrics_update`) para diagnóstico en UI.
- Endpoints de estadísticas de oportunidades (`/api/stats/opportunities*`) se mantienen sin renombre para no romper clientes actuales.

## Estado actualizado (2026-02-17, hard-stop por ticker)

- Guardrail backend agregado para evitar trading en tickers apagados:
  - `EventManager.is_event_trading_enabled(...)` valida ticker contra `settings.monitored_tickers`.
  - Tracking/señales de bot no avanzan si el ticker no está monitoreado.
  - `POST /api/orders` retorna `403` si se intenta operar un evento con ticker deshabilitado.

## Estado actualizado (2026-02-17, Kelly con bankroll real)

- `KS` en `Bot Trade` ahora usa bankroll real de API cuando está disponible:
  - `Header` ya consulta `/api/balance` y publica el valor en store compartido (`useAccountStore`),
  - `EventCard` toma ese bankroll real para cálculo Kelly (`KS %` / `KS $`).
- Fallback:
  - si balance API no está disponible, Kelly usa `settings.kelly_bankroll` (manual).

## Estado actualizado (2026-02-17, guardrails de compra bot)

- Se agregó control configurable de frecuencia/exposición para evitar compras en ráfaga:
  - `bot_risk_enabled`,
  - `bot_max_buys_per_event_side`,
  - `bot_cooldown_seconds_per_event_side`,
  - `bot_global_min_seconds_between_orders`,
  - `bot_max_event_exposure_pct`,
  - `bot_max_ticker_exposure_pct`.
- Aplicación backend:
  - validación previa en `POST /api/orders` (demo y live),
  - rechazo con `403 Risk guard blocked: <reason>` si viola reglas,
  - registro de fills para mantener estado de límites/cooldowns.
- UI Settings:
  - nueva sección `Bot Risk Guardrails` en Sidebar para ajustar estos parámetros en vivo por WebSocket.
  - incluye límites de exchange configurables:
    - `pm_min_shares` (default `5`),
    - `pm_min_notional_usd` (default `1`).

## Estado actualizado (2026-02-19, cap fijo por orden bot)

- Nuevo parámetro persistente en settings: `bot_order_notional_cap_usd` (default `5.0`).
- En `POST /api/orders`, si una orden excede ese notional:
  - se recorta automáticamente `shares` para quedar en el cap,
  - se intenta ejecutar con el tamaño recortado (en vez de bloquear por tamaño de orden).
- `validate_order_risk_guards` ahora prioriza este cap fijo por orden cuando está activo (>0),
  retornando temprano tras validar el tope por orden.

## Estado actualizado (2026-02-20, paridad reglas front/back para Buy At)

- `POST /api/orders` ahora valida adicionalmente:
  - `timeframe_filter` activo en settings vs `timeframe_minutes` del evento,
  - `quant_buy_gate` por lado (`up/down`) antes de ejecutar orden.
- Frontend `Bot Trade` fue alineado para evitar reglas locales divergentes:
  - habilitación del botón basada en `quant_buy_gate.enabled` + mínimos de exchange,
  - cálculo de `shares` y `$` mostrado usando `bot_order_notional_cap_usd` efectivo (capped).
- Objetivo: backend como fuente de verdad para operar bot sin depender de validaciones de UI.

## Estado actualizado (2026-02-20, diagnostico 403 + log de bloqueos)

- `POST /api/orders` ahora devuelve `403` enriquecido para bloqueos de `quant gate`:
  - incluye `quant_prob`, `ask`, `market_prob`, `edge_pct`, `edge_vs_ask_pct`,
    `sample`, `percentile` al momento del check.
- Se agregó log persistente de bloqueos de orden:
  - archivo: `backtest_output/order_blocked_log.csv`,
  - filas con timestamp, evento/lado, reason, detail, shares/notional solicitado vs efectivo,
    cap aplicado y métricas de quant gate.

## Estado actualizado (2026-02-20, ask fallback + edge_pct fix)

- Cuando `order_book_yes/no` no está disponible (WS no conectado aún / round-robin no llegó),
  el gate usa `yes_price`/`no_price` (mid) como proxy del ask.
- Flag `ask_is_proxy: bool` incluido en cada lado del `quant_buy_gate`.
- Lógica de edge en el gate:
  - `edge_pct` = `quant_prob - market_mid` (informativo)
  - `edge_vs_ask_pct` = `quant_prob - ask` (accionable — lo que realmente pagás)
  - Check principal `min_edge_pct` usa `edge_vs_ask_pct` cuando hay ask real,
    fallback a `edge_pct` vs mid cuando `ask_is_proxy=True`.
  - Filtro secundario `edge_vs_ask_enabled` sigue funcionando con threshold propio.
- Frontend: QE muestra `edge_vs_ask_pct` cuando hay order book real,
  `edge_pct*` (con asterisco) cuando ask es proxy (no hay book).
- Si `edge_vs_ask_enabled=True` y `ask_is_proxy=True` → bloquea con `no_ask_price`.

## Estado actualizado (2026-02-20, strong-signal sample override)

- Nuevo parámetro `quant_gate_min_sample_strong_signal` (default `20`):
  - cuando `quant_prob >= quant_gate_strong_signal_threshold` (default `0.72`),
    el gate usa este sample mínimo reducido en lugar de `quant_gate_min_sample` (120).
  - permite operar bins extremos fuera del rango entrenado que tienen señal fuerte
    pero pocos casos históricos (ej. BTC con price_diff = -272, prob_down ≈ 82%).
- Lógica: bins centrales (señal débil) siguen exigiendo n=120; bins extremos (señal fuerte) solo exigen n=20.
- `reason` en gate muestra `sample<20` (el efectivo) en vez de `sample<120`.
- Ambos lookups (`_lookup_quant_probs` y `_lookup_quant_probs_5m_slot`) ahora clampean
  al bin extremo cuando `price_diff` está fuera del rango entrenado (en vez de retornar None).
- Expuesto en Sidebar: `Strong Signal Min Sample` y `Strong Signal Threshold (%)`.

## Estado actualizado (2026-02-20, multi-window quant gate)

- Quant gate ahora soporta perfiles por ventana temporal del evento:
  - `base` (reglas actuales),
  - `early` (primeros segundos del evento),
  - `late` (últimos segundos antes de cierre).
- Overrides nuevos en settings (persistentes):
  - Early: `early_window_enabled`, `early_window_seconds`,
    `early_quant_gate_min_sample`, `early_quant_gate_min_edge_pct`,
    `early_quant_gate_min_abs_diff_usd` (+ campos edge/prob avanzados).
  - Late: `late_window_enabled`, `late_window_seconds`,
    `late_quant_gate_min_sample`, `late_quant_gate_min_edge_pct`,
    `late_quant_gate_min_abs_diff_usd` (+ campos edge/prob avanzados).
- Nuevo motivo de bloqueo posible en gate:
  - `diff_abs<...` (diferencia absoluta `|current_price - price_to_beat|` por debajo del mínimo de ventana).

## Estado actualizado (2026-02-21, tipado y documentación de settings)

- Auditoria completa de settings: todos los campos que operan en runtime ahora tienen tipado en Pydantic y TypeScript.
- Campos nuevos agregados a `SettingsData` (backend `schemas.py`) y `SettingsData` (frontend `types/events.ts`):
  - `quant_gate_min_sample_strong_signal` (int, default 20) — ya existía en `__init__` pero faltaba en Pydantic/TS.
  - `quant_gate_strong_signal_threshold` (float, default 0.72) — ídem.
  - `order_book_max_levels` (int, default 8) — controla niveles de bids/asks emitidos por WS.
  - `order_book_min_broadcast_ms` (int, default 120) — throttle de emisión de orderbook_update por evento/lado.
  - `bot_enforce_timeframe_filter` (bool, default true) — ver sección siguiente.
- Store frontend (`useEventsStore.ts`) actualizado con defaults para todos los campos anteriores.

## Estado actualizado (2026-02-21, fuentes de configuración)

- El sistema tiene 3 fuentes de configuración con la siguiente jerarquía (mayor prioridad al final):
  1. Defaults hardcodeados en `EventManager.__init__` — base de todos los settings del bot.
  2. `config/events.yaml` — controla discovery, pricing, demo events, UI. NO sobreescribe `self.settings`.
  3. `config/runtime_settings.json` — **fuente de verdad operativa**. Se aplica al iniciar y se actualiza al guardar desde UI (REST o WS). Versionado en git.
- Convención: si hay discrepancia entre JSON y código, el JSON gana en runtime. Para cambiar defaults permanentes, editar `__init__` de `EventManager` y `SettingsData` en `schemas.py`.

## Estado actualizado (2026-02-21, fix bot timeframe + double-check guards)

### Bug fix: bot auto-order ejecutaba en eventos fuera del timeframe seleccionado
- `_bot_maybe_place_order` en `event_manager.py` ahora verifica `timeframe_filter` vs `timeframe_minutes` del evento antes de ejecutar.
- Si el timeframe no coincide, el bot hace `return` con log `INFO` (no error).
- El check es **configurable**: nuevo setting `bot_enforce_timeframe_filter` (bool, default `true`).
  - Expuesto en Sidebar: checkbox **"Enforce Timeframe Filter (Bot)"** en sección Bot Risk Guardrails.
  - Si está `false`, el bot opera en eventos de cualquier timeframe (comportamiento anterior).

### Double-check guards confirmados
- **UP + DOWN en mismo evento**: cubierto a doble capa.
  - Backend: `validate_order_risk_guards` bloquea con `already_bought_<side>_this_event` al detectar fill del lado opuesto en el día. Aplica tanto a órdenes manuales como al bot auto-order interno.
  - Frontend: `boughtSide` deshabilita el botón del lado contrario en `EventCard`.
- **Timeframe mismatch en órdenes manuales**: `POST /api/orders` ya tenía el check (línea ~197, `trading.py`). Ahora el bot interno también lo tiene.

## Estado actualizado (2026-02-17, Buy At ejecutable)

- En `Bot Trade`, botones `Buy At` ahora ejecutan orden real vía `POST /api/orders`:
  - `side=Buy`,
  - `order_type=market`,
  - `outcome` por botón (`up/down`).
- Tamaño (`shares`) se calcula desde `KS $ / precio_lado` en tiempo real.
- Precio mostrado en botón prioriza `best ask` de order book; fallback a probabilidad (`yes_price`/`no_price`).
- UI muestra feedback de envío (`success/error`) en el card.

## Estado actualizado (2026-02-17, tracker de oportunidades alineado a ejecución)

- El tracker de oportunidades (`opportunities_log.csv`) ya no registra solo por transición de gate:
  - ahora exige stake accionable por lado usando Kelly + probabilidad quant,
  - valida mínimos de exchange (`pm_min_shares`, `pm_min_notional_usd`),
  - aplica caps locales base (`bot_max_event_exposure_pct`, `bot_max_ticker_exposure_pct`).
- `stake_usd` registrado en oportunidades ahora usa stake Kelly calculado (si disponible), no fijo por defecto.
- Frontend `Buy At` agrega pre-validación local visible en tooltip para:
  - mínimos de exchange,
  - caps locales de bot por evento/ticker.
- Auditoría de bloqueos:
  - nuevo log `backtest_output/opportunity_blocked.csv` con `blocked_reason`,
  - endpoint nuevo `GET /api/stats/opportunities/blocked/raw`,
  - dashboard analytics agrega tabla `Blocked Opportunities (Not Registered)`.

## Estado actualizado (2026-02-18, trazabilidad PTB)

- Se agregó trazabilidad de fuente para `price_to_beat`:
  - campo runtime nuevo por evento: `price_to_beat_source` (`gamma`, `config`, `binance_klines`, `binance_open`, `unknown`).
  - prioridad de asignación en backend:
    1. `settings.price_to_beat` (`gamma` si viene de discovery, o `config` si estático),
    2. fallback `binance_klines`,
    3. fallback `binance_open`.
- UI live:
  - `EventCard` muestra badge de fuente junto a `Price To Beat`:
    - `G` (Gamma),
    - `C` (Config),
    - `B` (Binance),
    - `U` (Unknown).

## Estado actualizado (2026-02-18, analytics funnel)

- Analytics de oportunidades ahora incluye KPI de funnel:
  - `Detected`,
  - `Registered`,
  - `Blocked`,
  - `% Executable` (`registered / (registered + blocked)`).
- Nuevo endpoint backend:
  - `GET /api/stats/opportunities/signals/raw?limit=...&ticker=...`
  - fuente: `opportunities_log.csv` (señales registradas).
- `Recent Outcomes` agrega columna:
  - `Percentile @ Signal` (desde `percentile_at_signal`).

## Estado actualizado (2026-02-18, default timeframe)

- Default de timeframe en app actualizado a `5m` (antes `15m`):
  - backend settings default (`EventManager`, `SettingsData`),
  - frontend store default (`useEventsStore`),
  - fallbacks de UI (`App` y selector `Sidebar`).

## Estado actualizado (2026-02-19, persistencia runtime settings)

- `mode` y `settings` de runtime ahora persisten en disco para continuidad sin frontend:
  - archivo: `config/runtime_settings.json` (versionado en git).
- Backend carga ese estado al iniciar (`EventManager.start()`), antes de inicializar eventos/streams.
- Backend guarda estado al:
  - `switch_mode`,
  - `update_settings` via WebSocket.

## Estado actualizado (2026-02-19, quant gate edge vs ask)

- Nuevo filtro opcional en `Quant Buy Gate`:
  - `quant_gate_edge_vs_ask_enabled` (default `false`),
  - `quant_gate_min_edge_vs_ask_pct` (default `2.0`).
- Regla:
  - para cada lado (`up/down`), exige `quant_prob_side - best_ask_side >= min_edge_vs_ask_pct`.
  - si falta ask, bloquea con reason `no_ask_price` cuando el filtro está activo.
- UI Settings (Sidebar):
  - toggle `Enable Edge vs Ask Filter`,
  - input `Min Edge vs Ask (%)`.

## Estado actualizado (2026-02-19, toggles UI cards)

- Settings -> `Chart Options` agrega toggles nuevos:
  - `Show Order Book Card` (`hide_order_book_card`),
  - `Show Positions Card` (`hide_positions_card`).
- `EventCard` respeta ambos toggles para ocultar/mostrar:
  - panel `Order Flow`,
  - panel `Positions`.

## Estado actualizado (2026-02-21, logs y bitácora)

### Rotación de bot_orders.csv por fecha
- `_BOT_ORDERS_LOG_PATH` reemplazado por función `_bot_orders_log_path()` en `event_manager.py`.
- El archivo ahora rota automáticamente por día UTC: `backtest_output/bot_orders_YYYY-MM-DD.csv`.
- El rollover es automático al cruzar medianoche — no requiere reiniciar el bot.

### Campo percentile_at_signal en bot_orders
- `_BOT_ORDERS_FIELDNAMES` agrega `percentile_at_signal` (entre `bankroll_usd` y `status`).
- Se extrae de `event_dict["quant_range_histogram"]["current_percentile"]` al momento de ejecutar la orden.
- Aplica tanto a órdenes `placed` como `failed`.

### runtime_settings.json movido a config/
- Antes: `backtest_output/runtime_settings.json` (ignorado por git).
- Ahora: `config/runtime_settings.json` (versionado en git).
- `_runtime_settings_path` en `EventManager.__init__` actualizado.
- Docs `AGENTS.md` y `docs/BOT_AUTO_ORDER.md` actualizados.

## Estado actualizado (2026-02-25, trazabilidad de precio real en bot orders)

- `backtest_output/bot_orders_YYYY-MM-DD.csv` ahora agrega columnas:
  - `price_source_at_send` (`best_ask` o `proxy_mid`),
  - `fill_price_real` (si viene en response de exchange),
  - `edge_at_fill_pct` (`quant_prob - fill_price_real` en %).
- `edge_pct` existente se mantiene como referencia de envío (`quant_prob - ask_price_at_send`).
- Se agregó extracción robusta de fill price desde respuesta de orden (`fills[]`, `avg_price`, `filled_price`, etc.).
- Compatibilidad de logs:
  - si existe archivo diario con header viejo, el backend migra automáticamente al nuevo schema antes de append.

## Estado actualizado (2026-02-25, paper mode bot + bitácora de decisiones)

- Nuevo setting runtime: `bot_paper_mode` (default `false`).
  - Cuando `true` y `trading_mode=bot`, el bot NO envía orden real a exchange.
  - En su lugar registra decisión simulada y mantiene guardrails/gating del flujo real.
- Nuevo log:
  - `backtest_output/paper_trades.csv`
  - Campos principales:
    - `decision_time`, `slot`, `range`, `prob_up`, `marketProb_at_decision`,
      `QuantumEdge`, `side_taken`, `event_outcome_real`, `pnl_simulated`
    - + metadatos (`event_id`, `ticker`, `stake_usd`, `status`, etc.)
- Reconciliación automática:
  - al cierre del evento, backend completa `event_outcome_real` y `pnl_simulated`
    sobre filas `pending` en `paper_trades.csv`.
  - `close_price` usa `current_price` al cierre (con cache de fallback).
- Endpoint nuevo:
  - `GET /api/stats/paper/raw?limit=500&ticker=BTC` para leer filas de paper mode.

### Script de bitácora
- Nuevo script: `scripts/bitacora.py`.
- Genera `backtest_output/bitacora_trades.csv` cruzando:
  - `bot_orders_*.csv` — órdenes ejecutadas (placed/failed).
  - `opportunity_outcomes.csv` — resultados (won, pnl, close_price, ...).
  - `opportunities_log.csv` — todas las señales detectadas.
  - `opportunity_blocked.csv` — señales bloqueadas por quant gate.
  - `order_blocked_log.csv` — órdenes bloqueadas por risk guard.
- Imprime resumen: hit rate, PnL, funnel de señales, hit rate por percentil.
- Uso:
  ```bash
  python3 scripts/bitacora.py                    # todos los logs disponibles
  python3 scripts/bitacora.py --date 2026-02-21  # filtra por fecha UTC
  python3 scripts/bitacora.py --dir /ruta/logs   # directorio personalizado
  ```

## Estado actualizado (2026-02-25, split de bankroll live/paper)

- Se separó el bankroll manual en dos settings:
  - `kelly_live_bankroll_usd`: sizing manual en live (fallback cuando no hay balance API).
  - `kelly_paper_bankroll_usd`: sizing para `bot_paper_mode`.
- Compatibilidad:
  - `kelly_bankroll` se mantiene como campo legado y fallback.
  - Si `runtime_settings.json` viejo solo trae `kelly_bankroll`, backend migra ese valor en memoria a los dos nuevos campos.
- UI Sidebar:
  - `Kelly Settings` ahora muestra `Live Manual Bankroll ($)` y `Paper Bankroll ($)`.

## Estado actualizado (2026-02-25, script reset de logs para paper)

- Nuevo script: `scripts/reset_logs_for_paper.sh`
- Objetivo: arrancar una corrida paper con logs limpios sin tocar config ni CSV del pipeline.
- Hace backup previo en `backtest_output/archive_YYYY-MM-DD_HHMMSS/` y luego limpia:
  - `paper_trades.csv`
  - `opportunities_log.csv`
  - `opportunity_outcomes.csv`
  - `opportunity_blocked.csv`
  - `order_blocked_log.csv`
  - `bot_orders_YYYY-MM-DD.csv` (del día actual)
- Uso:
  ```bash
  bash scripts/reset_logs_for_paper.sh
  bash scripts/reset_logs_for_paper.sh --include-backend-log
  ```

## Estado actualizado (2026-02-25, bot orders en Analytics)

- Nuevo endpoint backend:
  - `GET /api/stats/bot-orders/raw?limit=5000&days=7&ticker=BTC`
  - Lee `backtest_output/bot_orders_YYYY-MM-DD.csv` en ventana multi-día.
- Dashboard analytics:
  - Nuevo panel `Bot Orders (Execution Log)` en `/analytics/opportunities`.
  - Muestra tabla con:
    - `placed_at_utc`, `ticker`, `side`, `price` (send), `fill_price_real`,
      `edge_pct`, `edge_at_fill_pct`, `notional_usd`, `status`, `event_id`.
  - KPIs rápidos:
    - `total rows`, `placed`, `failed`, `with fill price`,
      `avg edge@send`, `avg edge@fill`.

## Estado actualizado (2026-02-25, fix label event_outcome con exclude-last-slot)

- Script afectado: `aggregate_pm_5m_slot_ranges.py`.
- Bug corregido:
  - antes, al usar `--exclude-last-slot`, se removía slot 30 y luego `event_outcome`
    se calculaba con `final_close` del último slot restante (slot 29).
  - resultado: label desplazado a ~4:50 en vez de cierre real 5:00.
- Comportamiento nuevo:
  - se mantiene `df_all` (slots 1..max_slot) para calcular `ref_price_all` + `final_close_all`.
  - `--exclude-last-slot` ahora solo filtra el dataset operable/exportado.
  - `prob_up_event/prob_down_event` se calculan con cierre real del evento (`final_close_all`)
    alineado al índice de filas exportadas.
- Efecto esperado:
  - con `--exclude-last-slot`: salida de slots operables (1..29), pero label de outcome a cierre 5m real.
  - sin `--exclude-last-slot`: se exportan slots completos incluyendo slot 30.
- Guardrails agregados en el script:
  - falla si detecta bloques 5m incompletos/duplicados (`count != max_slot`),
  - falla si `--exclude-last-slot` está desactivado y falta el slot final del bloque.
