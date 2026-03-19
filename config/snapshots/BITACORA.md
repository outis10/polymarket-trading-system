# Bitácora de Configuraciones

## 2026-03-11 — Semana del 11 al 16 de Marzo

**Snapshot:** `runtime_settings_2026-03-11.json`

**Cambios respecto a sesión anterior:**
- `quant_gate_max_spread_pct`: 0 → **3** (safety net, spreads BTC históricamente < 0.4%)
- `quant_gate_min_ask_price`: 0 → **0.30** (bloquea asks bajos donde el modelo genera edge falso; rango [0.20-0.30) tenía WR 0-17% en datos históricos)

**Contexto de la decisión:**
- Análisis de 665 órdenes resueltas (03-04 al 03-11)
- Ask [0.20-0.25): 5 órdenes, WR 0%, PnL -$12.00
- Ask [0.25-0.30): 6 órdenes, WR 17%, PnL -$1.01
- Edge alto (>20%) en asks bajos = ruido del modelo, no edge real
- Ejemplo gatillo: BTC slot 4 [40,50) UP, ask 0.2069, edge 23.31%, perdió -$5.12

---

## 2026-03-11 — Bot V2 (paper mode, estrategia optimizada)

**Snapshot:** `runtime_settings_v2.json`
**Env:** `.env.v2` | **Puerto:** 8011 | **Output:** `backtest_output_v2/`

**Cambios vs Bot A (live):**
- `bot_paper_mode`: false → **true**
- `quant_gate_min_ask_price`: 0.30 → **0.60**
- `quant_gate_enabled_slots`: [1-6] → **[1-29]** (todos)

**Simulación histórica (7 días):**
- Con ask≥0.60 + todos slots: 335 órdenes | WR 71.9% | PnL +$97.60
- vs baseline ask≥0.30: 649 órdenes | WR 61.5% | PnL +$23.93

**Arrancar ambas instancias (4 terminales):**
```bash
# Terminal 1 — Bot A (live, estrategia actual, puerto 8010)
python -m uvicorn backend.main:app --port 8010

# Terminal 2 — Bot B (paper, estrategia optimizada, puerto 8011)
ENV_FILE=.env.v2 python -m uvicorn backend.main:app --port 8011

# Terminal 3 — Frontend A (localhost:5173 → backend :8010)
cd frontend && npm run dev

# Terminal 4 — Frontend B (localhost:5174 → backend :8011)
cd frontend && npx vite --mode v2
```

---

## 2026-03-12 — Ajustes Bot A y Bot V2 tras análisis de drawdown

### Bot A (live)
**Cambios:**
- `quant_gate_enabled_slots`: [1-6] → **[1-12]** (slots 7-12 tienen WR alto con ask≥0.60)
- `quant_gate_min_ask_price`: 0.30 → **0.60** (bucket [0.50-0.60) tenía WR 35.7%, PnL -$38.75 en 3 días)
- `quant_gate_max_spread_pct`: 3 → **0** (desactivado, spreads BTC < 0.4% con ask alto)
- `bot_drawdown_circuit_breaker_enabled`: **true** (activado)
- `live_equity_start_bankroll_usd`: 100 → **140** (baseline corregido al bankroll actual)
- Umbral de pausa: $70 (50% de $140)

**Contexto:**
- Análisis 79 órdenes resueltas (10-12 Mar): WR 41.8%, PnL -$67.67
- BTC en tendencia bajista (46 DOWN / 33 UP). Modelo no captura trend.
- Slot 4: 24 trades, 25% WR, -$49.35 — mayor destructor de capital
- Rango [40,50): 0% WR, -$31.64 — todas las apuestas perdidas
- Ask [0.50-0.60): WR 35.7%, -$38.75 en 28 trades → eliminado con nuevo min_ask

### Bot V2 (paper)
**Cambios:**
- `quant_gate_min_ask_price`: 0.60 → **0.65**

