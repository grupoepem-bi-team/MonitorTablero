# ==========================================================================
# Dockerfile - Monitor de Tableros Power BI
# Multi-stage: builder instala deps, imagen final solo copia lo necesario.
# ==========================================================================

FROM --platform=$BUILDPLATFORM python:3.12-slim AS builder

WORKDIR /app

# Instalar dependencias (cache separado del codigo)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# --- Stage final ---
FROM python:3.12-slim

LABEL maintainer="BI Team"
LABEL description="Monitor de Tableros Power BI"

WORKDIR /app

# Instalar tzdata para que TZ=America/Argentina/Buenos_Aires funcione
RUN apt-get update && apt-get install -y --no-install-recommends tzdata && rm -rf /var/lib/apt/lists/*

# Copiar paquetes instalados del builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copiar el codigo de la app (src/ y frontend/)
COPY src/ ./src/
COPY frontend/ ./frontend/
COPY config_tableros.csv .

# .env, token_cache.bin y los JSON de estado se montan como volumenes
# en docker-compose.yml para persistir entre reinicios.
# config.py raisea si no encuentra AZURE_CLIENT_ID, por lo que .env
# es obligatorio en runtime (se monta como volumen RO).

EXPOSE 8070

# Healthcheck: verifica que el servidor responde
HEALTHCHECK --interval=30s --timeout=5s --retries=3 --start-period=15s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8070/api/todos', timeout=3)" || exit 1

# Comando: levantar el servidor web
CMD ["uvicorn", "frontend.server:app", "--host", "0.0.0.0", "--port", "8070"]