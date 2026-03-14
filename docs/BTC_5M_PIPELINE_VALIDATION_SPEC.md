# BTC 5m Pipeline Validation Spec

Fecha: 2026-03-13

---

## Objetivo

Dejar definida una version metodologicamente solida del pipeline BTC para eventos de `5m`, lista para implementar o validar en otra sesion.

La idea central es:

- mantener el mercado objetivo como evento binario de `5 minutos`,
- usar slots de `10 segundos`,
- y alinear exactamente entrenamiento e inferencia.

---

## Definicion del mercado

Mercado modelado:

- evento `BTC 5m Up/Down`
- referencia `price_to_beat = precio al inicio del evento` (open del primer slot del bloque)
- resolucion final:
  - `UP` si `final_close > ref_price`
  - `DOWN` si `final_close < ref_price`
  - empate: **opcion A seleccionada** — tratar como `0.5 / 0.5` y mantener en el dataset
    - Razon: excluir empates elimina informacion de regimenes planos que existen en live
    - Frecuencia empate exacto en BTC 5m: < 0.1% de eventos

---

## Definicion de la unidad de prediccion

La unidad de prediccion es:

- `slot` dentro del evento de `5m`
- con `slot_seconds = 10`
- por tanto `30 slots` por evento

Cada fila del dataset responde a esta pregunta:

> Dado el movimiento acumulado de BTC desde el inicio del evento hasta el cierre del slot `k`, cual es la probabilidad de que el evento termine UP al cierre del minuto 5.

---

## Principio metodologico clave

Alinear entrenamiento e inferencia. **Regla: `slot-close only`.**

- Entrenar con el estado del mercado al cierre de cada slot.
- Inferir en live solo al cierre de cada slot.
- No operar intra-slot si el entrenamiento fue construido con cierres de slot.

Ejemplo:

- slot 1 = segundo 10
- slot 2 = segundo 20
- ...
- slot 30 = segundo 300

---

## Definicion exacta de day_type y time_frame

Definidos en `config/time_windows.csv`. Zona horaria: `America/Los_Angeles`.

| day_type | time_frame | Horas locales | Descripcion |
|---|---|---|---|
| workday | tf1 | 0:00 – 5:00 | Madrugada / sesion Asia |
| workday | tf2 | 5:00 – 13:00 | Manana / apertura US pre-market y manana |
| workday | tf3 | 13:00 – 16:00 | Tarde US / cierre NY |
| workday | tf4 | 16:00 – 24:00 | Noche US |
| weekend | tf1 | 0:00 – 5:00 | Madrugada fin de semana |
| weekend | tf2 | 5:00 – 13:00 | Manana fin de semana |
| weekend | tf3 | 13:00 – 16:00 | Tarde fin de semana |
| weekend | tf4 | 16:00 – 24:00 | Noche fin de semana |

`workday` = lunes a viernes. `weekend` = sabado y domingo.

---

## Definicion exacta de bins de price_diff

**BTC 5m: bins fijos de $10.**

- `price_diff = close_del_slot - ref_price`
- `inf_range = floor(price_diff / 10) * 10`
- Ejemplo: price_diff = $23.5 → bin `[20, 30)`

**Justificacion de bins fijos vs adaptativos:**

- BTC en un dia normal se mueve $50-$200 en 5m; en dias extremos $500-$2000.
- Con bins adaptativos (percentiles), el bin cambia de ventana a ventana, rompiendo la alineacion train/inference.
- Con bins fijos, el lookup en live es identico al entrenamiento: `floor(price_diff / step) * step`.
- La cola de bins extremos tendra pocas muestras — el `min_count` las filtra.

**Pasos configurados por asset y duracion** (en `run_pm_pipeline.py`):

| Asset | 5m | 15m | 60m | 240m |
|---|---|---|---|---|
| BTC | $10 | $30 | $100 | $400 |
| ETH | $0.20 | $0.60 | $2.00 | $8.00 |
| SOL | $0.20 | $0.60 | $2.00 | $8.00 |
| XRP | $0.02 | $0.06 | $0.20 | $0.80 |

---

## Pipeline propuesto

### 1. Input base

Exportar BTC a `1s` con ventana de `60 dias`:

```bash
python3 export_binance_klines.py --symbol BTCUSDT --interval 1s --days 60
# Output: backtest_output/btc_1s_60d.csv
```

### 2. Resample a 10s

```bash
python3 resample_klines_to_excel_subminute.py --ticker BTC --event-minutes 5
# Output: backtest_output/btc_subminute_5m.csv
```

### 3. Construccion del dataset por bloque de 5m

Para cada bloque de `5m`:

