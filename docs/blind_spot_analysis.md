# Blind Spot Analysis — Metodología y Guía de Uso

## ¿Qué es esto?

Análisis periódico para detectar **condiciones donde el modelo pierde consistentemente**,
permitiendo ajustar los filtros del gate antes de que las pérdidas se acumulen.

No es una decisión única: debe repetirse cada **2-4 semanas** o cuando se acumulen
~200 trades nuevos, para que los patrones sean estadísticamente robustos.

---

## Cómo ejecutar

```bash
# Análisis completo (todos los datos disponibles)
python3 scripts/analyze_blind_spots.py

# Solo últimos 14 días
python3 scripts/analyze_blind_spots.py --days 14

# Desde una fecha específica
python3 scripts/analyze_blind_spots.py --since 2026-03-01

# Guardar CSV con resultados
python3 scripts/analyze_blind_spots.py --save

# Con mínimo de trades por bucket más exigente (para menos ruido)
python3 scripts/analyze_blind_spots.py --min-n 15
```

---

## Dimensiones analizadas

| Dimensión | Por qué importa |
|---|---|
| `spread_pct_at_send` | Spread alto = mercado ilíquido, model assumptions no se cumplen |
| `hour_pst` | Ciertos horarios tienen dinámica distinta (apertura NY, cierre Asia) |
| `slot` | Posición en la ventana de 5 min: early/mid/late tienen contextos diferentes |
| `side` | Si el modelo está sesgado sistemáticamente a UP o DOWN |
| `diff_vs_ptb` | Qué tan lejos está BTC del precio de referencia al momento de la señal |
| `edge_pct` | Si el gate de edge tiene zonas donde el modelo se sobre-estima |
| `fill_price` | Si ciertos rangos de precio tienen peor calibración |

---

## Umbrales de alerta (flags)

- 🔴 **BLIND SPOT**: `win_rate < 50%` Y `PnL < -$5` en el bucket
- ✅ **STRONG**: `win_rate > 70%` Y `PnL > $10`

Estos umbrales son conservadores. Con N < 30 por bucket, un blind spot puede ser
ruido estadístico. Con N > 50 y PnL negativo consistente, actuar.

---

## Filtros disponibles en runtime_settings.json

### Spread (implementado 2026-03-07)
```json
"quant_gate_max_spread_pct": 0.03
```
- `0.0` = desactivado (default)
- `0.03` = bloquea cuando spread > 3% (recomendado según análisis inicial)
- El reason en `opportunity_blocked.csv` aparecerá como `spread>3.00%`

### Min Ask Price (implementado 2026-03-08)
```json
"quant_gate_min_ask_price": 0.40
```
- `0.0` = desactivado (default)
- `0.40` = bloquea cuando ask real del outcome < $0.40 por share (recomendado)
- Solo aplica cuando el ask es real (no proxy/mid)
- El reason en `opportunity_blocked.csv` aparecerá como `ask<0.40`
- **Base**: 67 trades con fill 0.10–0.40 → -$79 PnL (-13% EV en bucket 0.3–0.4, N=40)
- Confirmado cruzando `polymarket_activity_*.csv` con `opportunity_outcomes.csv`

---

## Historial de análisis

### 2026-03-07 — Análisis inicial (716 trades, 4 días)

**Resultados globales**: 61.1% win rate, +$219.80 PnL, 8.5% ROI

**Blind spots detectados**:

| Dimensión | Valor | n | Win% | PnL |
|---|---|---|---|---|
| spread | 3-5% | 125 | 45.6% | -$61 |
| spread | >10% | 18 | 16.7% | -$43 |
| hora_pst | 22h | 35 | 42.9% | -$8 |
| hora_pst | 21h | 31 | 45.2% | -$27 |
| hora_pst | 11h | 39 | 46.2% | -$28 |
| hora_pst | 10h | 39 | 48.7% | -$19 |
| slot | 9 | 50 | 48.0% | -$45 |
| slot | 15 | 21 | 42.9% | -$34 |

**Peores combos (hora × side)**:
- 22h PST UP: 27.8% win, -$33.6
- 21h PST DOWN: 35.3%, -$23.4
- 10h PST DOWN: 36.8%, -$19.2
- 11h PST UP: 40.0%, -$34.4

**Acción tomada**: Implementado filtro `quant_gate_max_spread_pct`.
Horas y slots quedan pendientes de confirmación con más datos (N insuficiente
para actuar con certeza — esperar análisis en 2026-03-21).

---

### 2026-03-08 — Análisis por fill price (938 trades cruzados con outcomes, desde Mar 4)

**Fuente**: `polymarket_activity_2026-03-08.csv` cruzado con `opportunity_outcomes.csv` + `bot_orders_all_2026-03-08.csv`

**Resultados globales (desde Mar 4)**: +$46.20 PnL, +0.99% ROI, $4,684 apostados

**Hallazgo principal — distribución por fill price**:

| Bucket fill | N | Win% | EV% | PnL total |
|---|---|---|---|---|
| 0.10–0.20 | 9 | 22.2% | +48.1% | -$13.68 |
| 0.20–0.30 | 18 | 22.2% | -11.1% | -$26.47 |
| 0.30–0.40 | 40 | 35.0% | ≈0% | -$38.83 |
| 0.40–0.50 | 31 | 45.2% | +0.4% | -$16.42 |
| 0.50–0.60 | 153 | 68.0% | +23.6% | +$189.91 |
| 0.60–0.70 | 101 | 69.3% | +6.6% | +$144.54 |
| 0.70–0.80 | 57 | 73.7% | -1.8% | +$90.72 |
| 0.80–0.90 | 17 | 94.1% | +10.7% | +$62.59 |

