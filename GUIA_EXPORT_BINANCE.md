# Guía Rápida: Exportar Velas de Binance a CSV

Este proyecto incluye el script `export_binance_klines.py` para descargar velas históricas de Binance.

## Requisitos

1. Entorno virtual activo:
```bash
source venv/bin/activate
```

2. Dependencia:
```bash
pip install requests
```

## Uso básico

Exportar `BTCUSDT` en velas de `1m` para los últimos 3 meses:

```bash
python export_binance_klines.py \
  --symbol BTCUSDT \
  --interval 1m \
  --months 3 \
  --output btcusdt_1m_3m.csv
```

## Parámetros principales

- `--symbol`: par de trading (ejemplo: `BTCUSDT`, `ETHUSDT`)
- `--interval`: intervalo de vela (`1m`, `5m`, `15m`, `1h`, etc.)
- `--months`: meses hacia atrás desde ahora (UTC)
- `--start`: fecha inicio `YYYY-MM-DD`
- `--end`: fecha fin `YYYY-MM-DD`
- `--output`: archivo CSV de salida
- `--sleep-ms`: pausa entre requests (default `150`)

Nota: usa `--months` o `--start`/`--end`.

## Ejemplos

Rango por fechas:

```bash
python export_binance_klines.py \
  --symbol BTCUSDT \
  --interval 1m \
  --start 2025-11-01 \
  --end 2026-02-01 \
  --output btc_1m_nov_to_feb.csv
```

ETH a 5 minutos, últimos 6 meses:

```bash
python export_binance_klines.py \
  --symbol ETHUSDT \
  --interval 5m \
  --months 6 \
  --output ethusdt_5m_6m.csv
```

## Formato del CSV

Columnas:
- `open_time` (ms UNIX)
- `open_time_utc`
- `open`, `high`, `low`, `close`
- `volume`
- `close_time`
- `quote_asset_volume`
- `number_of_trades`
- `taker_buy_base_volume`
- `taker_buy_quote_volume`

## Agrupar velas y exportar a Excel (multi-timeframe)

Si ya tienes el CSV de 1 minuto, puedes crear un `.xlsx` con hojas por intervalo:

```bash
python resample_klines_to_excel.py \
  --input btcusdt_1m_3m.csv \
  --output btcusdt_multiframe.xlsx \
  --intervals 2m,3m,5m,15m
```

Esto genera un Excel con hojas:
- `2min`
- `3min`
- `5min`
- `15min`