- `ref_price = open del primer slot del bloque`
- `slot_close_price = close del slot k`
- `price_diff = slot_close_price - ref_price`
- `inf_range = floor(price_diff / 10) * 10`
- `day_type, time_frame = clasificar(block_ts)`

Columnas del dataset:

- `block_ts`, `slot`, `open_time_utc`
- `open`, `close`, `ref_price`
- `price_diff`, `inf_range`, `sup_range`
- `day_type`, `time_frame`

### 4. Label del evento

Para cada fila del slot:

- `event_outcome = 1.0` si `final_close > ref_price`
- `event_outcome = 0.0` si `final_close < ref_price`
- `event_outcome = 0.5` si empate (opcion A)

### 5. Agregacion

Agrupar por: `day_type, time_frame, slot, inf_range, sup_range`

Calcular:

- `prob_up = mean(event_outcome)`
- `prob_down = 1 - prob_up`
- `count_of_klines_inside_range = count(*)`

### 6. Filtro minimo de muestra

Aplicar `min_count = 20` en produccion.

Justificacion:

- `min_count = 5` es suficiente para OOS validation (ventanas de 14d son chicas).
- `min_count = 20` para el artefacto de produccion (60d de datos).
- Bins extremos con count < 20 se excluyen — el sistema cae a `prob_up = None` y el bot no apuesta.

### 7. Uso en runtime

En live, `event_manager.py` hace:

1. Calcular `slot = floor(elapsed_seconds / slot_seconds) + 1`
2. Esperar al cierre del slot.
3. Calcular `price_diff = current_price - price_to_beat`.
4. Clasificar `(day_type, time_frame)` del evento.
5. Lookup binario: `bisect.bisect_right(inf_ranges, price_diff)`.
6. Retornar `(prob_up, prob_down, count)`.

**Artefacto usado en produccion:**
`backtest_output/merged_pm_slot_ranges_4cryptos.csv`

Columnas: `event_type, ticker, day_type, time_frame, slot, inf_range, sup_range, prob_up, prob_down, count_of_klines_inside_range`

Recarga en caliente sin reiniciar: `POST /api/quant/reload`

---

## Validacion OOS walk-forward — Resultados

**Script:** `scripts/validate_oos_btc_5m.py`

**Configuracion:** train=14d, test=1d, rolling diario, min_count=5, range_step=$10

**Dataset:** `btc_subminute_5m.csv` — 515,691 filas (60 dias)

**Resultados (46 folds, 340,366 predicciones):**

| Metrica | Valor | Referencia (random) | Delta |
|---|---|---|---|
| Brier score | **0.18462** | 0.25000 | **-0.065** (mejor) |
| Log-loss | **0.64713** | 0.69315 | **-0.046** (mejor) |
| Accuracy (>50%) | **71.4%** | 50% | +21.4 pp |
| Cobertura de bins | 86.2% | — | 13.8% sin match |

**Calibracion por decil:**

| Pred medio | Actual medio | Error | N |
|---|---|---|---|
| 0.011 | 0.063 | -0.051 ⚠ | 33,980 |
| 0.145 | 0.199 | -0.054 ⚠ | 34,377 |
| 0.274 | 0.305 | -0.031 | 31,394 |
| 0.377 | 0.382 | -0.006 | 36,401 |
| 0.458 | 0.459 | -0.001 ✓ | 30,361 |
| 0.536 | 0.530 | +0.007 ✓ | 37,806 |
| 0.626 | 0.615 | +0.011 ✓ | 34,152 |
| 0.728 | 0.687 | +0.041 | 33,825 |
| 0.856 | 0.796 | +0.060 ⚠ | 34,170 |
| 0.989 | 0.932 | +0.057 ⚠ | 33,900 |

**Observacion de calibracion:** el modelo es demasiado extremo en las colas (predice 0.01 cuando el real es 0.06, y predice 0.99 cuando el real es 0.93). El rango medio [0.35-0.65] esta bien calibrado.

**Correccion recomendada:** aplicar Bayesian smoothing (Beta prior) para suavizar las colas.

**Rendimiento por time_frame:**

| time_frame | N | Brier | Accuracy |
|---|---|---|---|
| tf1 (madrugada) | 70,797 | 0.1809 | 72.2% |
| tf2 (manana US) | 114,460 | 0.1836 | 71.5% |
| tf3 (tarde NY) | 36,539 | **0.2083** | **67.4%** ⚠ |
| tf4 (noche US) | 118,570 | 0.1805 | 72.1% |

**Observacion:** `tf3` (13-16h LA = cierre de NY) es la ventana mas ruidosa. Considerar aumentar `min_count` o desactivar el bot en ese horario.

**Rendimiento por slot (peores 5):**