**Zona perdedora (fill < 0.40)**: 67 trades → -$79 PnL, edge promedio -6.4%
**Zona ganadora (fill ≥ 0.50)**: 328 trades → +$488 PnL, edge promedio +17.9%

**Acción tomada**: Implementado filtro `quant_gate_min_ask_price = 0.40`.

**Verificación adicional (double-check 2026-03-08)**: Se confirmó que el gate NO tiene bug.
Todos los placed orders tenían `edge_vs_ask > 0` (+3.9% a +20.2%, avg +9.3%).
El `edge_pct_at_signal` en `opportunity_outcomes` es vs mid-market (informativo), no vs ask (decisión).
El problema real es **calibración del modelo**, no lógica del gate.

| Bucket | N | Win% | AvgEdgeAsk | PnL | Veredicto |
|---|---|---|---|---|---|
| 0.1–0.2 | 14 | 28.6% | +9.4% | -$16.69 | monitorear |
| 0.2–0.3 | 23 | 13.0% | +8.7% | -$49.00 | FILTRAR |
| 0.3–0.4 | 49 | 38.8% | +8.5% | -$35.54 | FILTRAR |
| 0.4–0.5 | 39 | 51.3% | +10.9% | -$7.64 | monitorear |
| 0.5–0.9 | 358 | 70%+ | +10.0% | +$510 | OK |

El gate pasa trades con edge similar (+8-11%) en todos los buckets, pero los buckets
bajos ganan con mucha menos frecuencia de lo que el modelo predice → quant_prob
sobreestima la probabilidad real para outcomes de precio bajo.

---

### Causa raíz: descalibración del modelo en zona de precio bajo

El modelo de quant está entrenado principalmente con datos donde BTC tiene movimientos
moderados (outcomes de precio 0.5–0.7). En la zona 0.1–0.4, los outcomes representan
movimientos extremos o poco probables donde la calibración histórica es escasa.

**Síntoma**: el gate detecta edge real (+8-10% vs ask) pero la win rate real (13-38%)
no soporta ese edge — el modelo sobreestima `quant_prob` en esa zona.

---

### Posibles acciones para recalibrar el modelo

#### Opción A — Filtro temporal (implementado) ✅
```json
"quant_gate_min_ask_price": 0.40
```
Bloquea trades mientras el modelo no está calibrado en esa zona.
Ventaja: inmediato, cero riesgo. Desventaja: sacrifica oportunidades potencialmente buenas.

#### Opción B — Recalibración del quant_prob por bucket de precio
En el pipeline quant (`scripts/update_quant.sh`), agregar un factor de calibración
por rango de precio histórico. Si el modelo dice 25% pero históricamente gana 13%
en ese rango → escalar `quant_prob` por un factor de corrección `0.13/0.25 = 0.52`.
Requiere: +100 trades por bucket para estimación estable.

#### Opción C — Aumentar `quant_gate_min_edge_pct` para precios bajos
Exigir más edge en la zona problemática. Si el ask es < 0.40, requerir edge ≥ 20%
en lugar del default (4-7%). Esto reduce el número de trades bloqueados vs Opción A
pero sigue siendo más conservador.
```json
"quant_gate_min_edge_pct": 7.0   (global, ajustar con cuidado)
```

#### Opción D — Análisis de calibración por bin/slot + precio
El pipeline quant ya segmenta por `range` (bin de movimiento BTC) y `slot` (posición
en ventana). Verificar si los bins que corresponden a movimientos extremos ([-40,-30),
[30,40)) tienen peor calibración que los bins centrales ([-10,0), [0,10)).
Si es así, el filtro por precio es un proxy del filtro por bin extremo.

**Recomendación**: mantener Opción A activa y evaluar Opción B en la revisión de
2026-03-22 cuando haya más datos en la zona bloqueada para comparar.

---

## Criterios para actuar vs. esperar

| Condición | Acción recomendada |
|---|---|
| N < 20 en el bucket | Solo observar, no filtrar |
| N 20-50, PnL < -$15 | Monitorear en próximo ciclo |
| N > 50, win% < 45%, PnL < -$20 | Implementar filtro |
| Spread: cualquier bucket con PnL < -$30 | Actuar (señal clara, N suele ser suficiente) |

---

## Próxima revisión recomendada

**Fecha**: ~2026-03-22 (con ~2 semanas más de datos)

**Foco**:
1. Confirmar si horas 10h, 11h, 21h, 22h PST siguen siendo negativas con más N
2. Confirmar si slots 9 y 15 son consistentes o fueron ruido
3. Verificar si `quant_gate_max_spread_pct` está bloqueando oportunidades buenas (revisar `opportunity_blocked.csv`, reason `spread>3.00%`)
4. Verificar si `quant_gate_min_ask_price` reduce losses sin bloquear demasiado (revisar `opportunity_blocked.csv`, reason `ask<0.40`)
5. Re-correr `analyze_polymarket_activity.py` para ver evolución de PnL por bucket de precio
6. Calibration check: `quant_prob` vs `win_rate` real por bucket de precio

---

## Notas metodológicas

- Todos los análisis son **in-sample** — los datos usados para evaluar son los mismos
  que el bot generó. Existe riesgo de overfitting en filtros muy específicos.
- Priorizar filtros que tienen **explicación causal** (spread alto = iliquidez real)
  sobre filtros que son solo correlaciones estadísticas (hora específica sin razón clara).
- El análisis de contrarian EV (`scripts/analyze_contrarian_ev.py`) es complementario:
  muestra qué tan recuperable es cada pérdida si el mercado opuesto hubiera ganado.
