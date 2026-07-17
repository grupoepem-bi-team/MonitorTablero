#!/usr/bin/env bash
#
# first_auth.sh - Primera autenticacion de Azure AD en el servidor
#
# Se ejecuta EN EL SERVIDOR despues del deploy:
#   cd /opt/dashboardcontrol
#   bash deploy/first_auth.sh
#
# O remotamente desde la PC local:
#   REMOTE_USER=vm-hermes REMOTE_HOST=10.0.0.50 bash deploy/first_auth.sh --remote
#
# Variables configurables (con defaults):
#   REMOTE_USER   - usuario SSH (default: vm-hermes)
#   REMOTE_HOST   - IP/hostname  (default: 192.168.0.95)
#   REMOTE_DIR    - dir destino  (default: /opt/dashboardcontrol)
#   DASHBOARD_PORT- puerto       (default: 8070)

set -euo pipefail

REMOTE_USER="${REMOTE_USER:-vm-hermes}"
REMOTE_HOST="${REMOTE_HOST:-192.168.0.95}"
REMOTE_DIR="${REMOTE_DIR:-/opt/dashboardcontrol}"
DASHBOARD_PORT="${DASHBOARD_PORT:-8070}"

# Modo remoto: ejecutar via SSH en lugar de localmente
if [[ "${1:-}" == "--remote" ]]; then
    REMOTE="${REMOTE_USER}@${REMOTE_HOST}"
    echo "=== DashboardControl - Autenticacion remota ==="
    echo "Servidor: $REMOTE"
    echo
    echo "Se va a iniciar el device flow de Azure AD en el servidor."
    echo "Te va a mostrar una URL y un codigo."
    echo "Abri la URL en tu navegador y pega el codigo."
    echo
    ssh -t "$REMOTE" "cd $REMOTE_DIR && .venv/bin/python -m scripts.auth_step1"
    echo
    echo "Iniciando servicios..."
    ssh "$REMOTE" "sudo systemctl start dashboardcontrol-scheduler dashboardcontrol-frontend"
    echo
    echo "=== Todo listo ==="
    echo "Dashboard: http://${REMOTE_HOST}:${DASHBOARD_PORT}"
    echo "Logs:      ssh $REMOTE 'tail -f $REMOTE_DIR/logs/dashboardcontrol.log'"
    exit 0
fi

# Modo local (ejecutado directamente en el servidor)
echo "=== DashboardControl - Primera autenticacion ==="
echo
echo "Se va a iniciar el device flow de Azure AD."
echo "Te va a mostrar una URL y un codigo."
echo "Abri la URL en tu navegador y pega el codigo."
echo

cd "$REMOTE_DIR"
.venv/bin/python -m scripts.auth_step1

echo
echo "=== Autenticacion completada ==="
echo
echo "Iniciando servicios..."
sudo systemctl start dashboardcontrol-scheduler
sudo systemctl start dashboardcontrol-frontend

echo
echo "Verificando estado..."
sleep 3
systemctl status dashboardcontrol-scheduler --no-pager -l 2>&1 | head -10
echo
systemctl status dashboardcontrol-frontend --no-pager -l 2>&1 | head -10

echo
echo "=== Todo listo ==="
echo "Dashboard: http://localhost:${DASHBOARD_PORT}"
echo "Logs:      tail -f $REMOTE_DIR/logs/dashboardcontrol.log"