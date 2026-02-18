# Kelly En El Bot (Resumen Operativo)

## Estado actual

- `KS % ($)` se calcula en frontend y se muestra como recomendación visual.
- No existe aún ejecución backend que tome ese `KS` como tamaño real de orden.
- La ejecución del botón en `Bot Trade` depende del `Quant Buy Gate` (enabled/disabled + razones).

## Fórmula actual (UI)

Para cada lado (`UP`, `DOWN`):

1. `edge = modelProb - marketProb`
2. `edgePct = edge * 100`
3. Si `kelly_enabled = false` o `edgePct < kelly_min_edge_pct` => `KS = 0`
4. `raw = max(0, edge / max(0.0001, 1 - marketProb))`
5. `adjusted = raw * kelly_fraction`
6. `capped = min(adjusted, kelly_max_bet_pct, kelly_max_event_exposure_pct)`
7. `KS % = capped * 100`, `KS $ = capped * kelly_bankroll`

En fórmula:

$$
\text{edge}=p_m-p_x,\quad
\text{raw}=\max\left(0,\frac{\text{edge}}{\max(10^{-4},1-p_x)}\right)
$$

$$
\text{capped}=\min\left(\text{raw}\cdot f,\ b_{\max},\ e_{\max}\right),\quad
KS_{\%}=100\cdot\text{capped},\quad
KS_{\$}=B\cdot\text{capped}
$$

ASCII:

```text
edge = p_model - p_market
capped = min(max(0, edge / max(0.0001, 1 - p_market)) * kelly_fraction, max_bet_pct, max_event_exposure_pct)
KS% = 100 * capped
KS$ = bankroll * capped
```

## Fuentes de datos (qué usa cada término)

- `marketProb`:
  - `UP`: `yes_price`
  - `DOWN`: `no_price`
- `modelProb`:
  - preferido: `quant_prob_up/down`
  - fallback: modelo local derivado de `current_price` vs `price_to_beat`
- Settings:
  - `kelly_enabled`, `kelly_fraction`, `kelly_bankroll`,
  - `kelly_min_edge_pct`, `kelly_max_bet_pct`, `kelly_max_event_exposure_pct`

## Source quant actual en backend

- Eventos `5m`: usa primero `merged_pm_5m_slot_ranges_4cryptos.csv`
- Fallback: `merged_pm_ranges_4cryptos.csv`
- Campo diagnóstico: `quant_source` (`pm_5m_slot_ranges` / `pm_15m_minute_ranges`)

## Qué significa en operación

1. `KS` hoy es sugerencia de sizing, no tamaño ejecutado real.
2. Para “Kelly real” en ejecución:
  - mover cálculo al backend de órdenes,
  - usar bankroll real (API o ledger),
  - registrar fill size y slippage.

## Checklist rápido antes de usar KS como señal fuerte

1. Verificar `quant_source` esperado para el evento.
2. Confirmar `quant_buy_gate.enabled = true`.
3. Revisar latencia (`book_age_ms`) y spread.
4. Confirmar régimen (`weekday/weekend`) en dashboard.
