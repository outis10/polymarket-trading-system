# Guía Rápida - Configuración con MetaMask

Esta guía es para usuarios que conectaron MetaMask directamente a Polymarket.

## Paso 1: Exportar tu clave privada de MetaMask

1. Abre MetaMask
2. **Selecciona la cuenta que usas en Polymarket** (la que tiene fondos)
3. Click en los 3 puntos verticales (⋮) → "Detalles de la cuenta"
4. Click en "Exportar clave privada"
5. Ingresa tu contraseña de MetaMask
6. **Copia la clave privada**

### Sobre el prefijo "0x"

Si la clave privada NO empieza con `0x`, debes agregarlo manualmente:

```
# Si MetaMask te muestra:
abc123def456789...

# Debe quedar:
0xabc123def456789...
```

**IMPORTANTE**: La red seleccionada en MetaMask (Ethereum, Polygon, BSC) NO importa. La clave privada es la misma para todas las redes.

## Paso 2: Obtener tu dirección de wallet

1. En MetaMask, con la **misma cuenta** seleccionada
2. Click en el nombre de la cuenta para copiar la dirección
3. Debe verse como: `0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb`

## Paso 3: Generar credenciales

```bash
# Activar entorno virtual
source venv/bin/activate

# Ejecutar script de generación
python generate_credentials.py
```

Cuando el script pregunte:
- **¿Usar testnet?**: Responde `s` (sí) para empezar en testnet
- **Clave privada**: Pega tu clave privada (con el `0x`)
- **Dirección del wallet**: Pega tu dirección de MetaMask
- **Tipo de wallet**: Selecciona `0` (EOA/MetaMask)

El script mostrará las credenciales listas para copiar.

## Paso 4: Configurar el archivo .env

Copia las credenciales generadas al archivo `.env`:

```bash
cp .env.example .env
nano .env  # o usa tu editor favorito
```

Debe quedar algo así:

```env
# L1 Authentication
POLYMARKET_PRIVATE_KEY=0xabc123def456789...

# Configuración del wallet
POLYMARKET_FUNDER=0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb
POLYMARKET_SIGNATURE_TYPE=0  # 0 = MetaMask

# L2 Authentication
POLYMARKET_API_KEY=...
POLYMARKET_SECRET=...
POLYMARKET_PASSPHRASE=...

# Network
USE_TESTNET=true
CHAIN_ID=80002

# Trading configuration (puedes ajustar estos valores)
MAX_POSITION_SIZE=100.0
MAX_TOTAL_EXPOSURE=500.0
STOP_LOSS_PCT=0.05
TAKE_PROFIT_PCT=0.15
```

## Paso 5: Aprobar Allowances (OBLIGATORIO para MetaMask)

Este paso es **necesario solo para MetaMask** y se hace **una sola vez**:

```bash
python approve_allowances.py
```

Este script:
- Aprueba que los contratos de Polymarket puedan usar tus USDC
- Aprueba que los contratos puedan gestionar tus Conditional Tokens
- Se ejecuta en la blockchain (requiere un pequeño gas fee)

**NOTA**: Los usuarios de Magic/Email NO necesitan este paso.

## Paso 6: Probar la configuración

```bash
python test_setup.py
```

Si todo está correcto, deberías ver:
- ✓ Configuration valid
- ✓ Client initialized
- ✓ Connection successful
- ✓ All tests passed!

## Paso 7: Ejecutar el bot

```bash
python main.py
```

## Solución de Problemas

### "La clave privada debe empezar con 0x"
→ Agrega `0x` al inicio de tu clave privada

### "Invalid signature" o "Authentication failed"
→ Verifica que:
- La clave privada sea de la cuenta correcta (la que usas en Polymarket)
- Hayas copiado la clave completa (sin espacios al inicio/final)
- Hayas agregado el prefijo `0x`

### "Insufficient allowance"
→ Ejecuta `python approve_allowances.py`

### "No funds" o "Insufficient balance"
→ Deposita USDC en tu wallet de Polygon:
- Testnet: Usa el faucet de Polygon Amoy
- Mainnet: Transfiere USDC desde otro wallet o exchange

## Diferencias con Magic/Email

| Aspecto | MetaMask (signature_type=0) | Magic/Email (signature_type=1) |
|---------|----------------------------|--------------------------------|
| **Aprobar allowances** | ✗ Manual (approve_allowances.py) | ✓ Automático |
| **Exportar clave privada** | Desde MetaMask | Desde reveal.magic.link |
| **Complejidad** | Media | Baja |
| **Control** | Total (EOA) | Delegado (proxy) |

## Resumen de comandos

```bash
# 1. Generar credenciales
python generate_credentials.py

# 2. Configurar .env (copiar credenciales)
nano .env

# 3. Aprobar allowances (solo MetaMask)
python approve_allowances.py

# 4. Probar configuración
python test_setup.py

# 5. Ejecutar bot
python main.py
```

## Seguridad

- ⚠️ **NUNCA** compartas tu clave privada
- ⚠️ **NUNCA** commitees archivos con credenciales
- ⚠️ Siempre empieza en **TESTNET** primero
- ⚠️ Borra `generate_credentials.py` si tiene credenciales de mainnet
- ✓ Usa un wallet separado para trading automatizado
- ✓ Mantén un límite bajo de fondos en el wallet
