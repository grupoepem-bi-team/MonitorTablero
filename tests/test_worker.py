"""
test_worker.py - Tests del orquestador de corrida (worker).

Mockea auth.obtener_token y powerbi.consultar_tableros_en_paralelo para
verificar el flujo completo sin tocar la API real.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src import config


@pytest.fixture
def env_json(tmp_path, monkeypatch):
    """Redirige todos los JSON a tmp_path y devuelve los paths."""
    paths = {
        "estado": str(tmp_path / "estado.json"),
        "snapshot": str(tmp_path / "snapshot.json"),
        "cambios": str(tmp_path / "cambios.json"),
        "meta": str(tmp_path / "meta.json"),
        "historico": str(tmp_path / "historico.jsonl"),
    }
    monkeypatch.setattr(config, "ESTADO_ACTUAL_JSON", paths["estado"])
    monkeypatch.setattr(config, "SNAPSHOT_ESTADOS_JSON", paths["snapshot"])
    monkeypatch.setattr(config, "CAMBIOS_RECIENTES_JSON", paths["cambios"])
    monkeypatch.setattr(config, "CORRIDA_MONITOR_META_JSON", paths["meta"])
    monkeypatch.setattr(config, "HISTORICO_CORRIDAS_JSONL", paths["historico"])
    return paths


class TestEjecutarCorrida:
    @patch("src.worker.obtener_token")
    @patch("src.worker.consultar_tableros_en_paralelo")
    def test_corrida_ok(self, mock_paralelo, mock_token, env_json, tmp_path):
        mock_token.return_value = "fake-token"
        mock_paralelo.return_value = [
            {"tablero": "A", "critico": "1", "estado": "OK",
             "ultima_actualizacion": pd.Timestamp("2026-01-01 09:00"),
             "hora_consulta": pd.Timestamp("2026-01-01 10:00"),
             "retraso_min": 60.0, "error_detalle": ""},
            {"tablero": "B", "critico": "0", "estado": "Demorado",
             "ultima_actualizacion": pd.Timestamp("2026-01-01 07:00"),
             "hora_consulta": pd.Timestamp("2026-01-01 10:00"),
             "retraso_min": 180.0, "error_detalle": ""},
        ]

        # CSV temporal con 2 tableros
        csv_path = str(tmp_path / "test_tableros.csv")
        with open(csv_path, "w", encoding="utf-8") as f:
            f.write("tablero;workspace_id;dataset_id;tabla_dax;columna_dax;critico;frecuencia_objetivo_min;demorado_min;activo\n")
            f.write("A;12345678-1234-1234-1234-123456789012;abcdefab-abcd-abcd-abcd-abcdefabcdef;t;c;1;30;60;1\n")
            f.write("B;12345678-1234-1234-1234-123456789012;abcdefab-abcd-abcd-abcd-abcdefabcdef;t;c;0;30;60;1\n")

        from src.worker import ejecutar_corrida
        ejecutar_corrida(path_csv=csv_path)

        # Verificar que se escribieron los JSON
        assert os.path.isfile(env_json["estado"])
        assert os.path.isfile(env_json["snapshot"])
        assert os.path.isfile(env_json["cambios"])
        assert os.path.isfile(env_json["meta"])

        with open(env_json["estado"], encoding="utf-8") as f:
            estado = json.load(f)
        assert len(estado["tableros"]) == 2

        with open(env_json["meta"], encoding="utf-8") as f:
            meta = json.load(f)
        assert meta["exito"] is True
        assert meta["n_tableros"] == 2

    @patch("src.worker.obtener_token")
    def test_corrida_falla_sin_token(self, mock_token, env_json, tmp_path):
        mock_token.side_effect = RuntimeError("No se pudo obtener token")

        csv_path = str(tmp_path / "test_tableros.csv")
        with open(csv_path, "w", encoding="utf-8") as f:
            f.write("tablero;workspace_id;dataset_id;tabla_dax;columna_dax;critico;frecuencia_objetivo_min;demorado_min;activo\n")
            f.write("A;12345678-1234-1234-1234-123456789012;abcdefab-abcd-abcd-abcd-abcdefabcdef;t;c;1;30;60;1\n")

        from src.worker import ejecutar_corrida_con_manejo_error
        ok, err = ejecutar_corrida_con_manejo_error(path_csv=csv_path)
        assert ok is False
        assert "token" in err.lower()

        # La meta debe registrar el fallo
        with open(env_json["meta"], encoding="utf-8") as f:
            meta = json.load(f)
        assert meta["exito"] is False
        assert "token" in (meta["error"] or "").lower()

    @patch("src.worker.obtener_token")
    @patch("src.worker.consultar_tableros_en_paralelo")
    def test_corrida_sin_tableros_activos(self, mock_paralelo, mock_token, env_json, tmp_path):
        mock_token.return_value = "fake-token"

        csv_path = str(tmp_path / "test_tableros.csv")
        with open(csv_path, "w", encoding="utf-8") as f:
            f.write("tablero;workspace_id;dataset_id;tabla_dax;columna_dax;critico;frecuencia_objetivo_min;demorado_min;activo\n")
            f.write("A;12345678-1234-1234-1234-123456789012;abcdefab-abcd-abcd-abcd-abcdefabcdef;t;c;1;30;60;0\n")

        from src.worker import ejecutar_corrida
        ejecutar_corrida(path_csv=csv_path)

        # No debe llamar al paralelo (no hay activos)
        mock_paralelo.assert_not_called()

        with open(env_json["estado"], encoding="utf-8") as f:
            estado = json.load(f)
        assert estado["tableros"] == []  # DF vacio

    @patch("src.worker.obtener_token")
    @patch("src.worker.consultar_tableros_en_paralelo")
    def test_corrida_detecta_cambio_estado(self, mock_paralelo, mock_token, env_json, tmp_path):
        mock_token.return_value = "fake-token"

        # Primera corrida: todos OK
        mock_paralelo.return_value = [
            {"tablero": "A", "critico": "1", "estado": "OK",
             "ultima_actualizacion": pd.Timestamp("2026-01-01 09:30"),
             "hora_consulta": pd.Timestamp("2026-01-01 10:00"),
             "retraso_min": 30.0, "error_detalle": ""},
        ]

        csv_path = str(tmp_path / "test_tableros.csv")
        with open(csv_path, "w", encoding="utf-8") as f:
            f.write("tablero;workspace_id;dataset_id;tabla_dax;columna_dax;critico;frecuencia_objetivo_min;demorado_min;activo\n")
            f.write("A;12345678-1234-1234-1234-123456789012;abcdefab-abcd-abcd-abcd-abcdefabcdef;t;c;1;30;60;1\n")

        from src.worker import ejecutar_corrida
        ejecutar_corrida(path_csv=csv_path)

        # Segunda corrida: A pasa a Demorado
        mock_paralelo.return_value = [
            {"tablero": "A", "critico": "1", "estado": "Demorado",
             "ultima_actualizacion": pd.Timestamp("2026-01-01 07:00"),
             "hora_consulta": pd.Timestamp("2026-01-01 10:00"),
             "retraso_min": 180.0, "error_detalle": ""},
        ]
        ejecutar_corrida(path_csv=csv_path)

        with open(env_json["cambios"], encoding="utf-8") as f:
            cambios = json.load(f)
        assert cambios["hubo_cambios"] is True
        assert any("A" in linea for linea in cambios["lineas_cambios_ui"])

        with open(env_json["meta"], encoding="utf-8") as f:
            meta = json.load(f)
        assert meta["n_cambios_estado"] == 1