# Sell Flow — Documentación Técnica

## Resumen

El sistema permite vender posiciones abiertas desde la tarjeta de cada evento. El botón **Sell** aparece en la tabla de posiciones (`PositionDisplay`) junto a cada posición con qty > 0. La venta pasa por el mismo endpoint de órdenes que las compras (`POST /api/orders`), pero con lógica diferenciada para sells.

---

## 1. UI — PositionDisplay.tsx

La tabla de posiciones muestra una fila por cada outcome (Up / Down) con posición abierta.

```
OUTCOME | QTY  | PRICE | VALUE        | RETURN       | [Sell]
Up      | 12.5 | 0.560 | $7.00        | +$0.50 (8%)  | [Sell]
```

### Flujo del botón Sell

1. El usuario hace click en **Sell** de una fila.
2. El botón pasa a estado `disabled` con texto `"..."` mientras se procesa.
3. Se llama a `POST /api/orders` con:

```json
{
  "event_id": "<event_id>",
  "side": "Sell",
  "outcome": "up",          // o "down"
  "order_type": "market",
  "price": 0.56,            // current_price de la posición (fallback si no hay bid)
  "shares": 12.5            // qty completa de la posición
}
```

4. Al recibir respuesta:
   - **Éxito (2xx):** muestra toast verde con el mensaje del backend. Después de 1.5s refresca las posiciones.
   - **Error:** muestra toast rojo con el detalle del error.
5. El toast se auto-descarta a los 5 segundos.

---

## 2. Backend — POST /api/orders

### Diferencias vs. Buy

El endpoint detecta si es sell con:

```python
is_sell = order.side.strip().upper() == "SELL"
```

Y aplica las siguientes excepciones para sells:

| Check              | Buy                        | Sell               |
|--------------------|----------------------------|--------------------|
| Timeframe filter   | Bloqueado si no coincide   | **Ignorado**       |
| Quant gate         | Bloqueado si gate=False    | **Ignorado**       |
| Risk guards        | Validado (exposición, etc) | **Ignorado**       |
| Notional cap       | Limita shares por cap USD  | **Ignorado** (vende qty completa) |

### Precio del sell (market order)

Para una orden de venta de tipo `"market"`, el backend **no** llama a `place_market_order()` (que podía retornar `None` si no había bids en el CLOB). En su lugar:

```python
# Toma el best bid del order book ya en memoria
ob_key = "order_book_yes" if outcome_side == "up" else "order_book_no"
ob = event.get(ob_key) or {}
bids = ob.get("bids") or []

if bids and isinstance(bids[0], dict):
    sell_price = float(bids[0]["price"])   # best bid del libro
else:
    # Fallback: mid-price del evento, o el precio enviado por el frontend
    mid_key = "yes_price" if outcome_side == "up" else "no_price"
    sell_price = float(event.get(mid_key) or order.price or 0.50)

result = client.place_order(token_id, "SELL", sell_price, effective_shares)
```

**Por qué limit y no market:** Polymarket CLOB no tiene órdenes market puras; internamente `place_market_order` ya era un limit al best price. El cambio evita la llamada API extra que podía fallar.

### Token ID

El backend resuelve el token correcto a partir del `outcome`:

```python
token_id = event.get("yes_token_id") if order.outcome == "up" else event.get("no_token_id")
```

### Demo mode

En modo demo, los sells simulan éxito directamente (mismo path que antes, sin validar guards).

---

## 3. Diagrama de flujo

```
[Click Sell]
     │
     ▼
POST /api/orders { side: "Sell", outcome, shares: qty_completa }
     │
     ├── is_sell = True
     │
     ├── [SKIP] Timeframe filter
     ├── [SKIP] Quant gate
     ├── [SKIP] Risk guards
     ├── [SKIP] Notional cap
     │
     ├── Resolve token_id (yes_token o no_token)
     │
     ├── Resolve sell_price:
     │     ├── best bid de order_book en memoria
     │     └── fallback: mid-price → price del frontend
     │
     ├── client.place_order(token_id, "SELL", sell_price, shares)
     │
     ├── [OK] → OrderResponse { order_id, status, message }
     │           → broadcast balance_update por WS
     └── [FAIL] → HTTP 500
```

---

## 4. Limitaciones actuales

- **Sin gate de sell:** No hay lógica que evalúe si conviene vender (p.ej. gate de pérdida mínima, tiempo mínimo de hold). Se vende siempre al precio de mercado.
- **Qty fija = posición completa:** Siempre se vende la cantidad total de la posición mostrada. No hay sell parcial desde la UI.
- **Posiciones derivadas de trades:** El endpoint `GET /api/positions/{event_id}` calcula posiciones sumando BUY/SELL de `get_trades()`. Después de un sell exitoso, la posición desaparecerá del listado al refrescar (~1.5s delay).
