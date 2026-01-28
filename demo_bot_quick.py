#!/usr/bin/env python3
"""
Bot de demostración rápida - 1 iteración
"""
import logging
from datetime import datetime
from config.settings import settings
from core.client_wrapper import PolymarketClient
from risk.position_manager import PositionManager

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

print("""
╔═══════════════════════════════════════════╗
║   Polymarket Trading Bot - DEMO          ║
║   Modo: Observación (Sin Trading)        ║
╚═══════════════════════════════════════════╝
""")

try:
    # Inicializar componentes
    logger.info("Inicializando componentes...")
    settings.validate()

    client = PolymarketClient(settings.polymarket)
    position_manager = PositionManager(
        max_position_size=settings.trading.max_position_size,
        max_total_exposure=settings.trading.max_total_exposure,
        stop_loss_pct=settings.trading.stop_loss_pct,
        take_profit_pct=settings.trading.take_profit_pct
    )

    logger.info("✓ Bot inicializado correctamente")
    print()

    print("=" * 60)
    print(f"ITERACIÓN DE DEMO - {datetime.now().strftime('%H:%M:%S')}")
    print("=" * 60)
    print()

    # 1. Mostrar mercados
    print("📊 MERCADOS ACTIVOS:")
    try:
        markets = client.get_markets()
        print(f"   Total disponibles: {len(markets)}")

        if markets and len(markets) > 0:
            print(f"\n   Top 5 mercados más recientes:")
            for i, market in enumerate(markets[:5], 1):
                question = market.get('question', 'N/A')[:60]
                active = "✓" if market.get('active', False) else "✗"
                condition_id = market.get('condition_id', 'N/A')[:20]
                print(f"   {i}. [{active}] {question}...")
                print(f"      ID: {condition_id}...")
    except Exception as e:
        logger.error(f"Error obteniendo mercados: {e}")

    print()

    # 2. Mostrar órdenes activas
    print("📝 ÓRDENES ACTIVAS:")
    try:
        orders = client.get_open_orders()
        print(f"   Total órdenes: {len(orders)}")

        if orders and len(orders) > 0:
            for order in orders[:3]:
                print(f"   - ID: {order.get('id', 'N/A')[:20]}...")
                print(f"     Side: {order.get('side', 'N/A')}, Price: ${order.get('price', 'N/A')}")
        else:
            print("   ✓ Sin órdenes activas (normal para inicio)")
    except Exception as e:
        logger.error(f"Error obteniendo órdenes: {e}")

    print()

    # 3. Mostrar posiciones
    print("💼 POSICIONES:")
    try:
        positions = client.get_positions()
        print(f"   Posiciones abiertas: {len(positions)}")

        if positions and len(positions) > 0:
            for pos in positions[:3]:
                print(f"   - Token: {pos.get('token_id', 'N/A')[:20]}...")
                print(f"     Size: {pos.get('size', 'N/A')}")
        else:
            print("   ✓ Sin posiciones abiertas (normal para inicio)")
    except Exception as e:
        logger.error(f"Error obteniendo posiciones: {e}")

    print()

    # 4. Métricas de riesgo
    print("⚖️  MÉTRICAS DE RIESGO:")
    try:
        metrics = position_manager.get_risk_metrics()
        print(f"   Posiciones totales: {metrics['total_positions']}")
        print(f"   Exposición total: ${metrics['total_exposure']:.2f} / ${settings.trading.max_total_exposure:.2f}")
        print(f"   P&L total: ${metrics['total_pnl']:.2f}")
        print(f"   Utilización: {metrics['exposure_utilization']:.1%}")

        if metrics['total_exposure'] > 0:
            print(f"   ⚠️  Estás usando {metrics['exposure_utilization']:.1%} de tu límite de exposición")
        else:
            print(f"   ✓ Sin exposición actual (sin posiciones abiertas)")
    except Exception as e:
        logger.error(f"Error calculando métricas: {e}")

    print()

    # 5. Escaneo de oportunidades (placeholder)
    print("🔍 ANÁLISIS DE MERCADO:")
    print("   El bot está escaneando mercados...")
    print("   (Estrategia de trading NO implementada - solo monitoreo)")
    print()
    print("   Para implementar trading automático:")
    print("   → Edita main.py, función scan_markets() (línea 121-140)")
    print("   → Agrega tu lógica de estrategia")
    print("   → Las estrategias de ejemplo están en strategy/")

    print()
    print("=" * 60)
    print("✓ DEMO COMPLETADA")
    print("=" * 60)
    print()
    print("Este fue un ciclo completo del bot. En modo normal:")
    print()
    print("  • Se ejecuta continuamente cada 60 segundos")
    print("  • Monitorea mercados en tiempo real")
    print("  • Revisa tus posiciones")
    print("  • Aplica stop-loss y take-profit si tienes posiciones")
    print("  • Ejecuta tu estrategia de trading (cuando la implementes)")
    print()
    print("PRÓXIMOS PASOS:")
    print()
    print("1. Familiarízate con los ejemplos:")
    print("   python examples/01_explore_basics.py")
    print("   python examples/02_analyze_orderbook.py")
    print("   python examples/04_price_monitor.py")
    print()
    print("2. Ejecuta el bot completo (modo observación):")
    print("   python main.py")
    print("   (Detén con Ctrl+C)")
    print()
    print("3. Cuando estés listo, implementa tu estrategia:")
    print("   Edita main.py → función scan_markets()")
    print()

except KeyboardInterrupt:
    print("\n\n⚠️  Demo detenida por el usuario")
    print()

except Exception as e:
    logger.error(f"Error: {e}")
    import traceback
    traceback.print_exc()