| Slot | N | Brier | Accuracy |
|---|---|---|---|
| slot 1 | 12,445 | 0.2494 | 54.7% ⚠ |
| slot 2 | 12,257 | 0.2492 | 55.8% ⚠ |
| slot 3 | 12,120 | 0.2455 | 57.2% ⚠ |
| slot 4 | 12,005 | 0.2431 | 58.3% |
| slot 5 | 11,896 | 0.2390 | 60.0% |

**Observacion:** los slots 1-5 (primeros 50 segundos del evento) son casi aleatorios. El modelo gana precision a medida que avanza el evento. Considerar `bot_quant_gate_min_slot = 6` o similar para bloquear apuestas en slots iniciales.

---

## Lo que si es valido en esta especificacion

- `5m event`
- `30 slots de 10s`
- `price_diff vs ref_price`
- label final del evento
- segmentacion por `day_type + time_frame` (definidos exactamente arriba)
- lookup por bins fijos de `$10` para BTC
- empates como `0.5` (opcion A)

## Lo que no debe mezclarse

- artefactos de `7d` con artefactos de `60d`
- pipelines `5m/10s` con pipelines de otro horizonte
- decisiones intra-slot si el dataset fue entrenado con cierre de slot
- tablas viejas y nuevas con nombres ambiguos
- inferencia en tf3 sin aumentar `min_count`

---

## Validaciones obligatorias

### 1. Validacion de target

Confirmar que el label del dataset replica exactamente la logica de resolucion del evento `5m`.

### 2. Validacion temporal

Confirmar que entrenamiento e inferencia usan el mismo punto temporal: cierre del slot.

### 3. No leakage

Confirmar que ninguna feature usa informacion posterior al cierre del slot evaluado.

### 4. Cobertura de slots

Cada bloque valido debe tener `30` slots, sin huecos, sin duplicados. El bloque parcial final debe excluirse.

### 5. Calidad de muestra

Revisar bins con count bajo, bins extremos, estabilidad de `prob_up`. Usar `min_count=20` en produccion.

### 6. Validacion OOS

Usar `scripts/validate_oos_btc_5m.py`:

```bash
# Configuracion estandar
python3 scripts/validate_oos_btc_5m.py

# Con ventana de entrenamiento mas larga
python3 scripts/validate_oos_btc_5m.py --train-days 21 --min-count 10

# Excluyendo slots iniciales ruidosos
python3 scripts/validate_oos_btc_5m.py --skip-slots 1 2 3 4 5
```

Criterio de exito minimo en OOS:

| Metrica | Umbral |
|---|---|
| Brier score | < 0.22 |
| Accuracy >50% | > 62% |
| Calibracion cola | error < 0.08 en deciles extremos |

---

## Acciones recomendadas (pendientes)

1. **Bayesian smoothing en colas** — aplicar Beta prior para corregir sobreconfianza en deciles extremos (pred=0.01, pred=0.99).
2. **Aumentar min_count en tf3** — o desactivar el bot entre 13:00-16:00 LA (cierre NY).
3. **Considerar min_slot = 6** — los primeros 5 slots son casi aleatorios (Brier ≈ 0.25).
4. **Re-run OOS con --skip-slots 1 2 3 4 5** — para confirmar mejora de Brier > 0.18.

---

## Convencion de nombres de artefactos

| Artefacto | Descripcion |
|---|---|
| `btc_1s_60d.csv` | Klines 1s, 60 dias |
| `btc_subminute_5m.csv` | Klines 10s alineados a bloques 5m |
| `btc_pm_5m_slot_ranges.csv` | Tabla de probabilidad sin filtro de count |
| `btc_pm_5m_slot_ranges_mincount_20.csv` | Tabla filtrada, lista para produccion |
| `merged_pm_slot_ranges_4cryptos.csv` | Tabla unificada (4 assets, todos los event_types) |
| `oos_predictions_btc_5m.csv` | Predicciones OOS por fila |
| `oos_report_btc_5m.json` | Metricas OOS agregadas |

---

## Conclusion

La implementacion defendible es:

- evento objetivo: `BTC 5m`
- observacion: `slot close`
- granularidad: `10s`, `30 slots`
- feature principal: `price_diff vs price_to_beat`
- bins: `$10 fijos`
- segmentacion: `day_type + time_frame` (8 combinaciones)
- empates: `0.5` (opcion A)
- target: resultado final del bloque `5m`
- inferencia live: solo al cierre de cada slot

**Resultado OOS confirmado:** Brier=0.185, Accuracy=71.4% sobre 340k predicciones en 46 dias.
El modelo es significativamente mejor que random, con calibracion a mejorar en colas extremas y slots 1-5.

Si despues quieren operar dentro del slot, eso ya requiere un pipeline nuevo, no solo ajustar el runtime.
