"""
test_cambios.py - Tests unitarios de deteccion de cambios entre corridas.

Verifica que detectar_cambios identifique correctamente transiciones
(OK->Demorado, Error->OK, etc.), respete criticidad, y no falle con
snapshot vacio o DataFrame vacio.
"""
from __future__ import annotations

import pandas as pd
import pytest

from src.cambios import detectar_cambios, texto_cambio


def _df(estados: dict[str, str]) -> pd.DataFrame:
    return pd.DataFrame([
        {"tablero": t, "estado": e, "critico": "1" if t.startswith("C_") else "0"}
        for t, e in estados.items()
    ])


class TestDetectarCambios:
    def test_sin_cambios_devuelve_vacio(self):
        df = _df({"A": "OK", "B": "Demorado"})
        prev = {"A": {"estado": "OK"}, "B": {"estado": "Demorado"}}
        assert detectar_cambios(df, prev) == []

    def test_cambio_ok_a_demorado(self):
        df = _df({"A": "Demorado"})
        prev = {"A": {"estado": "OK"}}
        cambios = detectar_cambios(df, prev)
        assert len(cambios) == 1
        assert cambios[0] == ("A", "OK", "Demorado", False)

    def test_cambio_error_a_ok(self):
        df = _df({"A": "OK"})
        prev = {"A": {"estado": "Error"}}
        cambios = detectar_cambios(df, prev)
        assert cambios[0][1] == "Error"
        assert cambios[0][2] == "OK"

    def test_critico_se_marca(self):
        df = _df({"C_X": "Demorado"})
        prev = {"C_X": {"estado": "OK"}}
        cambios = detectar_cambios(df, prev)
        assert cambios[0][3] is True

    def test_tablero_nuevo_no_es_cambio(self):
        # Un tablero que no esta en el snapshot anterior no genera cambio
        df = _df({"NUEVO": "OK"})
        prev = {}
        assert detectar_cambios(df, prev) == []

    def test_snapshot_vacio_no_rompe(self):
        df = _df({"A": "OK"})
        assert detectar_cambios(df, {}) == []

    def test_df_vacio_no_rompe(self):
        df = pd.DataFrame(columns=["tablero", "estado", "critico"])
        prev = {"A": {"estado": "OK"}}
        assert detectar_cambios(df, prev) == []

    def test_multiples_cambios(self):
        df = _df({"A": "Demorado", "B": "OK", "C": "Error"})
        prev = {"A": {"estado": "OK"}, "B": {"estado": "Demorado"}, "C": {"estado": "OK"}}
        cambios = detectar_cambios(df, prev)
        assert len(cambios) == 3

    def test_critico_no_numerico_no_rompe(self):
        df = pd.DataFrame([{"tablero": "X", "estado": "Demorado", "critico": "abc"}])
        prev = {"X": {"estado": "OK"}}
        cambios = detectar_cambios(df, prev)
        assert cambios[0][3] is False  # fallback seguro


class TestTextoCambio:
    def test_formato_basico(self):
        txt = texto_cambio("Facturacion", "OK", "Demorado")
        assert "Facturacion" in txt
        assert "OK" in txt
        assert "Demorado" in txt

    def test_estado_desconocido_usa_label(self):
        txt = texto_cambio("X", "DESCONOCIDO", "OK")
        # LABEL_ESTADO no tiene "DESCONOCIDO", usa el valor original
        assert "DESCONOCIDO" in txt