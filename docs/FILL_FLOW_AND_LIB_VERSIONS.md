# Fill Flow and Library Versions

## Fill flow in the bot

### 1. Market BUY is sent to the CLOB

File: `backend/routers/trading.py`

```python
elif order.order_type == "market":
    if not is_sell:
        ask_price = quant_debug.get("ask_price_at_check")
        result = client.place_fok_order(token_id, "BUY", notional_usd, ask_price)
    else:
        result = client.place_market_order(token_id, side, effective_shares)
```

### 2. Wrapper that actually sends the order to Polymarket

File: `core/client_wrapper.py`

```python
def place_fok_order(
    self,
    token_id: str,
    side: str,
    amount_usd: float,
    hint_price: float = 0.0,
) -> Optional[Dict[str, Any]]:
    order_args = MarketOrderArgs(
        token_id=token_id,
        amount=amount_usd,
        side=side.upper(),
        order_type=OrderType.FAK,
        price=hint_price if hint_price > 0 else 0,
    )
    signed_order = self.client.create_market_order(order_args)
    result = self.client.post_order(signed_order, OrderType.FAK)
    return result
```

### 3. When the CLOB returns a result, the fill is recorded

File: `backend/routers/trading.py`

```python
if result:
    order_id = (
        getattr(result, "id", None)
        or getattr(result, "orderID", None)
        or (result.get("orderID") if isinstance(result, dict) else None)
        or str(result)[:16]
    )
    status = (
        getattr(result, "status", None)
        or (result.get("status") if isinstance(result, dict) else None)
        or "OPEN"
    )
    now_fill = datetime.now(tz=timezone.utc)
    if not is_sell:
        event_manager.register_order_fill(
            event_id=order.event_id,
            event=event,
            outcome=outcome_side,
            notional_usd=notional_usd,
            now_utc=now_fill,
            bankroll_snapshot_usd=bankroll_usd,
        )
        taking_amount = (
            result.get("takingAmount") if isinstance(result, dict) else None
        )
        real_shares = (
            float(taking_amount) if taking_amount else effective_shares
        )
        event_manager.record_position_buy(
            event_id=order.event_id,
            outcome=outcome_side,
            token_id=token_id,
            shares=real_shares,
            price=order_price_ref,
            placed_at_utc=now_fill.isoformat(),
        )
```

### 4. Auto-bot path also pre-logs and then attempts the fill

File: `backend/services/event_manager.py`

```python
_append_bot_order_log(_pre_log_row)
self.register_order_fill(
    event_id=event_id,
    event=event_dict,
    outcome=side,
    notional_usd=notional_usd,
    now_utc=now_utc,
)

result = await asyncio.to_thread(
    client.place_fok_order,
    token_id,
    "BUY",
    notional_usd,
    order_price,
)
```

## Versions used in this repo

| Library | Declared in `backend/requirements.txt` | Installed in current environment | Notes |
|---|---|---|---|
| `py-clob-client` | `py-clob-client` | `0.34.5` | Main Polymarket CLOB trading client |
| `requests` | `requests` | `2.32.5` | REST calls for market data and auxiliary endpoints |
| `websockets` | `websockets>=14.0` | `16.0` | Real-time Polymarket stream |
| `pydantic` | `pydantic>=2.0` | `2.12.5` | Request/settings validation |
| `python-dotenv` | `python-dotenv` | `1.2.1` | `.env` loading |
| `pyyaml` | `pyyaml` | `5.4.1` | YAML config loading |
| `cachetools` | `cachetools` | `6.2.6` | Auxiliary caching |
| `fastapi` | `fastapi>=0.115.0` | `not installed in current interpreter` | API layer required by the app |
| `uvicorn` | `uvicorn[standard]>=0.34.0` | `not installed in current interpreter` | ASGI server used to run the API |

## Notes

- `py-clob-client` pulls in important transitive trading dependencies such as:
  - `eth-account`
  - `eth-utils`
  - `httpx`
  - `poly_eip712_structs`
  - `py-builder-signing-sdk`
  - `py-order-utils`
- In this environment, `fastapi` and `uvicorn` were not importable from `python3`, so the table above marks them as not installed in the current interpreter instead of guessing a version.
