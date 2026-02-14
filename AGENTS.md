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
