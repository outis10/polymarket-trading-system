# Polymarket Trading System

Sistema automatizado de trading para Polymarket con gestión de riesgo, estrategias modulares e integración con LangChain/LangGraph.

## 🎯 Características

- **Wrapper del cliente oficial de Polymarket**: Capa de abstracción sobre `py-clob-client`
- **Gestión de riesgo**: Stop-loss, take-profit, límites de posición
- **Estrategias modulares**: Sistema extensible para diferentes estrategias de trading
- **Monitoreo de mercados**: Detección de oportunidades en tiempo real
- **Integración con IA**: Soporte para agentes LangChain/LangGraph
- **Logging completo**: Registro detallado de operaciones y errores

## 📁 Estructura del Proyecto

```
polymarket-trading-system/
├── config/              # Configuración
│   ├── settings.py     # Settings principales
│   └── strategies.yaml # Configuración de estrategias
├── core/               # Componentes core
│   └── client_wrapper.py # Wrapper del cliente Polymarket
├── monitoring/         # Monitoreo de mercados
│   ├── event_detector.py
│   └── market_scanner.py
├── strategy/          # Estrategias de trading
│   ├── base_strategy.py
│   ├── arbitrage.py
│   └── momentum.py
├── risk/              # Gestión de riesgo
│   └── position_manager.py
├── execution/         # Ejecución de órdenes
│   └── order_executor.py
├── analytics/         # Análisis y logging
│   ├── performance.py
│   └── logger.py
├── agents/           # Agentes LangChain
│   ├── decision_agent.py
│   └── analysis_agent.py
├── examples/           # Ejemplos para aprender a utilizar polymarket
└── tests/            # Tests
```

## 🚀 Instalación

### 1. Clonar y configurar entorno

```bash
cd /home/desarrollo/dev/proyectos/polymarket-trading-system

# Crear entorno virtual
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# o
venv\Scripts\activate     # Windows

# Instalar dependencias
pip install -r requirements.txt
```

### 2. Configurar variables de entorno

Copiar `.env.example` a `.env` y configurar:

```bash
cp .env.example .env
nano .env
```

Configurar las siguientes variables:

```env
# L1 Authentication (Clave privada del wallet)
POLYMARKET_PRIVATE_KEY=0x...

# Configuración del wallet
POLYMARKET_FUNDER=0x...
POLYMARKET_SIGNATURE_TYPE=1  # 1=Magic/email, 0=MetaMask, 2=proxy

# L2 Authentication (Generadas con generate_credentials.py)
POLYMARKET_API_KEY=...
POLYMARKET_SECRET=...
POLYMARKET_PASSPHRASE=...

# Network
USE_TESTNET=true
CHAIN_ID=80002  # 80002=testnet Polygon Amoy, 137=mainnet Polygon

# Configuración de trading
MAX_POSITION_SIZE=100.0
MAX_TOTAL_EXPOSURE=500.0
STOP_LOSS_PCT=0.05
TAKE_PROFIT_PCT=0.15

# OpenAI (para LangChain)
OPENAI_API_KEY=tu_openai_key
```

### 3. Obtener credenciales de Polymarket

**Importante**: Polymarket NO tiene una interfaz web para generar API keys. Las credenciales se derivan programáticamente desde tu clave privada del wallet.

#### ⚡ Guía Rápida para Usuarios de MetaMask

Si conectaste MetaMask directamente a Polymarket, consulta la **[Guía Rápida MetaMask](QUICKSTART_METAMASK.md)** para instrucciones paso a paso específicas.

#### Polymarket usa autenticación de dos niveles:
- **L1 (Nivel 1)**: Tu clave privada del wallet (Polygon)
- **L2 (Nivel 2)**: API credentials (apiKey, secret, passphrase) derivadas de tu clave privada

#### Paso 1: Obtener tu clave privada

