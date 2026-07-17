"""
test_estados.py - Tests unitarios de la logica de calculo de estados.

Cubre los umbrales (OK / Advertencia / Demorado / Error), el uso de umbrales
por tablero desde el CSV vs fallback global, y el ordenamiento por prioridad.
"""
from __future__ import annotations

import pandas as pd
import pytest

from src import config
from src.estados import (
    _leer_umbral,
    calcular_estado,
    calcular_estado_y_fila,
    ordenar_por_prioridad_estado,
)


# ---------------------------------------------------------------------------
# calcular_estado
# ---------------------------------------------------------------------------

class TestCalcularEstado:
    def test_ok_dentro_del_umbral(self):
        assert calcular_estado(0) == "OK"
        assert calcular_estado(30) == "OK"
        assert calcular_estado(60) == "OK"

    def test_advertencia_entre_ok_y_demorado(self):
        assert calcular_estado(61) == "Advertencia"
        assert calcular_estado(70) == "Advertencia"
        assert calcular_estado(80) == "Advertencia"

    def test_demorado_superior_a_adv(self):
        assert calcular_estado(81) == "Demorado"
        assert calcular_estado(9999) == "Demorado"

    def test_umbral_negativo_es_ok(self):
        # Un tablero actualizado "en el futuro" (clock skew) -> OK
        assert calcular_estado(-5) == "OK"

    def test_umbral_personalizado(self):
        assert calcular_estado(15, ok_max=10, adv_max=20) == "Advertencia"
        assert calcular_estado(25, ok_max=10, adv_max=20) == "Demorado"
        assert calcular_estado(5, ok_max=10, adv_max=20) == "OK"

    def test_umbral_ok_igual_a_adv(self):
        # Si ok_max == adv_max no hay zona de advertencia
        assert calcular_estado(50, ok_max=50, adv_max=50) == "OK"
        assert calcular_estado(51, ok_max=50, adv_max=50) == "Demorado"


# ---------------------------------------------------------------------------
# _leer_umbral
# ---------------------------------------------------------------------------

class TestLeerUmbral:
    def test_int_valido(self):
        assert _leer_umbral({"frecuencia_objetivo_min": 30}, "frecuencia_objetivo_min") == 30

    def test_float_se_trunca_a_int(self):
        assert _leer_umbral({"frecuencia_objetivo_min": "30.7"}, "frecuencia_objetivo_min") == 30

    def test_str_no_numerico_devuelve_none(self):
        assert _leer_umbral({"frecuencia_objetivo_min": "abc"}, "frecuencia_objetivo_min") is None

    def test_clave_inexistente_devuelve_none(self):
        assert _leer_umbral({}, "frecuencia_objetivo_min") is None

    def test_none_devuelve_none(self):
        assert _leer_umbral({"frecuencia_objetivo_min": None}, "frecuencia_objetivo_min") is None


# ---------------------------------------------------------------------------
# calcular_estado_y_fila
# ---------------------------------------------------------------------------

class TestCalcularEstadoYFila:
    def _row(self, **overrides):
        base = {
            "tablero": "Test",
            "critico": "0",
            "frecuencia_objetivo_min": 30,
            "demorado_min": 60,
        }
        base.update(overrides)
        return base

    def test_fila_ok(self):
        hc = pd.Timestamp("2026-01-01 10:00:00")
        ua = pd.Timestamp("2026-01-01 09:40:00")  # 20 min de retraso
        fila = calcular_estado_y_fila(self._row(), hc, ua)
        assert fila["estado"] == "OK"
        assert fila["retraso_min"] == 20.0
        assert fila["error_detalle"] == ""
        assert "tablero" in fila and "critico" in fila

    def test_fila_advertencia(self):
        hc = pd.Timestamp("2026-01-01 10:00:00")
        ua = pd.Timestamp("2026-01-01 09:15:00")  # 45 min
        fila = calcular_estado_y_fila(self._row(), hc, ua)
        assert fila["estado"] == "Advertencia"

    def test_fila_demorado(self):
        hc = pd.Timestamp("2026-01-01 10:00:00")
        ua = pd.Timestamp("2026-01-01 08:00:00")  # 120 min
        fila = calcular_estado_y_fila(self._row(), hc, ua)
        assert fila["estado"] == "Demorado"

    def test_fila_sin_umbrales_csv_usa_fallback(self):
        hc = pd.Timestamp("2026-01-01 10:00:00")
        ua = pd.Timestamp("2026-01-01 09:30:00")  # 30 min -> OK con fallback (60)
        fila = calcular_estado_y_fila(self._row(frecuencia_objetivo_min=None, demorado_min=None), hc, ua)
        assert fila["estado"] == "OK"

    def test_fila_retraso_negativo(self):
        hc = pd.Timestamp("2026-01-01 10:00:00")
        ua = pd.Timestamp("2026-01-01 10:05:00")  # -5 min (clock skew)
        fila = calcular_estado_y_fila(self._row(), hc, ua)
        assert fila["estado"] == "OK"
        assert fila["retraso_min"] == -5.0


# ---------------------------------------------------------------------------
# ordenar_por_prioridad_estado
# ---------------------------------------------------------------------------

class TestOrdenarPorPrioridad:
    def _df(self):
        return pd.DataFrame([
            {"tablero": "A", "estado": "OK", "retraso_min": 10.0},
            {"tablero": "B", "estado": "Error", "retraso_min": float("nan")},
            {"tablero": "C", "estado": "Demorado", "retraso_min": 120.0},
            {"tablero": "D", "estado": "Advertencia", "retraso_min": 70.0},
            {"tablero": "E", "estado": "Demorado", "retraso_min": 90.0},
        ])

    def test_error_primero(self):
        df = ordenar_por_prioridad_estado(self._df())
        assert df.iloc[0]["estado"] == "Error"

    def test_ok_ultimo(self):
        df = ordenar_por_prioridad_estado(self._df())
        assert df.iloc[-1]["estado"] == "OK"

    def test_demorado_ordena_por_retraso_desc(self):
        df = ordenar_por_prioridad_estado(self._df())
        dem = df[df["estado"] == "Demorado"]
        assert dem.iloc[0]["retraso_min"] > dem.iloc[1]["retraso_min"]

    def test_df_vacio_no_rompe(self):
        df = ordenar_por_prioridad_estado(pd.DataFrame())
        assert df.empty

    def test_no_tiene_columna_prio_auxiliar(self):
        df = ordenar_por_prioridad_estado(self._df())
        assert "_prio_estado" not in df.columns