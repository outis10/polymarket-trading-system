# LangChain Integration Notes

## Versiones Actuales (Enero 2025)

**LangChain 1.1 es la versión más reciente** (Diciembre 2025)

Las versiones de LangChain en el `requirements.txt` están configuradas para instalar siempre la última versión:

```bash
langchain                     # Core framework (1.1+)
langchain-core                # Core abstractions
langchain-community           # Community integrations
langchain-openai              # OpenAI integration
langchain-anthropic           # Anthropic (Claude) integration
langgraph                     # Graph-based workflows (1.0+)
langsmith                     # LangSmith tracing
```

### ¿Por qué sin versión específica?

✅ **Siempre obtienes la última versión estable**  
✅ **Acceso a nuevas features automáticamente**  
✅ **Bug fixes y mejoras de seguridad**  
✅ **Compatibilidad garantizada entre paquetes**  

⚠️ **Nota:** LangChain 1.x garantiza **no breaking changes** hasta 2.0

## Requisitos de Sistema

- **Python 3.10+** es requerido para LangChain v0.3+
- Verificar versión: `python --version`

## Instalación Recomendada

### Opción 1: Instalación Completa (Recomendada)
```bash
pip install -U langchain langgraph langchain-community
pip install -U langchain-openai  # Si usas OpenAI
pip install -U langchain-anthropic  # Si usas Claude
```

### Opción 2: Solo lo Necesario
```bash
# Core mínimo
pip install -U langchain

# Agregar según necesites
pip install -U langgraph  # Para workflows complejos
pip install -U langchain-openai  # Para GPT models
```

## Cambios Importantes en LangChain v1.0+ y v1.1

### Novedades en LangChain 1.1 (Diciembre 2025)

**Desarrollo de agentes más confiable y estructurado:**
- ✨ **Nuevo loop de agentes** con mejor control
- ✨ **Middleware system** para control fino del ciclo agente
- ✨ **Context-aware agents** con mejor manejo de contexto
- ✨ **Structured outputs** mejorados

### 1. Nuevo Sistema de Agentes (v1.0+)
LangChain v1 introduce `create_agent` como el nuevo estándar:

```python
from langchain import create_agent
from langchain_openai import ChatOpenAI

# Nuevo método (v1.0+)
agent = create_agent(
    model=ChatOpenAI(model="gpt-4"),
    tools=[...],
)

# Método antiguo (deprecated)
# from langgraph.prebuilt import create_react_agent
```

### 2. Content Blocks Estándar
Nueva propiedad `content_blocks` unificada:

```python
response = model.invoke("mensaje")
# Acceso unificado a contenido multimodal
blocks = response.content_blocks
```

### 3. Namespace Simplificado
Funcionalidad legacy movida a `langchain-classic`:

```bash
# Si necesitas funcionalidad legacy
pip install langchain-classic
```

**Legacy incluye:**
- Chains antiguos
- Retrievers (MultiQueryRetriever, etc.)
- Indexing API
- Hub module

## Integración con Este Proyecto

### Estructura Sugerida para Agentes

```python
# agents/trading_agent.py
from langchain import create_agent
from langchain_anthropic import ChatAnthropic
from langchain.tools import Tool

def create_polymarket_agent(client):
    """Crear agente de trading con LangChain"""
    
    # Definir herramientas disponibles
    tools = [
        Tool(
            name="get_market_price",
            description="Get current price for a token",
            func=lambda token_id: client.get_market_price(token_id)
        ),
        Tool(
            name="place_order",
            description="Place a trading order",
            func=lambda params: client.place_order(**params)
        ),
        # ... más tools
    ]
    
    # Crear agente con Claude
    agent = create_agent(
        model=ChatAnthropic(
            model="claude-sonnet-4-20250514",
            temperature=0
        ),
        tools=tools,
        system_prompt="You are a professional trading assistant..."
    )
    
    return agent
```

### Uso con LangGraph

