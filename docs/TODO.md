- [x] Prioridad alta: corregir manejo de fallos post-envio al CLOB.
  Fix: en status=failed (no_result y exception), se hace rollback de _order_guard_records y reset de _bot_prev_gate_enabled.
  Cubre: red/auth/exchange errors ya no dejan exposicion fantasma ni cooldowns falsos.

- [x] Prioridad alta: implementar cap real de exposicion por ticker/correlated cluster.
  Fix: nuevo setting bot_max_ticker_exposure_pct (default 0=off). Verificado en evaluate_bot_order_candidate y validate_order_risk_guards.
  Reason code: ticker_exposure_cap_reached con mensaje detallado en format_risk_guard_block_reason.

- [ ] Prioridad media: alinear inventario/riesgo con fill real.
  El bot ya extrae `fill_price_real` y `filled_shares_real`, pero parte del estado local sigue usando precio/shares estimados al enviar.
  Criterio de aceptacion:
  - posicion local, exposure tracking y analytics usan fill real cuando exista;
  - si hay fill parcial, el estado refleja size real ejecutado;
  - evitar divergencia entre orden enviada y posicion registrada.

- [ ] Prioridad media: limpieza de arquitectura de ventanas `early/late`.
  Hoy hay naming/config inconsistente entre schema, WS, frontend y runtime (`*_seconds` vs `*_start`/`*_end`).
  Si ya no se usa operativamente, conviene eliminar el mecanismo legacy completo para evitar falsa sensacion de control.
  Criterio de aceptacion:
  - una sola convencion de nombres en backend/frontend/runtime;
  - remover campos legacy no usados;
  - migracion de `runtime_settings.json` sin romper arranque.

- [ ] Prioridad media: revisar edge ejecutable vs precio real enviado.
  Hoy Kelly/eligibilidad se calculan con `ask_price`, pero la orden FOK puede salir a `ask + tolerance`.
  Eso puede destruir parte importante del edge neto en mercados thin.
  Criterio de aceptacion:
  - sizing y min edge consideran precio efectivamente enviable;
  - medir impacto de `fak_price_tolerance` y retries en `edge_at_fill_pct`;
  - evitar tomar trades cuyo edge desaparece por tolerancia/slippage esperado.

- [ ] Prioridad baja: retirar fallback legacy `kelly_bankroll`.
  `kelly_live_bankroll_usd` y `kelly_paper_bankroll_usd` siguen teniendo sentido como bankroll manual por modo.
  Lo realmente legacy hoy parece ser `kelly_bankroll`.
  Criterio de aceptacion:
  - confirmar que frontend/runtime ya no dependen de `kelly_bankroll`;
  - migrar settings viejos al cargar;
  - luego remover fallback del backend.

 - [] esta variable solo esta en version dos "bot_max_ticker_exposure_pct": 15,
