# Allowances — Documentación Técnica

## Resumen

Polymarket CLOB requiere dos tipos de allowances aprobados on-chain (Polygon) para operar:

| Tipo | Asset | Para qué sirve |
|------|-------|----------------|
| `COLLATERAL` | USDC | Permite al CLOB debitar USDC de tu wallet para comprar shares |
| `CONDITIONAL` | Token ERC-1155 (YES/NO) | Permite al CLOB mover shares desde tu wallet para venderlos |

Sin el allowance `CONDITIONAL`, los sells fallan con:
```
PolyApiException[status_code=400, error_message={'error': 'not enough balance / allowance'}]
```

---

## 1. Setup inicial (una sola vez)

### Approbar COLLATERAL (USDC)

```bash
python approve_allowances_auto.py
```

### Approbar CONDITIONAL para todos los tokens en historial de trades

Correr el siguiente script cuando aparezca el error de allowance en sells, o al configurar una cuenta nueva:

```bash
python3 -c "
from dotenv import load_dotenv
import os
load_dotenv()

from py_clob_client.client import ClobClient
from py_clob_client.clob_types import AssetType, BalanceAllowanceParams, ApiCreds

client = ClobClient(
    'https://clob.polymarket.com',
    key=os.getenv('POLYMARKET_PRIVATE_KEY'),
    chain_id=int(os.getenv('CHAIN_ID', '137')),
    signature_type=int(os.getenv('POLYMARKET_SIGNATURE_TYPE', '0')),
    funder=os.getenv('POLYMARKET_FUNDER'),
)
client.set_api_creds(ApiCreds(
    api_key=os.getenv('POLYMARKET_API_KEY'),
    api_secret=os.getenv('POLYMARKET_SECRET'),
    api_passphrase=os.getenv('POLYMARKET_PASSPHRASE'),
))

trades = client.get_trades()
token_ids = set(t.get('asset_id') for t in trades if t.get('side','').upper() == 'BUY')
print(f'Tokens a aprobar: {len(token_ids)}')
for tid in token_ids:
    r = client.update_balance_allowance(BalanceAllowanceParams(
        asset_type=AssetType.CONDITIONAL,
        token_id=tid,
        signature_type=int(os.getenv('POLYMARKET_SIGNATURE_TYPE', '0')),
    ))
    print(f'  OK: {str(tid)[:20]}...')
print('Listo.')
"
```

---

## 2. Allowance automático en sells (backend)

El backend (`backend/routers/trading.py`) ya llama a `update_balance_allowance` con `CONDITIONAL` automáticamente antes de cada sell:

```python
if is_sell:
    cond_params = BalanceAllowanceParams(
        asset_type=AssetType.CONDITIONAL,
        token_id=token_id,
        signature_type=client.config.signature_type,
    )
    client.client.update_balance_allowance(cond_params)
```

Esto cubre tokens nuevos comprados por el bot que aún no fueron aprobados manualmente.

---

## 3. Cuándo volver a correr el script manual

- Al crear una cuenta nueva o cambiar de wallet
- Si aparece de nuevo el error `not enough balance / allowance` en sells (puede pasar si hay tokens muy antiguos no cubiertos por el auto-approve)
- Nunca es necesario repetirlo para tokens ya aprobados — el allowance es permanente on-chain

---

## 4. Notas técnicas

- El allowance `CONDITIONAL` es por `token_id` específico (ERC-1155) — cada mercado YES/NO es un token diferente
- El allowance `COLLATERAL` es global para USDC
- Las transacciones de approve se confirman en Polygon (gas mínimo, ~$0.001)
- `signature_type=0` → MetaMask/EOA wallet
- `signature_type=1` → Magic/Email (no requiere approve manual)
