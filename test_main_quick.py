#!/usr/bin/env python3
"""
Test rápido del bot actualizado con Gamma API
"""
import logging
from main import TradingBot

# Setup logging simple
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

print("=" * 70)
print("TEST: Bot actualizado con Gamma API")
print("=" * 70)
print()

try:
    # Crear bot
    print("1. Inicializando bot...")
    bot = TradingBot()
    print("   ✓ Bot inicializado")
    print()

    # Probar scan_markets
    print("2. Ejecutando scan_markets() con Gamma API...")
    print("-" * 70)
    bot.scan_markets()
    print("-" * 70)
    print()

    # Mostrar status
    print("3. Mostrando status...")
    print("-" * 70)
    bot.display_status()
    print("-" * 70)
    print()

    print("=" * 70)
    print("✓ TEST COMPLETADO")
    print("=" * 70)
    print()
    print("El bot ahora:")
    print("  • Usa Gamma API para obtener mercados activos")
    print("  • Analiza oportunidades (precio bajo, alta confianza)")
    print("  • Solo hace LOGGING (no ejecuta trades)")
    print()
    print("Para ejecutar el bot completo:")
    print("  python main.py")
    print()

except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
