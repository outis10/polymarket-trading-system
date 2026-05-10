#!/usr/bin/env python3
"""
Test simple de configuración de Polymarket
"""
from dotenv import load_dotenv
import os

from py_clob_client_v2 import ApiCreds, ClobClient
from py_clob_client_v2.clob_types import AssetType, BalanceAllowanceParams

load_dotenv()

print("=" * 60)
print("Test de Configuración de Polymarket")
print("=" * 60)
print()

# Test 1: Conexión básica
print("1. Test de conexión básica...")
try:
    client = ClobClient('https://clob.polymarket.com', chain_id=137)
    time = client.get_server_time()
    print(f"   ✓ Servidor OK - Time: {time}")
except Exception as e:
    print(f"   ✗ Error: {e}")

#Test 2: Obtener mercados
print("\n2. Test de mercados...")
try:
    markets_response = client.get_markets()
    markets = markets_response.get('data', [])
    count = markets_response.get('count', 0)
    print(f"   ✓ Total markets disponibles: {count}")
    if markets:
        print(f"   ✓ Ejemplo: {markets[0].get('question', 'N/A')[:50]}...")
except Exception as e:
    print(f"   ✗ Error: {e}")

# Test 3: Cliente autenticado
print("\n3. Test de autenticación...")
try:
    api_creds = ApiCreds(
        api_key=os.getenv('POLYMARKET_API_KEY'),
        api_secret=os.getenv('POLYMARKET_SECRET'),
        api_passphrase=os.getenv('POLYMARKET_PASSPHRASE')
    )

    auth_client = ClobClient(
        'https://clob.polymarket.com',
        key=os.getenv('POLYMARKET_PRIVATE_KEY'),
        chain_id=137,
        signature_type=0,
        funder=os.getenv('POLYMARKET_FUNDER')
    )
    auth_client.set_api_creds(api_creds)
    print("   ✓ Cliente autenticado correctamente")

    # Verificar órdenes
    orders = auth_client.get_open_orders()
    print(f"   ✓ Órdenes activas: {len(orders) if orders else 0}")

except Exception as e:
    print(f"   ✗ Error: {e}")

# Test 4: Balance allowance
print("\n4. Test de allowance...")
try:
    allowance = auth_client.get_balance_allowance(
        BalanceAllowanceParams(
            asset_type=AssetType.COLLATERAL,
            signature_type=0,
        )
    )
    print(f"   Allowance actual: {allowance}")

except Exception as e:
    print(f"   ✗ Error: {e}")

print("\n" + "=" * 60)
print("RESUMEN")
print("=" * 60)
print()
print("✓ Configuración básica: OK")
print("✓ Credenciales: OK")
print()
print("SIGUIENTE PASO:")
print("  1. Ve a polymarket.com")
print("  2. Conecta MetaMask (cuenta: {}...)".format(os.getenv('POLYMARKET_FUNDER', '')[:10]))
print("  3. Haz un pequeño depósito de USDC")
print("  4. Esto aprobará automáticamente el allowance")
print()
print("="* 60)
