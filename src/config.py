"""
config.py - Configuracion central del proyecto.

Lee variables de entorno desde .env y define todas las constantes y rutas
que el resto de los modulos necesita. Es el unico lugar donde se configuran
parametros globales: si algo cambia, se cambia aca o en .env, no en el codigo.
"""
from __future__ import annotations

import os

# ---------------------------------------------------------------------------
# Rutas base
# ---------------------------------------------------------------------------

_ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
"""Directorio raiz del proyecto (un nivel arriba de src/)."""

# Carga .env si python-dotenv esta instalado (opcional, no rompe si falta).
try:
    from dotenv import load_dotenv

    load_dotenv(os.path.join(_ROOT_DIR, ".env"))
except ImportError:
    pass

CONFIG_TABLEROS_CSV = os.path.join(_ROOT_DIR, "config_tableros.csv")
"""CSV con la lista de tableros a monitorear."""

CACHE_FILE = os.path.join(_ROOT_DIR, "token_cache.bin")
"""Cache serializado de MSAL con el token de Azure AD."""

ESTADO_ACTUAL_JSON = os.path.join(_ROOT_DIR, "estado_actual.json")
"""Snapshot actual de todos los tableros (lo lee el frontend)."""

SNAPSHOT_ESTADOS_JSON = os.path.join(_ROOT_DIR, "estado_tableros_snapshot.json")
"""Estado anterior para detectar cambios entre corridas."""

CAMBIOS_RECIENTES_JSON = os.path.join(_ROOT_DIR, "cambios_recientes.json")
"""Transiciones de estado detectadas en la ultima corrida (lo lee el frontend)."""

CORRIDA_MONITOR_META_JSON = os.path.join(_ROOT_DIR, "corrida_monitor_meta.json")
"""Metadata de la ultima corrida: duracion, exito, error, cantidades."""

HISTORICO_CORRIDAS_JSONL = os.path.join(_ROOT_DIR, "historico_corridas.jsonl")
"""Historico de corridas: una linea JSON por corrida (append-only)."""


# ---------------------------------------------------------------------------
# Autenticacion Azure AD / Power BI
# ---------------------------------------------------------------------------

CLIENT_ID = os.environ.get("AZURE_CLIENT_ID", "").strip()
"""ID de la app registrada en Azure Entra ID. Se configura en .env."""

if not CLIENT_ID:
    raise RuntimeError(
        "AZURE_CLIENT_ID no esta definido. "
        "Configuralo en .env (ver .env.example). "
        "El fallback hardcodeado fue removido por seguridad (app vieja con permisos excesivos)."
    )

AUTHORITY = "https://login.microsoftonline.com/655b856c-39c2-4438-9d98-b375b84019a9"
"""Endpoint de Azure AD para el flujo de dispositivo (tenant GRUPOIDEM)."""

SCOPES = ["https://analysis.windows.net/powerbi/api/.default"]
"""Permisos solicitados al token. .default = todos los consentidos en Azure."""


# ---------------------------------------------------------------------------
# Parametros de consulta a Power BI
# ---------------------------------------------------------------------------

MAX_WORKERS_POWERBI = 12
"""Maximo de hilos concurrentes para consultar tableros en paralelo."""

POWERBI_API_TIMEOUT_S = 30
"""Timeout en segundos para cada consulta DAX a la API de Power BI."""


# ---------------------------------------------------------------------------
# Umbrales de estado por defecto
# ---------------------------------------------------------------------------
# Estos valores se usan como fallback si el CSV no define umbrales por tablero.
# Las columnas frecuencia_objetivo_min y demorado_min del CSV tienen prioridad.

RETASO_OK_MAX_MIN = 60
"""Retraso en minutos hasta el cual el tablero esta OK (fallback)."""

RETASO_ADVERTENCIA_MAX_MIN = 80
"""Retraso en minutos hasta el cual el tablero esta en Advertencia (fallback)."""


# ---------------------------------------------------------------------------
# Ordenamiento y etiquetas de estado
# ---------------------------------------------------------------------------

ORDEN_ESTADO = {"Error": 0, "Demorado": 1, "Advertencia": 2, "OK": 3}
"""Orden de prioridad para mostrar tableros: Error primero, OK al final."""

ESTADOS_PROBLEMA = ("Error", "Demorado", "Advertencia")
"""Estados que indican que un tablero tiene un problema."""

LABEL_ESTADO = {
    "OK": "OK",
    "Advertencia": "Advertencia",
    "Demorado": "Demorado",
    "Error": "Error",
}
"""Etiquetas legibles para mostrar en la UI."""


# ---------------------------------------------------------------------------
# Helpers de entorno
# ---------------------------------------------------------------------------


def env_int(nombre: str, default: int) -> int:
    """Lee un entero desde una variable de entorno con fallback."""
    v = os.environ.get(nombre)
    if v is None or str(v).strip() == "":
        return default
    try:
        return int(str(v).strip())
    except ValueError:
        return default


# ---------------------------------------------------------------------------
# Timeout para corrida manual desde el frontend
# ---------------------------------------------------------------------------

MONITOR_MANUAL_TIMEOUT_S = env_int("MONITOR_MANUAL_TIMEOUT_SEC", 900)
"""Segundos maximos al ejecutar el worker desde el boton 'Actualizar ahora'."""

HISTORICO_MAX_CORRIDAS = env_int("HISTORICO_MAX_CORRIDAS", 1008)
"""Maximo de corridas a guardar en historico (default: 7 dias x 144 corridas/30min)."""