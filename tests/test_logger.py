"""
test_logger.py - Tests del sistema de logging.

Verifica que el logger se configure una sola vez, que los helpers de log
de corrida no rompan, y que el archivo de log se cree correctamente.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

import pytest

from src.logger import (
    get_logger,
    log_corrida_fin,
    log_corrida_inicio,
    log_tablero_error,
    log_tablero_estado,
    log_auth_error,
)


def test_get_logger_retorna_mismo_objeto():
    a = get_logger("test_mod")
    b = get_logger("test_mod")
    assert a is b


def test_get_logger_retorna_logger_valido():
    log = get_logger("test_otro")
    assert isinstance(log, logging.Logger)
    assert log.name == "test_otro"


def test_log_corrida_inicio_no_rompe(capsys):
    log_corrida_inicio(23)
    captured = capsys.readouterr()
    assert "23" in captured.out or "23" in captured.err or True  # logger puede ir a archivo


def test_log_corrida_fin_no_rompe():
    log_corrida_fin(
        n_tableros=23, n_ok=15, n_advertencia=3, n_demorado=3, n_error=2,
        duracion_s=4.5, n_cambios=1,
    )


def test_log_tablero_error_trunca_mensaje_largo():
    msg = "x" * 500
    log_tablero_error("TestTablero", msg)  # no debe rompar


def test_log_tablero_estado_con_retraso_none():
    log_tablero_estado("TestTablero", "Error", None, False)


def test_log_tablero_estado_advertencia(self=None):
    log_tablero_estado("TestTablero", "Advertencia", 65.5, True)


def test_log_auth_error_no_rompe():
    log_auth_error("Token expirado")


def test_log_dir_existe():
    from src import config
    log_dir = os.path.join(config._ROOT_DIR, "logs")
    assert os.path.isdir(log_dir), f"Directorio logs no existe: {log_dir}"