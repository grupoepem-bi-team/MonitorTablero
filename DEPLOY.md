# Deploy con Docker

## Requisitos

- Docker 24+ con Docker Compose v2+
- `.env` configurado con `AZURE_CLIENT_ID` (obligatorio, sin fallback)
- `token_cache.bin` generado previamente (device flow interactivo)
- `config_tableros.csv` presente

## Deploy rapido

```bash
# 1. Asegurar .env y token_cache.bin
cp .env.example .env
# Editar .env con AZURE_CLIENT_ID
# Hacer login previo (device flow, fuera de Docker):
.venv/bin/python -m scripts.auth_step1
#   o en Windows:
.venv\Scripts\python.exe -m scripts.auth_step1

# 2. Levantar ambos servicios (frontend + scheduler)
docker compose up -d --build

# 3. Verificar
curl http://localhost:8070/api/todos | python -m json.tool

# 4. Ver logs
docker compose logs -f
```

## Servicios

| Servicio | Container | Funcion | Puerto |
|----------|-----------|---------|--------|
| `frontend` | `dashboardcontrol-frontend` | FastAPI + uvicorn (dashboard web + API) | `8070:8070` |
| `scheduler` | `dashboardcontrol-scheduler` | Worker cada 30 min (configurable) | - |

El `frontend` depende del `scheduler` (`depends_on`), por lo que el scheduler arranca primero.

## Volumenes

| Archivo | Tipo | Por que |
|---------|------|---------|
| `.env` | RO | Credenciales Azure AD + config (no se incluye en la imagen) |
| `token_cache.bin` | RW | Token MSAL, se actualiza al refrescar |
| `estado_actual.json` | RW | Snapshot de tableros (lo lee el frontend) |
| `estado_tableros_snapshot.json` | RW | Snapshot anterior para diff |
| `cambios_recientes.json` | RW | Transiciones detectadas |
| `corrida_monitor_meta.json` | RW | Metadata de ultima corrida |
| `historico_corridas.jsonl` | RW | Historico append-only |
| `config_tableros.csv` | RO | Config de tableros (no se modifica) |
| `logs/` | RW | Logs del worker (compartido entre servicios) |

## Comandos utiles

```bash
# Ver estado
docker compose ps

# Reiniciar
docker compose restart

# Actualizar codigo (rebuild)
docker compose up -d --build

# Detener
docker compose down

# Ver logs de un servicio
docker compose logs -f frontend
docker compose logs -f scheduler

# Ejecutar worker manualmente dentro del container
docker compose exec scheduler python -m src.worker

# Hacer login (device flow) dentro del container
docker compose exec scheduler python -m scripts.auth_step1
```

## Configuracion

### Puerto
El puerto se define en `Dockerfile` (`EXPOSE 8070`) y `docker-compose.yml` (`ports: "8070:8070"`).
Para cambiarlo, editar ambos archivos o usar variable:

```yaml
ports:
  - "${DASHBOARD_PORT:-8070}:8070"
```

### Intervalo del scheduler
Por defecto 30 min. Cambiar en `.env`:
```
SCHEDULER_INTERVAL_MIN=15
```

### Timeout de corrida manual
Por defecto 900s (15 min). Cambiar en `.env`:
```
MONITOR_MANUAL_TIMEOUT_SEC=600
```

## Notas

- El `.env` **no** se incluye en la imagen Docker (se monta como volumen RO)
- El `token_cache.bin` debe existir antes del primer deploy (login interactivo fuera de Docker)
- Si el token expira: `docker compose exec scheduler python -m scripts.auth_step1`
- El healthcheck del frontend verifica `/api/todos` cada 30s
- `restart: unless-stopped` reinicia los containers si crashean
- Build multi-stage: builder instala dependencias, imagen final solo copia lo necesario
- `.dockerignore` excluye `_legacy/`, `deploy/`, `scripts/`, `tests/`, `*.md`, JSONs de estado, logs, etc.

## Build multi-arquitectura (opcional)

```bash
# Build para ambas arquitecturas
docker buildx build --platform linux/amd64,linux/arm64 -t dashboardcontrol .

# Push a registry (ejemplo)
docker buildx build --platform linux/amd64,linux/arm64 -t registry/dashboardcontrol:latest --push .
```

---

## Alternativa: Deploy con systemd (sin Docker)

Ver `deploy/deploy.sh` y `deploy/first_auth.sh` para deploy directo a servidor Linux via rsync+SSH+systemd.