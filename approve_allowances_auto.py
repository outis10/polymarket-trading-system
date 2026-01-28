#!/usr/bin/env python3
"""
Script para aprobar allowances en Polymarket (versión automática)
"""
from py_clob_client.client import ClobClient
import sys
from dotenv import load_dotenv
import os

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

    print("Este script aprobará el allowance para:")
    print("  • Permitir que Polymarket CLOB use tus tokens")
    print()
    print("⚠️  IMPORTANTE:")
    print("  • Esto enviará transacciones a la blockchain")
    print("  • Necesitarás pagar gas fees (muy bajo en Polygon)")
    print("  • Solo necesitas hacer esto UNA VEZ")
    print()
    print("-" * 60)

    # Obtener configuración
    private_key = os.getenv('POLYMARKET_PRIVATE_KEY')
    funder = os.getenv('POLYMARKET_FUNDER')
    use_testnet = os.getenv('USE_TESTNET', 'false').lower() == 'true'
    chain_id = int(os.getenv('CHAIN_ID', '137'))

    # API credentials
    api_key = os.getenv('POLYMARKET_API_KEY')
    api_secret = os.getenv('POLYMARKET_SECRET')
    api_passphrase = os.getenv('POLYMARKET_PASSPHRASE')

    if not private_key:
        print("❌ Error: POLYMARKET_PRIVATE_KEY no está configurada en .env")
        sys.exit(1)

    if not funder:
        print("❌ Error: POLYMARKET_FUNDER no está configurada en .env")
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
            signature_type=0,
            funder=funder
        )
        print("✓ Cliente inicializado")

        # Configurar API credentials si están disponibles
        if api_key and api_secret and api_passphrase:
            print("Configurando credenciales API...")
            from py_clob_client.clob_types import ApiCreds
            api_creds = ApiCreds(
                api_key=api_key,
                api_secret=api_secret,
                api_passphrase=api_passphrase
            )
            client.set_api_creds(api_creds)
            print("✓ Credenciales API configuradas")
        else:
            print("Derivando credenciales API...")
            api_creds = client.create_or_derive_api_creds()
            client.set_api_creds(api_creds)
            print("✓ Credenciales API derivadas")

        print()

        # Verificar allowances actuales
        print("Verificando allowances actuales...")
        try:
            allowance = client.get_balance_allowance()
            print(f"  Allowance actual: {allowance}")
            print()

            # Verificar si ya está aprobado (allowance > 0 significa aprobado)
            if allowance and int(allowance) > 0:
                print("✓ El allowance ya está aprobado!")
                print("  No es necesario aprobar nuevamente.")
                print()
                print("=" * 60)
                print("✓ LISTO PARA USAR")
                print("=" * 60)
                print()
                print("Puedes continuar con:")
                print("  python test_setup.py")
                print()
                sys.exit(0)

        except Exception as e:
            print(f"  Advertencia: No se pudo verificar allowance actual: {e}")
            print()

        # Aprobar allowances
        print("Aprobando allowance...")
        print("⏳ Esto puede tardar unos segundos (esperando confirmación en blockchain)...")
        print()

        result = client.update_balance_allowance()

        print(f"✓ Allowance aprobado exitosamente!")
        print(f"  Resultado: {result}")
        print()

        # Verificar nuevamente
        print("Verificando allowance final...")
        try:
            allowance = client.get_balance_allowance()
            print(f"  ✓ Allowance: {allowance}")
            print()
        except Exception as e:
            print(f"  Advertencia: No se pudo verificar allowance: {e}")
            print()

        print("=" * 60)
        print("✓ PROCESO COMPLETADO")
        print("=" * 60)
        print()
        print("Ya puedes usar el bot de trading:")
        print("  python test_setup.py")
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
        print("  • No tienes fondos suficientes para gas fees en Polygon")
        print("  • La clave privada es incorrecta")
        print("  • Problemas de conectividad con Polygon")
        print("  • Tu wallet no tiene MATIC para pagar gas")
        print()
        print("Para obtener MATIC en Polygon mainnet:")
        print("  • Compra en un exchange y transfiere a tu wallet")
        print("  • Usa un bridge desde Ethereum")
        print("  • Usa un faucet de Polygon (si existe)")
        print()
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Operación cancelada por el usuario")
        sys.exit(0)
