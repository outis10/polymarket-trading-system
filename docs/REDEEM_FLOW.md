# Redeem / Claim de posiciones resueltas

Guía para reclamar USDC de posiciones ganadoras en Polymarket.

---

## Arquitectura de wallets

```
POLYMARKET_PRIVATE_KEY  →  EOA  0xBe393157E0887bD27bfdfD19b2637E0aA32de258
                                  │
                                  │ owner (threshold=1)
                                  ▼
POLYMARKET_FUNDER       →  Safe  0x968add541570F3EbDFe2520e25FB884deEcB6649
                                  │
                                  │ msg.sender al hacer redeem
                                  ▼
                            CTF Contract (tokens residen aquí)
```

- El **Safe** (proxy Gnosis 1-of-1) es quien tiene los conditional tokens.
- El **EOA** es el firmante; paga el gas en POL.
- El redeem llama `execTransaction` en el Safe, que a su vez llama `redeemPositions` en el CTF.

---

## Requisitos

| Requisito | Valor |
|-----------|-------|
| POL en EOA para gas | ~0.01 POL por posición (~$0.001) |
| Variables de entorno | `POLYMARKET_PRIVATE_KEY`, `POLYMARKET_FUNDER`, `CHAIN_ID=137` |
| RPC estable | `https://rpc-mainnet.matic.quiknode.pro` (o configurar `POLYGON_RPC_URL` en `.env`) |

---

## Endpoints

### Ver posiciones reclamables

```bash
curl http://localhost:8000/api/claimable -H 'X-API-Key: <key>'
```

Respuesta de ejemplo:
```json
{
  "claimable_usd": 26.23,
  "wallet": "0x968add...",
  "positions": [
    {
      "condition_id": "0x0a497e...",
      "title": "Bitcoin Up or Down - March 1, 2:05AM-2:10AM ET",
      "outcome": "Up",
      "outcome_index": 0,
      "neg_risk": false,
      "size": 262.338,
      "value_usd": 26.2338
    }
  ]
}
```

### Ejecutar redeem on-chain

```bash
curl -X POST http://localhost:8000/api/redeem -H 'X-API-Key: <key>'
```

Respuesta de ejemplo:
```json
{
  "redeemed": [
    {
      "title": "Bitcoin Up or Down - March 1, 2:05AM-2:10AM ET",
      "condition_id": "0x0a497e...",
      "outcome": "Up",
      "value_usd": 26.2338,
      "tx_hash": "0x3ab033...",
      "status": "sent"
    }
  ],
  "summary": {
    "sent": 1,
    "failed": 0,
    "skipped": 0,
    "total_usd_sent": 26.2338
  }
}
```

Verifica la tx en: `https://polygonscan.com/tx/<tx_hash>`

---

## Flujo interno (`backend/routers/trading.py`)

1. `GET /api/claimable` → `_fetch_claimable_sync(wallet)`
   - Consulta `data-api.polymarket.com/positions?user=<funder>`
   - Filtra por `redeemable=true` y `currentValue > 0`
   - Cachea 5 min

2. `POST /api/redeem` → `_redeem_positions_sync(private_key, wallet, chain_id, positions)`
   - Detecta si `wallet` tiene bytecode → `is_safe=True`
   - Para cada posición:
     - Codifica calldata de `redeemPositions(collateral, parentCollectionId, conditionId, indexSets)`
     - Llama `_gnosis_exec_transaction(...)` que:
       1. Obtiene el nonce actual del Safe
       2. Construye el hash EIP-712 (domain separator + SafeTx hash)
       3. Firma con EOA via `eth_keys` (ECDSA raw, v = recovery_id + 27)
       4. Envía `execTransaction` desde EOA → Safe → CTF
   - Invalida el cache de `/claimable`

### Contratos (Polygon Mainnet)

| Contrato | Dirección |
|----------|-----------|
| CTF (Conditional Token Framework) | `0x4D97DCd97eC945f40cF65F87097ACe5EA0476045` |
| USDC (collateral) | `0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174` |

### indexSets por outcomeIndex

```
outcomeIndex=0 (Yes/Up/primera opción)  →  indexSets=[1]
outcomeIndex=1 (No/Down/segunda opción) →  indexSets=[2]
```

---

## Cómo conseguir POL para gas

La EOA necesita POL en Polygon Mainnet para pagar el gas.

1. **Desde un exchange** (Binance, Kraken, OKX):
   - Retirar POL → red Polygon → dirección EOA (`0xBe393157...`)
   - Con 0.1 POL (~$0.01) tienes para decenas de redeems

2. **Desde MetaMask** (si la EOA es tu wallet de MetaMask):
   - La misma wallet donde tienes USDC en Polygon necesita tener POL

---

## Automatización futura (Phase 2)

Para ejecutar el redeem automáticamente cuando hay posiciones listas,
agregar un job en PM2 o cron que llame al endpoint periódicamente:

```bash
# Ejemplo cron (cada hora)
0 * * * * curl -s -X POST http://localhost:8000/api/redeem \
  -H 'X-API-Key: <key>' >> /var/log/redeem.log 2>&1
```
