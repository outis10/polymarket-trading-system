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

## Criterios para actuar vs. esperar

| Condición | Acción recomendada |
|---|---|
| N < 20 en el bucket | Solo observar, no filtrar |
| N 20-50, PnL < -$15 | Monitorear en próximo ciclo |
| N > 50, win% < 45%, PnL < -$20 | Implementar filtro |
| Spread: cualquier bucket con PnL < -$30 | Actuar (señal clara, N suele ser suficiente) |

---

## Próxima revisión recomendada

**Fecha**: ~2026-03-21 (con ~2 semanas más de datos)

**Foco**:
1. Confirmar si horas 10h, 11h, 21h, 22h PST siguen siendo negativas con más N
2. Confirmar si slots 9 y 15 son consistentes o fueron ruido
3. Verificar si el filtro de spread está bloqueando oportunidades buenas (revisar `opportunity_blocked.csv`)
4. Calibration check: `quant_prob` vs `win_rate` real por bucket

---

## Notas metodológicas

- Todos los análisis son **in-sample** — los datos usados para evaluar son los mismos
  que el bot generó. Existe riesgo de overfitting en filtros muy específicos.
- Priorizar filtros que tienen **explicación causal** (spread alto = iliquidez real)
  sobre filtros que son solo correlaciones estadísticas (hora específica sin razón clara).
- El análisis de contrarian EV (`scripts/analyze_contrarian_ev.py`) es complementario:
  muestra qué tan recuperable es cada pérdida si el mercado opuesto hubiera ganado.
