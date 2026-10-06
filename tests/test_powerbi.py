"""
test_powerbi.py - Tests unitarios de la capa de consulta a Power BI.

Mockea requests.post para no tocar la API real. Verifica:
- Construccion del DAX query
- Parseo de la respuesta
- Manejo de errores (HTTP 401, 500, timeout, JSON malformado)
- Paralelismo: un tablero que falla no afecta a los demas
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
import requests

from src import config
from src.powerbi import (
    _fila_resultado_error,
    _procesar_un_tablero,
    consultar_tablero,
    consultar_tableros_en_paralelo,
)


_ROW = {
    "tablero": "Test",
    "workspace_id": "12345678-1234-1234-1234-123456789012",
    "dataset_id": "abcdefab-abcd-abcd-abcd-abcdefabcdef",
    "tabla_dax": "ventas",
    "columna_dax": "Actualizado_al",
    "critico": "1",
    "frecuencia_objetivo_min": 30,
    "demorado_min": 60,
    "activo": 1,
}


class TestConsultarTablero:
    def _mock_resp(self, raw_value="2026-01-01T10:00:00", status=200):
        resp = MagicMock()
        resp.status_code = status
        resp.json.return_value = {
            "results": [{"tables": [{"rows": [{"[ultima_actualizacion]": raw_value}]}]}]
        }
        resp.raise_for_status = MagicMock()
        if status >= 400:
            resp.raise_for_status.side_effect = Exception(f"HTTP {status}")
        return resp

    @patch("src.powerbi.requests.post")
    def test_consulta_ok(self, mock_post):
        mock_post.return_value = self._mock_resp()
        ts = consultar_tablero(_ROW, "fake-token")
        assert isinstance(ts, pd.Timestamp)
        assert ts == pd.Timestamp("2026-01-01 10:00:00")

        # Verificar URL y payload
        call_args = mock_post.call_args
        url = call_args[0][0]
        assert "executeQueries" in url
        assert _ROW["workspace_id"] in url
        assert _ROW["dataset_id"] in url

        headers = call_args[1]["headers"]
        assert headers["Authorization"] == "Bearer fake-token"

        payload = call_args[1]["json"]
        assert "EVALUATE" in payload["queries"][0]["query"]
        assert "MAX('ventas'[Actualizado_al])" in payload["queries"][0]["query"]

    @patch("src.powerbi.requests.post")
    def test_error_http_401(self, mock_post):
        mock_post.return_value = self._mock_resp(status=401)
        with pytest.raises(Exception, match="401"):
            consultar_tablero(_ROW, "fake-token")

    @patch("src.powerbi.requests.post")
    def test_error_http_500(self, mock_post):
        mock_post.return_value = self._mock_resp(status=500)
        with pytest.raises(Exception, match="500"):
            consultar_tablero(_ROW, "fake-token")

    @patch("src.powerbi.requests.post")
    def test_respuesta_malformada_sin_results(self, mock_post):
        resp = MagicMock()
        resp.status_code = 200
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {"otra_cosa": []}
        mock_post.return_value = resp
        with pytest.raises(KeyError):
            consultar_tablero(_ROW, "fake-token")

    @patch("src.powerbi.requests.post")
    def test_respuesta_con_null(self, mock_post):
        # Power BI puede devolver null si la columna esta vacia
        resp = MagicMock()
        resp.status_code = 200
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {
            "results": [{"tables": [{"rows": [{"[ultima_actualizacion]": None}]}]}]
        }
        mock_post.return_value = resp
        # pd.to_datetime(None) -> NaT, no deberia romper
        ts = consultar_tablero(_ROW, "fake-token")
        assert pd.isna(ts)


class TestProcesarUnTablero:
    @patch("src.powerbi.consultar_tablero")
    def test_ok(self, mock_consultar):
        mock_consultar.return_value = pd.Timestamp("2026-01-01 10:00:00")
        hora = pd.Timestamp("2026-01-01 10:30:00")
        resultado = _procesar_un_tablero(_ROW, "token", hora)
        assert resultado["estado"] == "OK"
        assert resultado["retraso_min"] == 30.0
        assert resultado["error_detalle"] == ""
        assert resultado["tablero"] == "Test"

    @patch("src.powerbi.consultar_tablero")
    def test_error_devuelve_fila_error(self, mock_consultar):
        mock_consultar.side_effect = Exception("Connection timeout")
        hora = pd.Timestamp("2026-01-01 10:30:00")
        resultado = _procesar_un_tablero(_ROW, "token", hora)
        assert resultado["estado"] == "Error"
        assert "timeout" in resultado["error_detalle"].lower()
        assert pd.isna(resultado["ultima_actualizacion"])
        assert resultado["retraso_min"] != resultado["retraso_min"]  # NaN check

    @patch("src.powerbi.consultar_tablero")
    def test_demorado(self, mock_consultar):
        mock_consultar.return_value = pd.Timestamp("2026-01-01 08:00:00")
        hora = pd.Timestamp("2026-01-01 10:30:00")  # 150 min
        resultado = _procesar_un_tablero(_ROW, "token", hora)
        assert resultado["estado"] == "Demorado"


class TestConsultarEnParalelo:
    def test_lista_vacia_devuelve_vacio(self):
        assert consultar_tableros_en_paralelo([], "token") == []

    @patch("src.powerbi._procesar_un_tablero")
    def test_un_fallo_no_afecta_al_resto(self, mock_proc):
        mock_proc.side_effect = [
            {"tablero": "A", "estado": "OK", "retraso_min": 10.0,
             "critico": "0", "ultima_actualizacion": pd.Timestamp.now(),
             "hora_consulta": pd.Timestamp.now(), "error_detalle": ""},
            {"tablero": "B", "estado": "Error", "retraso_min": float("nan"),
             "critico": "0", "ultima_actualizacion": pd.NaT,
             "hora_consulta": pd.Timestamp.now(), "error_detalle": "fail"},
            {"tablero": "C", "estado": "OK", "retraso_min": 5.0,
             "critico": "0", "ultima_actualizacion": pd.Timestamp.now(),
             "hora_consulta": pd.Timestamp.now(), "error_detalle": ""},
        ]
        records = [{"tablero": f"T{i}", "critico": "0"} for i in range(3)]
        resultados = consultar_tableros_en_paralelo(records, "token")
        assert len(resultados) == 3
        estados = [r["estado"] for r in resultados]
        assert "Error" in estados
        assert "OK" in estados


class TestFilaResultadoError:
    def test_estructura(self):
        hora = pd.Timestamp("2026-01-01 10:00")
        fila = _fila_resultado_error({"tablero": "X", "critico": "1"}, hora, "msg")
        assert fila["estado"] == "Error"
        assert fila["tablero"] == "X"
        assert fila["critico"] == "1"
        assert pd.isna(fila["ultima_actualizacion"])
        assert fila["error_detalle"] == "msg"


# ---------------------------------------------------------------------------
# Fase 2: reintentos y renovacion de token
# ---------------------------------------------------------------------------


class TestReintentos:
    """Un fallo transitorio (timeout / 5xx / 429) no debe marcar el tablero en Error."""

    def _ok_resp(self):
        resp = MagicMock()
        resp.status_code = 200
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {
            "results": [{"tables": [{"rows": [{"[ultima_actualizacion]": "2026-01-01T10:00:00"}]}]}]
        }
        return resp

    @patch("src.powerbi.time.sleep", MagicMock())
    @patch("src.powerbi.requests.post")
    def test_reintenta_en_timeout_y_luego_ok(self, mock_post):
        mock_post.side_effect = [requests.Timeout("boom"), requests.Timeout("boom"), self._ok_resp()]
        ts = consultar_tablero(_ROW, "tok")
        assert ts == pd.Timestamp("2026-01-01 10:00:00")
        assert mock_post.call_count == 3

    @patch("src.powerbi.time.sleep", MagicMock())
    @patch("src.powerbi.requests.post")
    def test_reintenta_en_500_y_luego_ok(self, mock_post):
        err = MagicMock()
        err.status_code = 503
        err.raise_for_status.side_effect = Exception("HTTP 503")
        mock_post.side_effect = [err, self._ok_resp()]
        ts = consultar_tablero(_ROW, "tok")
        assert ts == pd.Timestamp("2026-01-01 10:00:00")
        assert mock_post.call_count == 2

    @patch("src.powerbi.time.sleep", MagicMock())
    @patch("src.powerbi.requests.post")
    def test_agota_reintentos_y_lanza(self, mock_post):
        mock_post.side_effect = requests.Timeout("siempre falla")
        with pytest.raises(Exception):
            consultar_tablero(_ROW, "tok")
        # intentos iniciales + POWERBI_RETRIES
        assert mock_post.call_count == config.POWERBI_RETRIES + 1


class TestRenovacionTokenEn401:
    """Si el token vencio a mitad de corrida (401), renovar una vez y reintentar."""

    @patch("src.powerbi.obtener_token")
    @patch("src.powerbi.consultar_tablero")
    def test_renueva_token_y_reintenta(self, mock_consultar, mock_token):
        err401 = requests.HTTPError("401 Client Error")
        err401.response = MagicMock(status_code=401)
        mock_consultar.side_effect = [err401, pd.Timestamp("2026-01-01 10:00:00")]
        mock_token.return_value = "token-nuevo"
        hora = pd.Timestamp("2026-01-01 10:30:00")

        resultado = _procesar_un_tablero(_ROW, "token-viejo", hora)

        assert resultado["estado"] == "OK"
        assert resultado["error_detalle"] == ""
        mock_token.assert_called_once()
        assert mock_consultar.call_args_list[1][0][1] == "token-nuevo"