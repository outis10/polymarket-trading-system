#!/usr/bin/env python3
"""
Bot de demostración - Ejecuta por 5 minutos para familiarización
"""
import logging
import time
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

    # Ejecutar 5 iteraciones (5 minutos aprox)
    MAX_ITERATIONS = 5

    for iteration in range(1, MAX_ITERATIONS + 1):
        print("=" * 60)
        print(f"ITERACIÓN {iteration}/{MAX_ITERATIONS} - {datetime.now().strftime('%H:%M:%S')}")
        print("=" * 60)
        print()

        # 1. Mostrar mercados
        print("📊 MERCADOS ACTIVOS:")
        try:
            markets = client.get_markets()
            print(f"   Total disponibles: {len(markets)}")

            if markets:
                print(f"\n   Top 5 mercados más recientes:")
                for i, market in enumerate(markets[:5], 1):
                    question = market.get('question', 'N/A')[:60]
                    active = "✓" if market.get('active', False) else "✗"
                    print(f"   {i}. [{active}] {question}...")
        except Exception as e:
            logger.error(f"Error obteniendo mercados: {e}")

        print()

        # 2. Mostrar órdenes activas
        print("📝 ÓRDENES ACTIVAS:")
        try:
            orders = client.get_open_orders()
            print(f"   Total órdenes: {len(orders)}")

            if orders:
                for order in orders[:3]:
                    print(f"   - ID: {order.get('id', 'N/A')[:20]}...")
                    print(f"     Side: {order.get('side', 'N/A')}, Price: ${order.get('price', 'N/A')}")
            else:
                print("   (Sin órdenes activas)")
        except Exception as e:
            logger.error(f"Error obteniendo órdenes: {e}")

        print()

        # 3. Mostrar posiciones
        print("💼 POSICIONES:")
        try:
            positions = client.get_positions()
            print(f"   Posiciones abiertas: {len(positions)}")

            if positions:
                for pos in positions[:3]:
                    print(f"   - Token: {pos.get('token_id', 'N/A')[:20]}...")
                    print(f"     Size: {pos.get('size', 'N/A')}")
            else:
                print("   (Sin posiciones abiertas)")
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
        except Exception as e:
            logger.error(f"Error calculando métricas: {e}")

        print()

        # 5. Escaneo de oportunidades (placeholder)
        print("🔍 ESCANEO DE OPORTUNIDADES:")
        print("   (Estrategia no implementada - solo monitoreo)")
        print()

        # Esperar antes de la siguiente iteración
        if iteration < MAX_ITERATIONS:
            print(f"⏳ Esperando 60 segundos hasta próxima iteración...")
            print()
            time.sleep(60)

    print("=" * 60)
    print("DEMO COMPLETADA")
    print("=" * 60)
    print()
    print("Has visto cómo el bot:")
    print("  ✓ Monitorea mercados activos")
    print("  ✓ Revisa órdenes y posiciones")
    print("  ✓ Calcula métricas de riesgo")
    print("  ✓ Se ejecuta en ciclos cada 60 segundos")
    print()
    print("Para ejecutar el bot completo (continuamente):")
    print("  python main.py")
    print()
    print("Para detenerlo en cualquier momento: Ctrl+C")
    print()

except KeyboardInterrupt:
    print("\n\n⚠️  Demo detenida por el usuario")
    print()

except Exception as e:
    logger.error(f"Error: {e}")
    import traceback
    traceback.print_exc()
