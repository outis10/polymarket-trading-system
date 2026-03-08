## El sabado 7 Marzo de 2026
Se analizo estrategia de contrarian pero no se obtuvieron resultados deterministicos.
Se procedio a un analisis Blind SPOT con el objetivo de identificar patrones: blind_spot_analysis.md

**Filtros implementados (2026-03-07)**:
- `quant_gate_max_spread_pct` (0.03 recomendado): bloquea trades cuando spread ask-bid > 3%.
  Razon: spread alto = mercado iliquido, assumptions del modelo no se cumplen.

## El domingo 8 Marzo de 2026

**Infraestructura**:
- Agregado endpoint `GET /api/equity` que retorna bankroll + positions_value + claimable + net_pnl en una sola llamada paralela.
- Header del frontend actualizado con chip "Net PnL" (verde/rojo) usando el nuevo endpoint.
- `live_equity_start_bankroll_usd = 122.47` fijado en runtime_settings (primer bankroll registrado: 2026-03-04T01:51 UTC).
- Background task `_equity_snapshot_loop`: guarda equity completo (bankroll+claimable+positions) cada 30 min en `backtest_output/equity_snapshots.csv`.

**Analisis de actividad Polymarket (scripts/export_polymarket_activity.py)**:
- Exportados 3,059 trades y 540 posiciones desde data-api.polymarket.com.
- Script `scripts/analyze_polymarket_activity.py` con 5 analisis: PnL por mercado, distribucion de fills, actividad por hora PST, slippage estimado, posiciones abiertas.
- PnL real desde 2026-03-04: +$46.20 (+0.99% ROI) sobre $4,684 apostados.

**Hallazgo critico — fills en precio < 0.40**:
- 67 trades con fill price 0.10-0.40 generaron -$79 PnL combinado.
- 328 trades con fill price 0.50-0.90 generaron +$488 PnL combinado.
- El edge promedio en la zona perdedora es -6.4% (vs +17.9% en la zona ganadora).
- Confirmado cruzando `opportunity_outcomes.csv` con `bot_orders_all_2026-03-08.csv`.

**Filtros implementados (2026-03-08)**:
- `quant_gate_min_ask_price` (0.40 recomendado): bloquea trades cuando el ask real del outcome < 0.40.
  Razon: fills a precio bajo tienen EV negativo historicamente (-13% en bucket 0.3-0.4 con N=40).
  Reason en opportunity_blocked.csv: `ask<0.40`

**Proxima revision recomendada**: ~2026-03-22
- Confirmar si filtro min_ask_price reduce losses sin bloquear oportunidades buenas.
- Re-correr analyze_blind_spots.py con ~2 semanas mas de datos.
- Re-correr analyze_polymarket_activity.py para ver evolucion de PnL por bucket.
