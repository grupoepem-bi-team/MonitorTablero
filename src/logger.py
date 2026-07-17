"""
logger.py - Sistema de logging centralizado para DashboardControl.

Registra la salud del proyecto: corridas del worker, errores de consulta,
fallos de autenticacion, warnings y eventos del frontend.

Los logs se escriben a:
  - logs/dashboardcontrol.log  (rotativo, 5 MB x 5 archivos)
  - consola (si se ejecuta desde CLI)

Niveles:
  DEBUG   - detalle de cada tablero consultado
  INFO    - corridas exitosas, inicio/fin de procesos
  WARNING - tableros con estado no-OK, retrasos
  ERROR   - errores de consulta, fallos de auth
  CRITICAL - fallos que impiden que el sistema funcione

Uso desde cualquier modulo:
    from src.logger import get_logger
    log = get_logger(__name__)
    log.info("Corrida iniciada")
    log.error("Fallo consultando tablero X", extra={"tablero": "X"})
"""
from __future__ import annotations

import logging
import logging.handlers
import os
from datetime import datetime
from pathlib import Path

from src import config

_LOG_DIR = os.path.join(config._ROOT_DIR, "logs")
"""Directorio donde se guardan los archivos de log."""

_LOG_FILE = os.path.join(_LOG_DIR, "dashboardcontrol.log")
"""Archivo de log principal (rotativo)."""

_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s"
"""Formato de cada linea de log."""

_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
"""Formato de fecha en el log."""

_logger_configured = False
"""Flag para no reconfigurar el logger si ya fue configurado."""


def get_logger(name: str = __name__) -> logging.Logger:
    """
    Retorna un logger configurado con el nombre dado.

    La primera llamada configura el logger global (handlers, formato, nivel).
    Las llamadas subsiguientes solo retornan el logger con ese nombre.

    Args:
        name: Nombre del logger (usar __name__ desde cada modulo).

    Returns:
        logging.Logger: Logger listo para usar.
    """
    global _logger_configured

    logger = logging.getLogger(name)

    if not _logger_configured:
        _setup_root_logger()
        _logger_configured = True

    return logger


def _setup_root_logger() -> None:
    """Configura el logger raiz con file handler rotativo y console handler."""
    os.makedirs(_LOG_DIR, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    # Silenciar librerias externas que generan mucho ruido en DEBUG
    for noisy in ("urllib3", "msal", "requests", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    # File handler rotativo (5 MB x 5 archivos)
    file_handler = logging.handlers.RotatingFileHandler(
        _LOG_FILE,
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(_LOG_FORMAT, _DATE_FORMAT))

    # Console handler (solo INFO+ para no saturar la consola)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter(_LOG_FORMAT, _DATE_FORMAT))

    root.addHandler(file_handler)
    root.addHandler(console_handler)


def log_corrida_inicio(n_tableros: int) -> None:
    """
    Registra el inicio de una corrida del monitor.

    Args:
        n_tableros: Cantidad de tableros a consultar.
    """
    log = get_logger("worker")
    log.info("=== Corrida iniciada === tableros=%d", n_tableros)


def log_corrida_fin(
    n_tableros: int,
    n_ok: int,
    n_advertencia: int,
    n_demorado: int,
    n_error: int,
    duracion_s: float,
    n_cambios: int,
) -> None:
    """
    Registra el fin de una corrida con el resumen de salud.

    Args:
        n_tableros: Total consultado.
        n_ok: Tableros en OK.
        n_advertencia: Tableros en Advertencia.
        n_demorado: Tableros en Demorado.
        n_error: Tableros en Error.
        duracion_s: Duracion en segundos.
        n_cambios: Cambios de estado detectados.
    """
    log = get_logger("worker")
    log.info(
        "=== Corrida finalizada === "
        "total=%d OK=%d adv=%d dem=%d err=%d cambios=%d dur=%.1fs",
        n_tableros,
        n_ok,
        n_advertencia,
        n_demorado,
        n_error,
        n_cambios,
        duracion_s,
    )

    if n_error > 0:
        log.error(
            "%d tablero(s) en Error tras corrida",
            n_error,
        )
    elif n_demorado > 0:
        log.warning(
            "%d tablero(s) Demorado, %d Advertencia (sin errores)",
            n_demorado,
            n_advertencia,
        )


def log_tablero_error(tablero: str, error: str) -> None:
    """
    Registra el error de un tablero individual.

    Args:
        tablero: Nombre del tablero.
        error: Mensaje de error (truncado a 300 chars).
    """
    log = get_logger("powerbi")
    error_short = (error or "")[:300]
    log.error("Tablero '%s' -> Error: %s", tablero, error_short)


def log_tablero_estado(
    tablero: str,
    estado: str,
    retraso_min: float | None,
    critico: bool,
) -> None:
    """
    Registra el estado de un tablero tras consulta exitosa.

    Args:
        tablero: Nombre del tablero.
        estado: Estado asignado (OK, Advertencia, Demorado).
        retraso_min: Minutos de retraso (None si es Error).
        critico: Si el tablero es critico.
    """
    log = get_logger("powerbi")
    retraso_str = f"{retraso_min:.1f}min" if retraso_min is not None else "N/A"
    nivel = logging.DEBUG
    if estado == "Demorado":
        nivel = logging.WARNING
    elif estado == "Advertencia":
        nivel = logging.DEBUG
    log.log(
        nivel,
        "Tablero '%s' -> %s (retraso=%s, critico=%s)",
        tablero,
        estado,
        retraso_str,
        critico,
    )


def log_auth_error(mensaje: str) -> None:
    """
    Registra un fallo de autenticacion.

    Args:
        mensaje: Detalle del error de auth.
    """
    log = get_logger("auth")
    log.critical("Fallo de autenticacion: %s", mensaje)


def log_frontend(metodo: str, path: str, status: int, duracion_ms: float) -> None:
    """
    Registra una peticion al frontend (para monitorear salud de la API).

    Args:
        metodo: HTTP method (GET, POST, etc).
        path: Path del endpoint.
        status: HTTP status code.
        duracion_ms: Duracion en milisegundos.
    """
    log = get_logger("frontend")
    nivel = logging.INFO
    if status >= 500:
        nivel = logging.ERROR
    elif status >= 400:
        nivel = logging.WARNING
    log.log(nivel, "%s %s -> %d (%.0fms)", metodo, path, status, duracion_ms)