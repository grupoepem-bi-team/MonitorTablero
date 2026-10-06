"""
test_salud.py - Tests del modulo de salud del propio monitor.

Verifica el calculo de salud (ok / desactualizado / caido / sin_datos) y que
el healthcheck real distinga "proceso vivo" de "corrida real OK".
"""
from __future__ import annotations

from datetime import datetime, timedelta

from src import config
from src.salud import CAIDO, DESACTUALIZADO, OK, SIN_DATOS, calcular_salud, edad_minutos, esta_sano


def _meta(hace_min: float, exito: bool = True, error=None) -> dict:
    """Construye una meta con la ultima corrida hecha 'hace_min' minutos."""
    ts = datetime.now() - timedelta(minutes=hace_min)
    return {
        "version": 1,
        "ultima_corrida_fin": ts.isoformat(),
        "exito": exito,
        "error": error,
        "n_tableros": 21,
        "n_cambios_estado": 0,
    }


class TestCalcularSalud:
    def test_corrida_reciente_y_ok(self):
        s = calcular_salud(_meta(hace_min=1))
        assert s["codigo"] == OK
        assert s["exito"] is True
        assert s["edad_min"] is not None and s["edad_min"] < 5

    def test_corrida_fresca_justo_en_el_limite(self):
        # 30 min: dentro de la ventana fresca (35)
        assert calcular_salud(_meta(hace_min=30))["codigo"] == OK

    def test_corrida_desactualizada(self):
        # Entre 35 y 90 min: desactualizada
        s = calcular_salud(_meta(hace_min=50))
        assert s["codigo"] == DESACTUALIZADO
        assert esta_sano(s) is True

    def test_corrida_vieja_esta_caido(self):
        s = calcular_salud(_meta(hace_min=200))
        assert s["codigo"] == CAIDO
        assert esta_sano(s) is False

    def test_corrida_fallida_esta_caido_aunque_sea_reciente(self):
        # ESTE es el caso del incidente: corrida reciente pero exito=false
        s = calcular_salud(_meta(hace_min=2, exito=False, error="token silencioso"))
        assert s["codigo"] == CAIDO
        assert esta_sano(s) is False
        assert "token" in (s["error"] or "")

    def test_sin_datos(self):
        s = calcular_salud({})
        assert s["codigo"] == SIN_DATOS
        assert esta_sano(s) is False
        assert s["edad_min"] is None


class TestEdadMinutos:
    def test_none(self):
        assert edad_minutos(None) is None

    def test_invalido(self):
        assert edad_minutos("no es fecha") is None

    def test_calculo(self):
        ts = (datetime.now() - timedelta(minutes=10)).isoformat()
        edad = edad_minutos(ts)
        assert 9 <= edad <= 11

    def test_con_timezone_no_rompe(self):
        ts = (datetime.now() - timedelta(minutes=5)).isoformat() + "+00:00"
        edad = edad_minutos(ts)
        assert edad is not None