**Contexto:**
- 251 trades resueltos | WR 65.3% | PnL bruto +$24.61
- Bucket [0.60-0.65): 159 trades (63% del total), WR 61%, PnL -$4.52 — sin contribución al PnL
- Bucket [0.65-0.70): WR 74.6%, PnL +$41.33 — el sweet spot real
- Friction simulada: $71.85 (fee 2% + spread/2 + slippage 3%) — puede estar sobreestimada vs live

---

## 2026-03-13 — Ajustes Bot V2 tras análisis día de pérdidas

**Snapshot:** `runtime_settings_v2_2026-03-13.json`

**Cambios:**
- `quant_gate_min_edge_pct`: 7 → **10** (filtrar señales de baja calidad)
- `bot_max_ticker_exposure_pct`: 15 → **0** (deshabilitado)
- `monitored_tickers`: BTC/ETH/SOL/XRP → **BTC/ETH/SOL** (XRP removido)
- `bot_paper_mode`: true → **false** (modo live)

**Contexto:**
- 106 trades resueltos el 2026-03-12 | WR 60% | PnL -$7.82
- XRP concentraba las pérdidas: WR 52% en rangos near-flat [-0.02,0.00) y [0.00,0.02) → EV negativo a precio 0.60–0.70
- `bot_max_ticker_exposure_pct` bloqueaba señales de alta calidad (edge 40%, prob 90%) en XRP → removido; el drawdown circuit breaker (50%) es la protección sistémica real
- Simulación edge≥10%: 34 trades a 74% WR vs 72 trades a 62% con edge≥7% — calidad sobre volumen

**Criterio de revisión `quant_gate_min_edge_pct`:**
- Revisar el lunes post-pipeline con ≥50 trades acumulados
- Si WR < 65% → considerar subir a 12%; si WR > 75% con N suficiente → mantener

---

---

## 2026-03-19 — Filtro de volatilidad por spread + horas US market open

**Cambios en runtime_settings.json (Bot principal):**
- `quant_gate_max_spread_pct`: 0 → **2** (bloquea órdenes con spread ≥ 2%)
- `quant_gate_blocked_hours_pst`: agrega **10h y 11h** (ventana post-apertura NYSE)

**Análisis que motivó el cambio (831 órdenes resueltas, Mar 4–19):**

| Spread | n | WR | PnL |
|--------|---|----|-----|
| <2%    | 531 | 64.6% | +$58 |
| 2-4%  | 205 | 47.8% | negativo |
| ≥10%  | 11  | 27.3% | negativo |

| Hora PST | n | WR |
|----------|---|----|
| 10h | 45 | 33.3% ← peor hora del día |
| 11h | 37 | 43.2% |
| 12h | 50 | 72.0% (se normaliza) |

**Simulación de impacto histórico:**
- Solo spread ≥2% bloqueado: delta PnL **+$97.80** (36% menos órdenes)
- Solo horas 10-11h bloqueadas: delta PnL **+$93.17** (10% menos órdenes)
- Ambos combinados: **+$156.88** → PnL total de -$39 a **+$117** (WR 66.7%)

**Período perdedor Mar 9-13 (análisis):**
- Spread 2-4%: WR 34.5%, PnL -$92 ← mayor destructor ese período
- Spread <2%: WR 57.8%, PnL -$75 → vol sistémica sostenida, no solo spread puntual
- Pendiente: si persisten pérdidas en días de alta vol sistémica, evaluar CVI como filtro adicional

**Checkpoint bankroll al reinicio:** $89 (kelly_live_bankroll_usd)

---

**Configuración activa Bot A (live):**
- Ticker: BTC
- Timeframe: 5m
- Blocked hours PST: 0-10, 14, 17-18, 20, 23 (weekends: all day)
- quant_gate_min_sample: 80
- quant_gate_min_edge_pct: 7
- kelly_fraction: 0.25
- kelly_live_bankroll_usd: 290
- bot_order_notional_cap_usd: 10
- bot_max_event_exposure_pct: 2
- bot_min_diff_abs: {"BTC": 10}
- mode: live / trading_mode: bot