```python
# agents/trading_graph.py
from langgraph.graph import StateGraph, END
from typing import TypedDict

class TradingState(TypedDict):
    market_data: dict
    signal: dict
    position: dict
    
def create_trading_workflow():
    """Crear workflow de trading con LangGraph"""
    
    workflow = StateGraph(TradingState)
    
    # Definir nodos
    workflow.add_node("analyze", analyze_market)
    workflow.add_node("decide", make_decision)
    workflow.add_node("execute", execute_trade)
    workflow.add_node("monitor", monitor_position)
    
    # Definir edges
    workflow.add_edge("analyze", "decide")
    workflow.add_conditional_edges(
        "decide",
        should_execute,
        {
            "execute": "execute",
            "skip": END
        }
    )
    workflow.add_edge("execute", "monitor")
    workflow.add_edge("monitor", END)
    
    workflow.set_entry_point("analyze")
    
    return workflow.compile()
```

## LangSmith para Observabilidad

LangSmith permite tracing y debugging de agentes:

```python
import os
from langsmith import Client

# Configurar en .env
os.environ["LANGCHAIN_TRACING_V2"] = "true"
os.environ["LANGCHAIN_API_KEY"] = "tu_api_key"
os.environ["LANGCHAIN_PROJECT"] = "polymarket-trading"

# Automáticamente hace tracing de todas las operaciones
```

## Ejemplos de Uso en Trading

### 1. Análisis de Sentimiento
```python
from langchain_anthropic import ChatAnthropic

llm = ChatAnthropic(model="claude-sonnet-4-20250514")

def analyze_market_sentiment(market_description: str):
    prompt = f"""
    Analiza el siguiente mercado de predicción y determina:
    1. Sentimiento general (bullish/bearish/neutral)
    2. Factores clave que afectan el resultado
    3. Nivel de certidumbre (0-100%)
    
    Mercado: {market_description}
    
    Responde en formato JSON.
    """
    return llm.invoke(prompt)
```

### 2. Generación de Estrategias
```python
def generate_trading_strategy(market_data: dict):
    prompt = f"""
    Dados los siguientes datos de mercado:
    {market_data}
    
    Genera una estrategia de trading que incluya:
    - Punto de entrada
    - Stop-loss
    - Take-profit
    - Tamaño de posición recomendado
    - Justificación de la estrategia
    """
    return llm.invoke(prompt)
```

### 3. Agent con Tools
```python
from langchain import create_agent

# Herramientas específicas de Polymarket
polymarket_tools = [
    Tool(
        name="get_markets",
        description="Get list of active prediction markets",
        func=client.get_markets
    ),
    Tool(
        name="analyze_odds",
        description="Analyze if odds are favorable for betting",
        func=analyze_odds
    ),
]

agent = create_agent(
    model=ChatAnthropic(model="claude-sonnet-4-20250514"),
    tools=polymarket_tools,
    system_prompt="""You are a prediction market expert.
    Analyze markets and suggest profitable trading opportunities."""
)

# Usar el agente
result = agent.invoke({
    "input": "Find the best trading opportunity in sports markets"
})
```

## Recursos Adicionales

- [LangChain Docs](https://docs.langchain.com/)
- [LangGraph Docs](https://docs.langchain.com/oss/python/langgraph/)
- [LangSmith](https://docs.langchain.com/langsmith/)
- [Anthropic Integration](https://docs.langchain.com/oss/python/langchain/anthropic/)

## Troubleshooting

### Error: "Python 3.10+ required"
```bash
# Verificar versión
python --version

# Actualizar Python si es necesario
sudo apt update
sudo apt install python3.10
```

### Error: "Module not found: langchain"
```bash
# Reinstalar con versión específica
pip install --upgrade langchain==0.3.0
```

### Error: "ImportError: cannot import name 'create_react_agent'"
```bash
# Actualizar a nuevo método
# Antiguo: from langgraph.prebuilt import create_react_agent
# Nuevo: from langchain import create_agent
```

## Notas de Migración

Si estás usando código antiguo de LangChain:

1. **Chains → Agents**: Migrar de chains a create_agent
2. **RetrievalQA → RAG**: Usar nuevas APIs de RAG
3. **Callbacks → Tracing**: Usar LangSmith para observabilidad

Para código legacy que no quieres migrar:
```bash
pip install langchain-classic
```

---

**Última actualización:** Enero 2025
