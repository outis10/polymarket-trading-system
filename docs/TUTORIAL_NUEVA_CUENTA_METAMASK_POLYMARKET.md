# Tutorial: Nueva Cuenta MetaMask + Polymarket (para este proyecto)

Guia practica para crear una cuenta nueva y dejarla operativa con este repo.

## 0) Objetivo

Al terminar, debes tener:

- Cuenta nueva de MetaMask.
- Cuenta nueva en Polymarket conectada a esa wallet.
- Credenciales API (L2) configuradas en `.env`.
- Allowances aprobados (si corresponde).
- Backend respondiendo `GET /api/balance` sin error.

---

## 1) Crear una wallet nueva en MetaMask

1. Abre MetaMask.
2. Crea una cuenta/wallet nueva (idealmente en un perfil de navegador separado).
3. Guarda la seed phrase offline.
4. Exporta la private key de esa cuenta (la usaras para el bot).

Notas:

- La private key es la misma para todas las redes.
- Si MetaMask la muestra sin `0x`, agrega `0x` manualmente.

---

## 2) Crear cuenta nueva en Polymarket con esa wallet

1. Entra a https://polymarket.com.
2. Conecta la wallet nueva (MetaMask).
3. Completa onboarding basico.
4. En Settings copia la direccion de wallet/funder.

---

## 3) Fondear la wallet (USDC en Polygon)

Necesitas USDC en Polygon para operar.

Opciones tipicas:

- Comprar/enviar USDC desde exchange a red Polygon.
- Bridge desde otra red a Polygon.

Verifica antes de seguir:

- Tienes saldo USDC en la wallet nueva.
- Tienes un poco de MATIC para gas.

---

## 4) Configurar credenciales en el proyecto

Desde la raiz del repo:

```bash
cd /home/desarrollo/dev/proyectos/polymarket-trading-system
source venv/bin/activate
```

Genera/deriva credenciales:

```bash
python generate_credentials.py
```

Completa `.env` con la wallet nueva:

```env
POLYMARKET_PRIVATE_KEY=0x...
POLYMARKET_FUNDER=0x...
POLYMARKET_SIGNATURE_TYPE=0
POLYMARKET_API_KEY=...
POLYMARKET_SECRET=...
POLYMARKET_PASSPHRASE=...
USE_TESTNET=false
CHAIN_ID=137
```

Si usas seguridad de este proyecto, tambien:

```env
API_KEY=...               # backend
ALLOWED_ORIGINS=http://localhost:5173
```

En `frontend/.env.local`:

```env
VITE_APP_PASSWORD=...
VITE_API_KEY=...          # misma API_KEY del backend
```

---

## 5) Aprobar allowances (MetaMask = signature_type=0)

Para MetaMask debes aprobar allowances una vez:

```bash
source venv/bin/activate
python approve_allowances_auto.py
```

Si falla, revisa:

- red correcta (Polygon mainnet),
- wallet/funder correcto,
- saldo y gas.

---

## 6) Levantar backend y validar

Inicia backend:

```bash
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

Prueba balance:

```bash
curl -H "X-API-Key: TU_API_KEY" http://localhost:8000/api/balance
```

Esperado:

- `balance` numerico > 0 (o al menos sin error de credenciales).

---

## 7) Validacion minima antes de operar

Checklist:

- `GET /api/balance` responde bien.
- `GET /api/events` responde bien.
- En UI se ve `Bankroll` correcto.
- Si usaras bot:
  - revisar `bot_paper_mode` antes de live,
  - validar caps (`bot_order_notional_cap_usd`, exposicion, cooldowns),
  - validar `kelly_min_edge_pct` y `quant_gate_*`.

---

## 8) Recomendacion de seguridad operativa

- No reutilices private key de cuenta principal.
- Usa cuenta dedicada por estrategia/bot.
- Nunca commitees `.env` ni `frontend/.env.local`.
- Rota API keys si sospechas exposicion.

---

## 9) Troubleshooting rapido

`/api/balance` da error:

- revisa L2 creds (`POLYMARKET_API_KEY/SECRET/PASSPHRASE`),
- revisa `POLYMARKET_FUNDER`,
- revisa red (`CHAIN_ID=137` para mainnet).

No deja tradear:

- faltan allowances,
- no hay USDC/MATIC,
- risk guards bloqueando (`order_blocked_log.csv`),
- `bot_paper_mode=true` (no ejecuta live real).

---

## 10) Comandos utiles

Validar estado de settings:

```bash
curl -H "X-API-Key: TU_API_KEY" http://localhost:8000/api/events
```

Reset logs paper:

```bash
bash scripts/reset_logs_for_paper.sh
```

---

Si quieres, en una siguiente iteracion te dejo una version corta tipo checklist de 2 minutos para onboarding rapido.

