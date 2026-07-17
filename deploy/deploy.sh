#!/usr/bin/env bash
#
# deploy.sh - Deploy de DashboardControl al servidor Linux via SSH+rsync
#
# Uso basico (usa defaults del server actual):
#   bash deploy/deploy.sh
#
# Deploy a otro server (sobreescribir variables via entorno):
#   REMOTE_USER=deploy REMOTE_HOST=10.0.0.50 REMOTE_DIR=/opt/dashboardcontrol \
#       bash deploy/deploy.sh
#
# Variables configurables (con defaults):
#   REMOTE_USER   - usuario SSH en el servidor  (default: vm-hermes)
#   REMOTE_HOST   - IP o hostname del servidor   (default: 192.168.0.95)
#   REMOTE_DIR    - directorio de instalacion    (default: /opt/dashboardcontrol)
#   DASHBOARD_PORT- puerto del frontend          (default: 8070)
#   PYTHON        - binario de python en server  (default: python3)
#
# Este script:
#   1. Crea el directorio remoto
#   2. Copia los archivos del proyecto (sin .venv, logs, JSONs de estado, _legacy)
#   3. Crea/recrea el venv e instala dependencias
#   4. Registra los servicios de systemd con el puerto y rutas correctas
#   5. Habilita los servicios
#   6. Verifica
#
# NOTA: El token_cache.bin NO se copia. Hay que autenticarse en el servidor
#       con el device flow la primera vez (ver deploy/first_auth.sh).

set -euo pipefail

# --- Configuracion (sobreescribible via entorno) ---
REMOTE_USER="${REMOTE_USER:-vm-hermes}"
REMOTE_HOST="${REMOTE_HOST:-192.168.0.95}"
REMOTE_DIR="${REMOTE_DIR:-/opt/dashboardcontrol}"
DASHBOARD_PORT="${DASHBOARD_PORT:-8070}"
PYTHON="${PYTHON:-python3}"

REMOTE="${REMOTE_USER}@${REMOTE_HOST}"

echo "=== DashboardControl - Deploy al servidor ==="
echo "Destino:    $REMOTE:$REMOTE_DIR"
echo "Puerto:     $DASHBOARD_PORT"
echo "Python:     $PYTHON"
echo

# Validar que tenemos conectividad SSH
echo "[0/6] Verificando conectividad SSH..."
if ! ssh -o BatchMode=yes -o ConnectTimeout=5 "$REMOTE" "true" 2>/dev/null; then
    echo "ERROR: No se puede conectar via SSH a $REMOTE"
    echo "       Verifica que la clave SSH este configurada o que tengas acceso."
    exit 1
fi
echo "SSH OK."
echo

# 1. Crear directorio remoto
echo "[1/6] Creando directorio remoto..."
ssh "$REMOTE" "sudo mkdir -p $REMOTE_DIR && sudo chown $REMOTE_USER:$REMOTE_USER $REMOTE_DIR"

# 2. Copiar archivos del proyecto
echo "[2/6] Copiando archivos del proyecto..."
rsync -avz --delete \
    --exclude='.venv/' \
    --exclude='logs/' \
    --exclude='__pycache__/' \
    --exclude='*.pyc' \
    --exclude='_legacy/' \
    --exclude='.pytest_cache/' \
    --exclude='token_cache.bin' \
    --exclude='estado_actual.json' \
    --exclude='estado_tableros_snapshot.json' \
    --exclude='cambios_recientes.json' \
    --exclude='corrida_monitor_meta.json' \
    --exclude='ntfy_push_pref.json' \
    --exclude='mobile_push_tokens.json' \
    --exclude='device_flow_info.txt' \
    --exclude='.git/' \
    --exclude='ngrok.yml' \
    ./ "$REMOTE:$REMOTE_DIR/"

# 3. Crear venv (limpio) e instalar dependencias
echo "[3/6] Creando venv e instalando dependencias..."
ssh "$REMOTE" "cd $REMOTE_DIR && \
    $PYTHON -m venv --clear .venv && \
    .venv/bin/pip install --upgrade pip && \
    .venv/bin/pip install -r requirements.txt"

# 4. Generar e instalar servicios de systemd con parametros correctos
echo "[4/6] Instalando servicios de systemd..."
# Sustituir variables en los .service con los valores de este deploy
ssh "$REMOTE" "cd $REMOTE_DIR/deploy && \
    sed 's|/opt/dashboardcontrol|${REMOTE_DIR}|g; s|--port 8070|--port ${DASHBOARD_PORT}|g; s|User=vm-hermes|User=${REMOTE_USER}|g' \
        dashboardcontrol-frontend.service > /tmp/dc-frontend.service && \
    sed 's|/opt/dashboardcontrol|${REMOTE_DIR}|g; s|User=vm-hermes|User=${REMOTE_USER}|g' \
        dashboardcontrol-scheduler.service > /tmp/dc-scheduler.service && \
    sudo cp /tmp/dc-frontend.service /etc/systemd/system/ && \
    sudo cp /tmp/dc-scheduler.service /etc/systemd/system/ && \
    rm /tmp/dc-frontend.service /tmp/dc-scheduler.service && \
    sudo systemctl daemon-reload"

# 5. Habilitar servicios (no iniciar todavia: falta auth)
echo "[5/6] Habilitando servicios..."
ssh "$REMOTE" "sudo systemctl enable dashboardcontrol-scheduler dashboardcontrol-frontend"

# 6. Verificar
echo "[6/6] Verificando..."
ssh "$REMOTE" "echo 'Python:' && $PYTHON --version && \
    echo 'venv:' && $REMOTE_DIR/.venv/bin/python --version && \
    echo 'Dependencias:' && $REMOTE_DIR/.venv/bin/pip list --format=columns | head -20"

echo
echo "=== Deploy completado ==="
echo
echo "PROXIMO PASO: Autenticar en el servidor con el device flow."
echo "Ejecutar en el servidor (o via SSH):"
echo "  ssh $REMOTE"
echo "  cd $REMOTE_DIR"
echo "  .venv/bin/python -m scripts.auth_step1"
echo
echo "Despues de autenticar, iniciar los servicios:"
echo "  sudo systemctl start dashboardcontrol-scheduler dashboardcontrol-frontend"
echo
echo "Dashboard: http://${REMOTE_HOST}:${DASHBOARD_PORT}"
echo "Logs:      ssh $REMOTE 'tail -f $REMOTE_DIR/logs/dashboardcontrol.log'"