**Si usas email/Magic Link (más común):**
1. Ve a [reveal.magic.link/polymarket](https://reveal.magic.link/polymarket)
2. Inicia sesión con tu email de Polymarket
3. Copia tu clave privada (debe empezar con `0x`)

**Si usas MetaMask:**
1. Abre MetaMask → Click en los 3 puntos → Detalles de la cuenta
2. Exportar clave privada
3. Copia tu clave privada (debe empezar con `0x`)

#### Paso 2: Obtener tu dirección de funder

1. Ve a [polymarket.com/settings](https://polymarket.com/settings)
2. Copia tu dirección de wallet (la que tiene fondos)

#### Paso 3: Generar credenciales de API

**Opción A - Script interactivo (RECOMENDADO):**

Usa el script interactivo incluido en el proyecto:

```bash
# Activar entorno virtual
source venv/bin/activate

# Ejecutar script de generación
python generate_credentials.py
```

El script te guiará paso a paso y mostrará las credenciales listas para copiar a tu `.env`

**Opción B - Script manual:**

Si prefieres hacerlo manualmente, crea `generate_credentials_manual.py`:

```python
from py_clob_client.client import ClobClient

# Configuración
HOST = "https://clob-testnet.polymarket.com"  # testnet
CHAIN_ID = 80002  # testnet
PRIVATE_KEY = "0x..."  # Tu clave privada del Paso 1
FUNDER = "0x..."  # Tu dirección de wallet del Paso 2

# Crear cliente
client = ClobClient(
    HOST,
    key=PRIVATE_KEY,
    chain_id=CHAIN_ID,
    signature_type=1,  # 1 para Magic/email, 0 para MetaMask, 2 para browser proxy
    funder=FUNDER
)

# Generar/derivar credenciales
api_creds = client.create_or_derive_api_creds()

print("=== Copia esto a tu .env ===")
print(f"POLYMARKET_PRIVATE_KEY={PRIVATE_KEY}")
print(f"POLYMARKET_FUNDER={FUNDER}")
print(f"POLYMARKET_API_KEY={api_creds.api_key}")
print(f"POLYMARKET_SECRET={api_creds.api_secret}")
print(f"POLYMARKET_PASSPHRASE={api_creds.api_passphrase}")
```

Ejecutar:
```bash
source venv/bin/activate
python generate_credentials_manual.py
```

**Notas de seguridad:**
- Borra cualquier script temporal después de copiar las credenciales
- Las credenciales son determinísticas (siempre las mismas para la misma clave privada)
- Si pierdes las credenciales, puedes regenerarlas ejecutando el script nuevamente

#### Tipos de Signature

| Tipo | Valor | Descripción |
|------|-------|-------------|
| EOA (MetaMask) | 0 | Wallet estándar. **Requiere aprobar allowances manualmente** |
| POLY_PROXY (Magic/Email) | 1 | Login con email/Google. Allowances automáticos |
| GNOSIS_SAFE | 2 | Multisig proxy para browser wallets |

#### Notas importantes sobre claves privadas en MetaMask

**La clave privada es la MISMA para todas las redes**:
- No importa si tienes seleccionada Ethereum, Polygon, BSC, etc.
- La misma clave privada funciona en todas las redes
- Solo usa la clave privada de la cuenta que conectaste a Polymarket

**Formato de la clave privada**:
- Debe empezar con `0x`
- Si MetaMask te muestra la clave SIN el prefijo `0x`, agrégalo manualmente
- Ejemplo: `abc123...` → `0xabc123...`

**Para usuarios de MetaMask (signature_type=0)**:
- Debes aprobar manualmente los allowances de USDC y Conditional Tokens
- Esto se hace una sola vez antes de tu primer trade
- Consulta la sección "Aprobar Allowances para MetaMask" más abajo

### 4. Aprobar Allowances para MetaMask (solo signature_type=0)

**IMPORTANTE**: Si usas MetaMask (signature_type=0), debes aprobar allowances ANTES de poder hacer trading. Los usuarios de Magic/Email (signature_type=1) NO necesitan hacer esto.

Los allowances permiten que los contratos de Polymarket muevan tus tokens USDC y Conditional Tokens.

**Opción A - Desde la interfaz web (más fácil)**:
1. Ve a [polymarket.com](https://polymarket.com)
2. Conecta tu MetaMask
3. Deposita USDC (esto aprobará automáticamente los allowances)

**Opción B - Programáticamente**:
```python
# Crear script approve_allowances.py
from py_clob_client.client import ClobClient

PRIVATE_KEY = "0x..."  # Tu clave privada
CHAIN_ID = 137  # 137 para mainnet, 80002 para testnet

client = ClobClient(
    "https://clob.polymarket.com",
    key=PRIVATE_KEY,
    chain_id=CHAIN_ID,
    signature_type=0,
    funder=PRIVATE_KEY  # Para EOA, funder es tu misma dirección
)

# Aprobar allowances
client.set_allowances()
print("✓ Allowances aprobados correctamente")
```

**Verificar allowances**:
```python
allowances = client.get_allowances()
print(f"USDC Allowance: {allowances['usdc']}")
print(f"CTF Allowance: {allowances['ctf']}")
```

## 📖 Uso Básico

### Opción A: Backend + Frontend (recomendado)

Esta es la forma actual de usar la interfaz web en tiempo real.

#### 1) Levantar backend (FastAPI)

En una terminal, desde la raíz del proyecto:

```bash
source venv/bin/activate
pip install -r backend/requirements.txt
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

Backend disponible en:
- API docs: `http://localhost:8000/docs`
- WebSocket: `ws://localhost:8000/ws/events`

#### 2) Levantar frontend (React + Vite)

En otra terminal:

```bash
cd frontend
npm install
npm run dev
```

Frontend disponible en:
- UI: `http://localhost:5173`

Nota: `frontend/vite.config.ts` ya incluye proxy de `/api` y `/ws` hacia `localhost:8000`.

#### 3) Modo demo vs live

El modo se controla desde WebSocket (`switch_mode`) y por configuración de eventos:
- Demo: usa datos simulados (`demo_events` en `config/events.yaml`)
- Live: usa Binance + Polymarket (`events` en `config/events.yaml`)

Para live trading, asegúrate de tener `.env` con credenciales válidas.

### Opción B: Bot CLI (flujo clásico)

```bash
source venv/bin/activate
python main.py
```

### Exportar histórico de trades (CSV/JSON)

Usa el script `export_trades.py` para guardar tus transacciones y analizarlas después.

```bash
source venv/bin/activate
python export_trades.py --output trades_export.csv
```

Ejemplos útiles:

```bash
# Exportar a JSON
python export_trades.py --format json --output trades_export.json --limit 500

# Muestreo continuo cada 1 segundo por 10 minutos (append)
python export_trades.py --poll-seconds 1 --duration-seconds 600 --append --output trades_stream.csv

# Filtrar por side/token/mercado
python export_trades.py --side BUY --asset-id <TOKEN_ID> --market "<MARKET_ID_O_TEXTO>" --output buy_trades.csv
```

Parámetros principales:
- `--poll-seconds`: intervalo de captura en segundos (ej: `1`)
- `--duration-seconds`: duración total del muestreo (`0` = infinito)
- `--append`: agrega nuevos registros al archivo en vez de sobrescribir
- `--limit`: máximo de trades por consulta
- `--before` / `--after`: cursores/filtros temporales si el API los soporta

### Ejemplo de uso programático

```python
from config.settings import settings
from core.client_wrapper import PolymarketClient
from risk.position_manager import PositionManager
from execution.order_executor import OrderExecutor

# Inicializar componentes
client = PolymarketClient(settings.polymarket)
position_manager = PositionManager(
    max_position_size=settings.trading.max_position_size,
    max_total_exposure=settings.trading.max_total_exposure
)
executor = OrderExecutor(client, position_manager)

# Obtener mercados
markets = client.get_markets(closed=False, active=True)

# Ejecutar estrategia (ejemplo)
for market in markets:
    # Tu lógica de análisis aquí
    pass
```

## 🔧 Desarrollo

### Crear una nueva estrategia

```python
from strategy.base_strategy import BaseStrategy, Signal, SignalAction
from typing import Dict, Any, Optional

class MiEstrategia(BaseStrategy):
    def __init__(self, config: Dict[str, Any]):
        super().__init__("MiEstrategia", config)
    
    def analyze(self, market_data: Dict[str, Any]) -> Optional[Signal]:
        # Tu lógica aquí
        # Retornar Signal o None
        pass
```

### Ejecutar tests

```bash
pytest tests/
```

## 📊 Gestión de Riesgo

El sistema incluye gestión automática de riesgo:

- **Stop-loss**: Cierre automático en pérdidas del 5% (configurable)
- **Take-profit**: Cierre automático en ganancias del 15% (configurable)
- **Límites de posición**: Máximo por posición individual
- **Límite de exposición total**: Control de exposición agregada

## 🤖 Integración con LangChain

El directorio `agents/` está preparado para integración con LangChain:

```python
from langchain import OpenAI
from agents.decision_agent import DecisionAgent

# Crear agente de decisión
agent = DecisionAgent(
    llm=OpenAI(temperature=0),
    client=client
)

# Analizar mercado
decision = agent.analyze_market(market_id)
```

## 📝 Logging

Los logs se guardan en:
- `trading_bot.log`: Log completo del bot
- Console: Salida en tiempo real

Configurar nivel de logging en `.env`:
```env
LOG_LEVEL=INFO  # DEBUG, INFO, WARNING, ERROR
```

## ⚠️ Advertencias

- **SIEMPRE** comenzar en testnet (`USE_TESTNET=true`)
- **NUNCA** compartir tu clave privada o credenciales API
- **NUNCA** commitear el archivo `.env` o `generate_credentials.py` con datos reales
- **BORRAR** `generate_credentials.py` después de generar credenciales de mainnet
- Las credenciales son **determinísticas** (la misma clave privada siempre genera las mismas)
- Si pierdes las credenciales API, puedes regenerarlas con el mismo script
- Para MetaMask (signature_type=0): debes aprobar allowances de tokens antes de tradear
- Probar estrategias extensivamente antes de usar dinero real
- El trading automatizado conlleva riesgos

## 🔒 Seguridad

- API keys en variables de entorno
- `.env` en `.gitignore`
- No guardar credenciales en código
- Usar testnet para desarrollo

## 📚 Recursos

- [Documentación Polymarket API](https://docs.polymarket.com)
- [py-clob-client GitHub](https://github.com/Polymarket/py-clob-client)
- [LangChain Documentation](https://python.langchain.com)

## 🤝 Contribuir

1. Fork el proyecto
2. Crear feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit cambios (`git commit -m 'Add some AmazingFeature'`)
4. Push to branch (`git push origin feature/AmazingFeature`)
5. Abrir Pull Request

## 📄 Licencia

Este proyecto es de uso personal. Ver `LICENSE` para más detalles.

## 👤 Autor

Narciso - Treasury Operations & Software Developer

## 🗺️ Roadmap

- [ ] Implementar estrategia de arbitraje
- [ ] Implementar estrategia de momentum
- [ ] Integración completa con LangChain
- [ ] Dashboard web para monitoreo
- [ ] Backtesting framework
- [ ] Notificaciones (Telegram, Email)
- [ ] Base de datos para histórico
- [ ] API REST para control remoto

## 📞 Soporte

Para preguntas o issues, abrir un issue en GitHub o contactar directamente.

---

⚡ **Desarrollado con** Python, Polymarket API, LangChain
