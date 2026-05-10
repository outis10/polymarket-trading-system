#!/usr/bin/env python3
"""
Script para aprobar allowances en Polymarket (solo para MetaMask/EOA)
Este paso es necesario ANTES de poder hacer trading con signature_type=0
"""
import sys
from dotenv import load_dotenv
import os

from py_clob_client_v2 import ClobClient
from py_clob_client_v2.clob_types import AssetType, BalanceAllowanceParams

# Cargar variables de entorno
load_dotenv()


def main():
    print("=" * 60)
    print("Aprobación de Allowances para Polymarket")
    print("=" * 60)
    print()

    # Verificar que es MetaMask
    signature_type = int(os.getenv('POLYMARKET_SIGNATURE_TYPE', '0'))

    if signature_type != 0:
        print("⚠️  Este script es solo para usuarios de MetaMask (signature_type=0)")
        print(f"   Tu configuración actual es signature_type={signature_type}")
        print()
        if signature_type == 1:
            print("Los usuarios de Magic/Email NO necesitan aprobar allowances.")
            print("Puedes proceder directamente a usar el bot.")
        sys.exit(0)

    print("Este script aprobará allowances para:")
    print("  • USDC (para depositar y tradear)")
    print("  • Conditional Tokens (para gestionar posiciones)")
    print()
    print("⚠️  IMPORTANTE:")
    print("  • Esto enviará transacciones a la blockchain")
    print("  • Necesitarás pagar gas fees (muy bajo en Polygon)")
    print("  • Solo necesitas hacer esto UNA VEZ")
    print()

    confirm = input("¿Continuar? (s/n) [s]: ").strip().lower()
    if confirm == 'n':
        print("Operación cancelada.")
        sys.exit(0)

    print()
    print("-" * 60)

    # Obtener configuración
    private_key = os.getenv('POLYMARKET_PRIVATE_KEY')
    use_testnet = os.getenv('USE_TESTNET', 'true').lower() == 'true'
    chain_id = int(os.getenv('CHAIN_ID', '80002' if use_testnet else '137'))

    if not private_key:
        print("❌ Error: POLYMARKET_PRIVATE_KEY no está configurada en .env")
        sys.exit(1)

    # Configurar host
    if use_testnet:
        host = "https://clob-testnet.polymarket.com"
        network_name = "TESTNET (Polygon Amoy)"
    else:
        host = "https://clob.polymarket.com"
        network_name = "MAINNET (Polygon)"

    print(f"Red: {network_name} (chain_id={chain_id})")
    print(f"Host: {host}")
    print()

    try:
        print("Inicializando cliente...")
        client = ClobClient(
            host,
            key=private_key,
            chain_id=chain_id,
            signature_type=0
        )
        print("✓ Cliente inicializado")
        print()

        coll_params = BalanceAllowanceParams(
            asset_type=AssetType.COLLATERAL,
            signature_type=0,
        )

        # Verificar allowance actual
        print("Verificando allowance actual...")
        try:
            allowance = client.get_balance_allowance(coll_params)
            print(f"  Collateral allowance actual: {allowance}")
            print()
        except Exception as e:
            print(f"  No se pudo verificar el allowance actual: {e}")
            print()

        # Aprobar allowances
        print("Aprobando allowances...")
        print("⏳ Esto puede tardar unos segundos (esperando confirmación en blockchain)...")
        print()

        client.update_balance_allowance(coll_params)

        print("✓ Allowances aprobados exitosamente!")
        print()

        # Verificar nuevamente
        print("Verificando allowance final...")
        try:
            allowance = client.get_balance_allowance(coll_params)
            print(f"  ✓ Collateral allowance: {allowance}")
            print()
        except Exception as e:
            print(f"  Advertencia: No se pudo verificar el allowance: {e}")
            print()

        print("=" * 60)
        print("✓ PROCESO COMPLETADO")
        print("=" * 60)
        print()
        print("Ya puedes usar el bot de trading:")
        print("  python main.py")
        print()

    except Exception as e:
        print()
        print("=" * 60)
        print("❌ ERROR")
        print("=" * 60)
        print(f"Error al aprobar allowances: {e}")
        print()
        print("Posibles causas:")
        print("  • No tienes fondos suficientes para gas fees")
        print("  • La clave privada es incorrecta")
        print("  • Problemas de conectividad con Polygon")
        print()
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Operación cancelada por el usuario")
        sys.exit(0)
