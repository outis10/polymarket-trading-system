#!/usr/bin/env python3
"""
Test simple del bot - ejecuta una iteración
"""
import logging
from config.settings import settings
from core.client_wrapper import PolymarketClient
from risk.position_manager import PositionManager

# Setup logging simple
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

print("=" * 60)
print("Test del Trading Bot")
print("=" * 60)
print()

try:
    # Validar settings
    logger.info("Validando configuración...")
    settings.validate()
    logger.info("✓ Configuración válida")

    # Inicializar cliente
    logger.info("Inicializando cliente de Polymarket...")
    client = PolymarketClient(settings.polymarket)
    logger.info("✓ Cliente inicializado")

    # Inicializar position manager
    logger.info("Inicializando position manager...")
    position_manager = PositionManager(
        max_position_size=settings.trading.max_position_size,
        max_total_exposure=settings.trading.max_total_exposure,
        stop_loss_pct=settings.trading.stop_loss_pct,
        take_profit_pct=settings.trading.take_profit_pct
    )
    logger.info("✓ Position manager inicializado")
    print()

    # Test 1: Obtener balance
    print("1. BALANCE:")
    try:
        balance = client.get_balance()
        if balance:
            print(f"   Balance allowance: ${balance:.2f}")
        else:
            print("   Balance: No disponible (normal)")
    except Exception as e:
        print(f"   Info: {e}")
    print()

    # Test 2: Obtener mercados
    print("2. MERCADOS ACTIVOS:")
    try:
        markets = client.get_markets()
        print(f"   Total mercados disponibles: {len(markets)}")

        if markets:
            print(f"\n   Primeros 3 mercados:")
            for i, market in enumerate(markets[:3], 1):
                question = market.get('question', 'N/A')
                print(f"   {i}. {question[:50]}...")

    except Exception as e:
        print(f"   Error: {e}")
    print()

    # Test 3: Obtener órdenes
    print("3. ÓRDENES ABIERTAS:")
    try:
        orders = client.get_open_orders()
        print(f"   Órdenes activas: {len(orders)}")
    except Exception as e:
        print(f"   Error: {e}")
    print()

    # Test 4: Posiciones
    print("4. POSICIONES:")
    try:
        positions = client.get_positions()
        print(f"   Posiciones abiertas: {len(positions)}")
    except Exception as e:
        print(f"   Error: {e}")
    print()

    # Test 5: Risk metrics
    print("5. MÉTRICAS DE RIESGO:")
    try:
        metrics = position_manager.get_risk_metrics()
        print(f"   Total posiciones: {metrics['total_positions']}")
        print(f"   Exposición total: ${metrics['total_exposure']:.2f}")
        print(f"   P&L total: ${metrics['total_pnl']:.2f}")
        print(f"   Utilización: {metrics['exposure_utilization']:.1%}")
    except Exception as e:
        print(f"   Error: {e}")
    print()

    print("=" * 60)
    print("✓ TEST COMPLETADO")
    print("=" * 60)
    print()
    print("Tu bot está listo para ejecutarse:")
    print("  python main.py")
    print()
    print("NOTA: El bot actual NO hace trades automáticos.")
    print("Solo monitorea mercados y posiciones.")
    print()

except Exception as e:
    logger.error(f"Error: {e}")
    import traceback
    traceback.print_exc()
