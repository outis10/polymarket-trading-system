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
