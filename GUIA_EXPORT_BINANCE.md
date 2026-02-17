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

python3 export_binance_klines.py \
  --four-cryptos \
  --interval 1s \
  --start 2026-02-09 \
  --end 2026-02-14 \
  --output-dir backtest_output

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
  --input ./data/btcusdt_1m_3m.csv \
  --output btcusdt_multiframe.xlsx \
  --intervals 2m,3m,5m,15m
  
  
python3 resample_klines_to_excel.py \
  --input ./data/btcusdt_1m_3m.csv \
  --output btcusdt_multiframe.xlsx \
  --intervals 2m,3m,4m,5m,6m,7m,8m,9m,10m,11m,12m,13m,14m,15m,16m,17m,18m,19m,20m,21m,22m,23m,24m,25m,26m,27m,28m,29m,30m,31m,32m,33m,34m,35m,36m,37m,38m,39m,40m,41m,42m,43m,44m,45m,46m,47m,48m,49m,50m,51m,52m,53m,54m,55m,56m,57m,58m,59m,60m
  
```

Esto genera un Excel con hojas:
- `2min`
- `3min`
- `5min`
- `15min`

## Pipeline completo para 4 criptos (extract -> frames -> aggregate -> merge)

Script: `run_pm_pipeline_4cryptos.py`

Este pipeline corre para `BTCUSDT, ETHUSDT, SOLUSDT, XRPUSDT` y guarda todo en `backtest_output/` con prefijo por ticker:

1. Exporta velas 1m de Binance.
2. Genera Excel multiframe con hoja `1min`.
3. Ejecuta `aggregate_pm_15m_ranges.py`.
4. Genera merge final con columna `ticker`.

### Comando rápido

```bash
source venv/bin/activate
python run_pm_pipeline_4cryptos.py --months 3 --output-dir backtest_output
```

### Parámetros útiles

- `--symbols`: lista separada por coma (default: `BTCUSDT,ETHUSDT,SOLUSDT,XRPUSDT`)
- `--months`: meses de histórico para export Binance (default: `3`)
- `--range-step`: paso de rango para aggregate (default: `10`)
- `--min-count`: mínimo de ocurrencias para archivo filtrado (default: `20`)
- `--output-dir`: carpeta de salida (default: `backtest_output`)

### Archivos de salida (por ticker)

Para cada ticker (`btc`, `eth`, `sol`, `xrp`):
- `{ticker}_1m_3m.csv`
- `{ticker}_multiframe.xlsx`
- `{ticker}_pm_ranges.csv`
- `{ticker}_pm_ranges_mincount_20.csv`

Salida consolidada:
- `merged_pm_ranges_4cryptos.csv` (incluye columna `ticker`)

## Tutorial del XLSX generado

El archivo `.xlsx` incluye una hoja por intervalo y una hoja `features_summary`.

### Columnas por hoja de intervalo

- `open_time`: timestamp de apertura (Unix ms)
- `open_time_utc`: apertura en UTC (fecha legible)
- `open`, `high`, `low`, `close`: OHLC de la vela agregada
- `volume`: volumen del activo base
- `close_time`: timestamp de cierre (Unix ms)
- `quote_asset_volume`: volumen en activo cotizado (por ejemplo USDT)
- `number_of_trades`: total de trades en la vela
- `taker_buy_base_volume`: volumen comprador agresor (base)
- `taker_buy_quote_volume`: volumen comprador agresor (quote)
- `roi_x_minute`: retorno de la vela, `(close - open) / open`
- `roi_<intervalo>`: alias del retorno por intervalo (ej. `roi_5m`)
- `volatility`: rango relativo de vela, `(high - low) / open`
- `log_return`: retorno logarítmico vs vela previa, `ln(close_t / close_t-1)`
- `direction`: `up`, `down` o `flat`
- `up_move`: 1 si sube, 0 si no
- `down_move`: 1 si baja, 0 si no
- `prob_up`: media móvil de `up_move` (ventana `--prob-window`, default 20)
- `prob_down`: `1 - prob_up`
- `15m_block_ts`: bloque temporal de 15 minutos (timestamp UTC)
- `ts_15m_block`: bloque de 15 minutos en Unix ms

### Qué puedes medir con estas columnas

- Sesgo de mercado reciente: con `prob_up` y `prob_down`
- Impulso de corto plazo: con `roi_x_minute` y `direction`
- Volatilidad intravela: con `volatility`
- Flujo comprador agresor: con `taker_buy_base_volume / volume`
- Consistencia de movimiento por intervalo: con `pct_up`, `pct_down` de `features_summary`

### Playbook simple de 5 reglas

1. Filtro de régimen:
   - operar largos solo si `prob_up >= 0.60`
2. Entrada momentum:
   - `direction == up`, `roi_x_minute > 0`, y `taker_buy_base_volume / volume >= 0.55`
3. Evitar sobreextensión:
   - no entrar si `roi_x_minute > 0.012` (ejemplo para 5m)
4. Salida por pérdida de ventaja:
   - cerrar si `direction == down` o `prob_up < 0.50`
5. SL/TP adaptativos:
   - `SL = 0.8 * mean_volatility`, `TP = 1.5 * mean_volatility`

## Plantilla de backtest sobre el XLSX

Se incluye el script `backtest_xlsx_template.py` para probar este playbook sobre una hoja del Excel.

### Dependencias

```bash
pip install pandas numpy openpyxl
```

### Ejecución

```bash
python backtest_xlsx_template.py \
  --input btcusdt_multiframe.xlsx \
  --sheet 5min \
  --initial-capital 10000 \
  --fee-bps 5 \
  --risk-per-trade 0.01 \
  --prob-threshold 0.60 \
  --min-taker-ratio 0.55 \
  --max-roi-entry 0.012
```

### Métricas que entrega

- `total_return_pct`
- `win_rate`
- `profit_factor`
- `max_drawdown_pct`
- `num_trades`

## Runner de matriz de timeframes (A/B/C)

Para automatizar comparación entre sets de intervalos, usa:

```bash
python3 run_experiments_timeframes.py \
  --input btcusdt_multiframe.xlsx \
  --setups A1,A2,B,C \
  --output-summary backtest_output/timeframe_setups_summary.csv \
  --output-detail backtest_output/timeframe_setups_detail.csv \
  --top 15
```

Setups incluidos:
- `A1`: `5m,15m,30m,60m`
- `A2`: `5m,10m,15m,20m,30m,60m`
- `B`: `2m..60m` (todos)
- `C`: `3m,5m,8m,13m,21m,34m,55m`

Opcional: guardar CSV de trades por intervalo:

```bash
python3 run_experiments_timeframes.py \
  --input btcusdt_multiframe.xlsx \
  --save-trades-dir backtest_output/trades_by_setup
```

### Grid-search de parámetros

Para barrer combinaciones de reglas y obtener ranking automático:

```bash
python3 run_experiments_timeframes.py \
  --input btcusdt_multiframe.xlsx \
  --setups A1,A2,B,C \
  --grid-search \
  --grid-prob-thresholds 0.60,0.65,0.70 \
  --grid-min-taker-ratios 0.55,0.60,0.65 \
  --grid-max-roi-entries 0.008,0.010,0.012 \
  --grid-sl-mults 0.60,0.80 \
  --grid-tp-mults 1.5,2.0 \
  --output-summary backtest_output/timeframe_grid_summary.csv \
  --output-detail backtest_output/timeframe_grid_detail.csv \
  --top 20
```

Tip: empieza con una grilla pequeña (o `--max-combos`) para iterar rápido.
