# Polymarket Monitor Dashboard (Dash)

Real-time multi-event monitoring dashboard for Polymarket, built with Dash.

## Quick Start

```bash
pip install dash dash-bootstrap-components cachetools pandas plotly pyyaml requests
python dashboard/run.py
```

Open http://localhost:8050

## Structure

```
dashboard/
  app.py                    # App factory + entry point
  layout.py                 # Layout builder (header, sidebar, event grid, stores, intervals)
  run.py                    # python dashboard/run.py
  assets/
    style.css               # Dark theme CSS
  components/
    event_card.py           # Full event card (header, price, chart, order book, trading)
    price_display.py        # Current price, price to beat, change indicator
    countdown.py            # MM:SS countdown timer
    chart.py                # Dual-axis price chart (price + probability)
    order_book.py           # HTML tables with CSS depth bars
    sidebar.py              # Offcanvas settings panel
  callbacks/
    data_updates.py         # Interval -> fetch data -> dcc.Store
    price_callbacks.py      # Store -> price display divs
    chart_callbacks.py      # Store -> chart figures
    countdown_callbacks.py  # 1s interval -> countdown
    orderbook_callbacks.py  # Store + tab clicks -> order book HTML
    trading_callbacks.py    # Quick amounts, trade summary, trade execution
    sidebar_callbacks.py    # Mode toggle, refresh rate, chart options
  data/
    models.py               # EventData, OrderBook dataclasses + serialization
    demo.py                 # Simulated price/order book generators
    binance.py              # Binance API helpers (TTLCache)
    polymarket.py           # Polymarket client wrapper
```

## Architecture

### State (dcc.Store)

| Store | Purpose | Writer |
|---|---|---|
| `events-data-store` | All event data (prices, history, order books) | `data_updates` callback only |
| `app-settings-store` | Mode, refresh rate, chart options | `sidebar_callbacks` only |

Trading inputs (`shares-input`, `limit-price-input`, `trade-type-radio`) live in the DOM and are never written by data callbacks, so they keep focus and value during refresh.

### Intervals

| Interval | Period | Drives |
|---|---|---|
| `refresh-interval` | Configurable (1-30s) | Data fetch + price/chart/order book updates |
| `countdown-interval` | Always 1s | Countdown display only |

### Callbacks (pattern-matching)

One callback per type serves all events via `MATCH`/`ALL`:

```
refresh-interval
  -> data_updates -> writes events-data-store
      -> price_callbacks (MATCH) -> price divs
      -> chart_callbacks (MATCH) -> chart figures
      -> orderbook_callbacks (MATCH) -> order book HTML

countdown-interval
  -> countdown_callbacks (ALL) -> countdown displays (reads store, never writes)

User interactions (independent of interval):
  -> quick-btn click -> shares-input value
  -> shares/limit change -> trade-summary
  -> trade-btn click -> execute trade, show alert
  -> sidebar toggles -> app-settings-store + interval.interval
```

## Modes

- **Demo**: Simulated price data from `config/events.yaml` `demo_events` section. No external connections.
- **Live**: Fetches real prices from Binance (spot price) and Polymarket (order books/probabilities). Requires `config/events.yaml` `events` section and a configured `.env`.

Toggle between modes in the Settings panel (gear icon).

## Configuration

Events are defined in `config/events.yaml`. Demo events need `initial_price`, `price_to_beat`, `volatility`. Live events need `binance_symbol`, `event_start_time`, `condition_id`, and `tokens`.
