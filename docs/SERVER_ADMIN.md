# Server Admin — EC2 Ubuntu

## Conexión

```bash
ssh -i tu-archivo.pem ubuntu@52.87.47.169
```

---

## Bot (polymarket-bot.service)

```bash
# Estado
sudo systemctl status polymarket-bot

# Iniciar
sudo systemctl start polymarket-bot

# Detener
sudo systemctl stop polymarket-bot

# Reiniciar
sudo systemctl restart polymarket-bot

# Logs en tiempo real
journalctl -u polymarket-bot -f

# Últimas 100 líneas
journalctl -u polymarket-bot -n 100

# Logs de hoy
journalctl -u polymarket-bot --since today

# Solo errores
journalctl -u polymarket-bot -p err
```

---

## Nginx

```bash
# Estado
sudo systemctl status nginx

# Reiniciar
sudo systemctl restart nginx

# Recargar config sin downtime
sudo systemctl reload nginx

# Validar config
sudo nginx -t

# Logs de acceso
sudo tail -f /var/log/nginx/access.log

# Logs de error
sudo tail -f /var/log/nginx/error.log
```

---

## Deploy — actualizar código

```bash
cd /home/ubuntu/app

# Bajar cambios
git pull

# Rebuildar frontend (solo si hubo cambios en frontend/)
cd frontend && npm run build && cd ..

# Reinstalar deps backend (solo si hubo cambios en requirements.txt)
source venv/bin/activate && pip install -r backend/requirements.txt

# Reiniciar bot
sudo systemctl restart polymarket-bot
```

---

## Variables de entorno

```bash
# Editar .env del backend
nano /home/ubuntu/app/.env

# Editar .env del frontend (requiere rebuild)
nano /home/ubuntu/app/frontend/.env
cd /home/ubuntu/app/frontend && npm run build

# Después de cambiar .env del backend
sudo systemctl restart polymarket-bot
```

---

## Recursos del servidor

```bash
# CPU y RAM en tiempo real
htop

# RAM disponible
free -h

# Disco
df -h

# Procesos escuchando puertos
sudo ss -tlnp

# Verificar que el bot escucha en 8000
sudo ss -tlnp | grep 8000
```

---

## Archivos importantes

| Archivo | Descripción |
|---|---|
| `/home/ubuntu/app/.env` | Variables de entorno del backend |
| `/home/ubuntu/app/frontend/.env` | Variables del frontend (pre-build) |
| `/home/ubuntu/app/frontend/dist/` | Frontend compilado (servido por Nginx) |
| `/home/ubuntu/app/backtest_output/` | CSVs de trades, bloqueos y analytics |
| `/home/ubuntu/app/config/runtime_settings.json` | Settings del bot en tiempo real |
| `/etc/nginx/sites-available/polymarket` | Config de Nginx |
| `/etc/systemd/system/polymarket-bot.service` | Config del servicio systemd |

---

## Quant pipeline (actualización diaria)

```bash
cd /home/ubuntu/app
source venv/bin/activate
bash scripts/update_quant.sh
```

O via API (sin reiniciar el bot):
```bash
curl -X POST http://127.0.0.1:8000/api/quant/reload \
  -H "X-API-Key: TU_API_KEY"
```

---

## Reset de logs para paper mode

```bash
cd /home/ubuntu/app
bash scripts/reset_logs_for_paper.sh
```

---

## Troubleshooting

### El bot no arranca
```bash
journalctl -u polymarket-bot -n 50
# Revisar errores en .env o dependencias faltantes
```

### Nginx 502 Bad Gateway
```bash
# El bot no está corriendo
sudo systemctl start polymarket-bot
```

### Nginx 403 Permission Denied
```bash
chmod 755 /home/ubuntu
chmod -R 755 /home/ubuntu/app/frontend/dist
sudo systemctl restart nginx
```

### Reiniciar todo
```bash
sudo systemctl restart polymarket-bot
sudo systemctl restart nginx
```
