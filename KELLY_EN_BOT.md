# Kelly En El Bot (Estado Actual)

## 1) Alcance real hoy

En el estado actual del proyecto, el cálculo de Kelly (`KS % ($)`) se usa para **mostrar recomendación de stake en UI**.

- Se calcula en frontend: `frontend/src/components/EventCard.tsx`.
- No hay ejecución backend que use ese tamaño de Kelly para enviar órdenes automáticamente.
- Lo que sí afecta la habilitación de compra es el `Quant Buy Gate` (`event.quant_buy_gate`).

## 2) Fórmula usada actualmente

Para cada lado (`up` / `down`) en `EventCard`:

1. `edge = modelProb - marketProb`
2. `edgePct = edge * 100`
3. Si `kelly_enabled = false` o `edgePct < kelly_min_edge_pct`, entonces `KS = 0`
4. `denom = max(0.0001, 1 - marketProb)`
5. `raw = max(0, edge / denom)`
6. `adjusted = raw * kelly_fraction`
7. `capped = min(adjusted, kelly_max_bet_pct, kelly_max_event_exposure_pct)`
8. Resultado:
   - `KS % = capped * 100`
   - `KS $ = capped * kelly_bankroll`

Versión matemática:

$$
\text{edge} = p_{\text{model}} - p_{\text{market}}
$$

$$
\text{raw} = \max\left(0, \frac{\text{edge}}{\max(10^{-4}, 1-p_{\text{market}})}\right)
$$

$$
\text{adjusted} = \text{raw}\cdot f,\quad f=\text{kelly\_fraction}
$$

$$
\text{capped} = \min\left(\text{adjusted},\, b_{\max},\, e_{\max}\right)
$$

$$
KS_{\%}=100\cdot \text{capped},\qquad
KS_{\$}=\text{bankroll}\cdot \text{capped}
$$

Fallback ASCII:

```text
edge = p_model - p_market
raw = max(0, edge / max(0.0001, 1 - p_market))
adjusted = raw * kelly_fraction
capped = min(adjusted, max_bet_pct, max_event_exposure_pct)
KS% = 100 * capped
KS$ = bankroll * capped
```

Notas:
- `kelly_max_bet_pct` y `kelly_max_event_exposure_pct` llegan como `%` en settings y se convierten a fracción (`/100`).
- El cálculo es deliberadamente conservador por `max(0, ...)` (no sugiere stake negativo).

## 3) De dónde sale cada dato

## 3.1 Settings de Kelly

Fuente: `Sidebar` -> WebSocket `update_settings` -> backend settings -> snapshot/WS -> frontend store.

Campos:
- `kelly_enabled`
- `kelly_fraction`
- `kelly_bankroll`
- `kelly_min_edge_pct`
- `kelly_max_bet_pct`
- `kelly_max_event_exposure_pct`

Archivos:
- `frontend/src/components/layout/Sidebar.tsx`
- `backend/ws/handlers.py`
- `backend/services/event_manager.py`
- `frontend/src/stores/useEventsStore.ts`

## 3.2 `marketProb` (probabilidad de mercado)

Para `UP`: `marketProb = event.yes_price`  
Para `DOWN`: `marketProb = event.no_price`

`yes_price/no_price` se forman en backend desde:

1. Precio de referencia (`current_price`) vs `price_to_beat` (swing model), y/o
2. Mid-price derivado de orderbook real (`fetch_real_prices`) cuando está disponible.

Archivo principal:
- `backend/services/event_manager.py`
- `backend/services/polymarket.py`

## 3.3 `modelProb` (probabilidad del modelo)

Selección en frontend:

- Si hay quant data:
  - `kellyModelUp = event.quant_prob_up`
  - `kellyModelDown = event.quant_prob_down`
- Si no hay quant data:
  - fallback local:
    - `directionalBias = tanh((current_price - price_to_beat) / max(1, price_to_beat*0.01))`
    - `pUpModel = clamp(yes_price + 0.1 * directionalBias, 0.01, 0.99)`
    - `pDownModel = 1 - pUpModel`

Archivo:
- `frontend/src/components/EventCard.tsx`

## 3.4 De dónde salen `quant_prob_up/down`

Backend (`EventManager`) calcula `quant_prob_up/down` en `_apply_quant_metrics`.

Fuente preferida:
- Para eventos `5m`: tabla `backtest_output/merged_pm_5m_slot_ranges_4cryptos.csv`  
  (`quant_source = pm_5m_slot_ranges`)

Fallback:
- Tabla histórica `backtest_output/merged_pm_ranges_4cryptos.csv`  
  (`quant_source = pm_15m_minute_ranges`)

Archivo:
- `backend/services/event_manager.py`

## 4) Relación con ejecución del bot

En tarjetas `Bot Trade`:

- Botón `Buy At XXc` se habilita/deshabilita por `quant_buy_gate`.
- El valor `KS % ($)` mostrado es guía visual de sizing, no orden automática con ese monto.

Archivo:
- `frontend/src/components/EventCard.tsx`

## 5) Fuentes de datos (resumen)

1. Binance/Chainlink:
- Alimenta `current_price` de referencia del evento.

2. Polymarket orderbook:
- Alimenta `yes_price/no_price` y libros cuando hay fetch de mercado.

3. CSV quant offline:
- `merged_pm_5m_slot_ranges_4cryptos.csv` (5m/10s)
- `merged_pm_ranges_4cryptos.csv` (modelo previo)

4. Settings de usuario:
- Sidebar -> WS -> backend settings -> frontend store.

## 6) Importante para interpretación

1. `kelly_bankroll` usado por `KS` hoy es el valor de settings, no balance API en tiempo real.
2. `KS` no representa todavía “tamaño ejecutado”.
3. Si quieres Kelly operativo real, hay que llevar este cálculo al backend de ejecución y usar bankroll/fills reales.
