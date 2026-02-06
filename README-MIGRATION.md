# Polymarket Monitor - React + FastAPI

Dashboard de monitoreo en tiempo real para Polymarket, migrado de Dash a React + FastAPI con WebSockets.

## Arquitectura

```
┌─────────────────────────────────────────────────────────┐
│  Browser (React + TypeScript)                           │
│                                                         │
│  useWebSocket("/ws/events") ──→ useEventsStore (zustand)│
│       │                              │                  │
│       │                    ┌─────────┴──────────┐       │
│       │                    │                    │       │
│  PriceDisplay  PriceChart  OrderBook  TradingPanel      │
│  (re-renders only changed components via zustand)       │
└────────────┬────────────────────────────────────────────┘
             │ WebSocket + REST
             ▼
┌─────────────────────────────────────────────────────────┐
│  FastAPI Backend (Python)                               │
│                                                         │
│  /ws/events ← WebSocket broadcast to all clients        │
│       ▲                                                 │
│  EventManager (singleton, background task)              │
│       │                                                 │
│  ┌────┴─────────────────────────────────┐               │
│  │  BinanceService      PolymarketService│              │
│  │  (REST + WS)         (REST + WS)      │              │
│  └───────────────────────────────────────┘               │
│                                                         │
│  /api/orders ← REST → PolymarketClient (order exec)    │
│  /api/events ← REST → Initial data load                │
└─────────────────────────────────────────────────────────┘
```

## Requisitos

### Backend
- Python 3.11+
- Dependencias en `backend/requirements.txt`

### Frontend
- Node.js 20 LTS (recomendado)
- npm 10+

## Instalacion

### 1. Backend

```bash
# Desde el directorio raiz del proyecto
cd /home/desarrollo/dev/proyectos/polymarket-trading-system

# Activar virtualenv (si no esta activo)
source venv/bin/activate

# Instalar dependencias del backend
pip install -r backend/requirements.txt
```

### 2. Frontend

```bash
cd frontend
npm install
```

## Ejecucion

### Desarrollo (2 terminales)

**Terminal 1 - Backend:**
```bash
cd /home/desarrollo/dev/proyectos/polymarket-trading-system
source venv/bin/activate
uvicorn backend.main:app --reload --port 8000
```

**Terminal 2 - Frontend:**
```bash
cd /home/desarrollo/dev/proyectos/polymarket-trading-system/frontend
npm run dev
```

Abrir http://localhost:5173 en el navegador.

### Produccion

**Backend:**
```bash
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

**Frontend:**
```bash
cd frontend
npm run build
# Los archivos estaticos quedan en frontend/dist/
```

## Endpoints

### REST API

| Metodo | Endpoint | Descripcion |
|--------|----------|-------------|
| GET | `/api/events` | Lista todos los eventos con datos actuales |
| GET | `/api/events/{id}` | Obtiene un evento por ID |
| GET | `/api/config` | Configuracion de trading y UI |
| POST | `/api/orders` | Ejecuta una orden de trading |
| DELETE | `/api/orders/{id}` | Cancela una orden |

### WebSocket

| Endpoint | Descripcion |
|----------|-------------|
| `/ws/events` | Stream en tiempo real de eventos |

**Mensajes WS (servidor → cliente):**
```json
{"type": "full_snapshot", "data": {"events": {...}, "settings": {...}}}
{"type": "price_update", "event_id": "...", "data": {...}}
{"type": "orderbook_update", "event_id": "...", "data": {...}}
{"type": "settings_update", "data": {...}}
```

**Mensajes WS (cliente → servidor):**
```json
{"type": "switch_mode", "mode": "demo|live"}
{"type": "update_settings", "settings": {"refresh_rate": 5}}
```

## Estructura de Archivos

```
backend/
  main.py                 # FastAPI app + uvicorn
  config.py               # Lee events.yaml + .env
  requirements.txt        # Dependencias Python
  models/
    schemas.py            # Pydantic models
  services/
    binance.py            # Binance REST + WS
    polymarket.py         # Polymarket REST + WS
    demo.py               # Generador de datos demo
    event_manager.py      # Orquestador de updates
  ws/
    manager.py            # WebSocket connection manager
    handlers.py           # Endpoint /ws/events
  routers/
    events.py             # GET /api/events
    trading.py            # POST /api/orders

frontend/
  package.json
  tsconfig.json
  vite.config.ts
  index.html
  src/
    main.tsx              # Entry point
    App.tsx               # Router + layout
    styles/
      global.css          # Tema dark completo
    types/
      events.ts           # Interfaces TypeScript
    stores/
      useEventsStore.ts   # Zustand - estado de eventos
      useSettingsStore.ts # Zustand - UI settings
    hooks/
      useWebSocket.ts     # Conexion WS con reconnect
      useCountdown.ts     # Timer countdown
    components/
      layout/
        Header.tsx        # Header con boton settings
        Sidebar.tsx       # Drawer de configuracion
      EventCard.tsx       # Card completa de evento
      PriceDisplay.tsx    # Precios y probabilidades
      PriceChart.tsx      # Chart con lightweight-charts
      OrderBook.tsx       # Tabla de order book
      TradingPanel.tsx    # Panel de trading
      Countdown.tsx       # Timer MM:SS
```

## Configuracion

### Modo Demo vs Live

- **Demo**: Datos simulados, no requiere credenciales
- **Live**: Conecta a Polymarket y Binance APIs

Cambiar modo desde el Sidebar en la UI, o via WebSocket:
```json
{"type": "switch_mode", "mode": "live"}
```

### Variables de Entorno (.env)

```env
# Polymarket L1 Auth
POLYMARKET_PRIVATE_KEY=0x...
POLYMARKET_FUNDER=0x...
POLYMARKET_SIGNATURE_TYPE=1

# Polymarket L2 Auth (opcional, se deriva si no existe)
POLYMARKET_API_KEY=
POLYMARKET_SECRET=
POLYMARKET_PASSPHRASE=

# Network
USE_TESTNET=true
CHAIN_ID=80002
```

### Eventos (config/events.yaml)

Los eventos se configuran en `config/events.yaml`. Ver archivo existente para ejemplos.

## Tecnologias

### Backend
- FastAPI 0.115+
- Uvicorn (ASGI server)
- WebSockets (websockets lib)
- Pydantic 2.0
- py-clob-client (Polymarket SDK)

### Frontend
- React 19
- TypeScript 5.7
- Vite 6
- Zustand 5 (state management)
- lightweight-charts 4.2 (TradingView charts)

## Migracion desde Dash

Este proyecto reemplaza el dashboard Dash (`dashboard/`) con:

| Dash | React + FastAPI |
|------|-----------------|
| `dcc.Store` | Zustand stores |
| `dcc.Interval` | WebSocket push |
| `dcc.Graph` (Plotly) | lightweight-charts |
| Callbacks | REST + WS handlers |
| `html.Table` | React components |

El directorio `dashboard/` original se mantiene como referencia.
