"""
test_metricas.py - Tests unitarios de las metricas derivadas.

Verifica resumen, ranking de atraso, criticos en riesgo, top constantes,
tendencia, fiabilidad y formateo de tiempo humano.
"""
from __future__ import annotations

import math
from unittest.mock import MagicMock

import pandas as pd
import pytest

from src.metricas import (
    calcular_fiabilidad,
    calcular_metricas_completas,
    calcular_resumen,
    calcular_tendencia,
    criticos_en_riesgo,
    enriquecer_tableros,
    formatear_hace,
    ranking_atraso,
    ranking_constantes,
)


def _df():
    """DataFrame con 5 tableros representativos."""
    return pd.DataFrame([
        {"tablero": "A", "critico": "1", "estado": "OK",
         "ultima_actualizacion": pd.Timestamp("2026-07-16 10:00"),
         "hora_consulta": pd.Timestamp("2026-07-16 10:30"),
         "retraso_min": 30.0, "error_detalle": ""},
        {"tablero": "B", "critico": "1", "estado": "Demorado",
         "ultima_actualizacion": pd.Timestamp("2026-07-16 07:00"),
         "hora_consulta": pd.Timestamp("2026-07-16 10:30"),
         "retraso_min": 210.0, "error_detalle": ""},
        {"tablero": "C", "critico": "0", "estado": "Advertencia",
         "ultima_actualizacion": pd.Timestamp("2026-07-16 09:15"),
         "hora_consulta": pd.Timestamp("2026-07-16 10:30"),
         "retraso_min": 75.0, "error_detalle": ""},
        {"tablero": "D", "critico": "0", "estado": "Error",
         "ultima_actualizacion": pd.NaT,
         "hora_consulta": pd.Timestamp("2026-07-16 10:30"),
         "retraso_min": float("nan"), "error_detalle": "timeout"},
        {"tablero": "E", "critico": "0", "estado": "OK",
         "ultima_actualizacion": pd.Timestamp("2026-07-16 10:05"),
         "hora_consulta": pd.Timestamp("2026-07-16 10:30"),
         "retraso_min": 25.0, "error_detalle": ""},
    ])


class TestFormatearHace:
    def test_minutos(self):
        assert formatear_hace(25) == "25min"
        assert formatear_hace(0) == "0min"

    def test_hora_y_minuto(self):
        assert formatear_hace(90) == "1h 30m"
        assert formatear_hace(60) == "1h"

    def test_dia(self):
        assert formatear_hace(1440) == "1 dia"
        assert formatear_hace(1500) == "1 dia 1h"

    def test_dias(self):
        assert formatear_hace(2880) == "2 dias"
        assert formatear_hace(3000) == "2 dias 2h"

    def test_nan_devuelve_dashes(self):
        assert formatear_hace(float("nan")) == "--"
        assert formatear_hace(None) == "--"

    def test_negativo_devuelve_cero(self):
        assert formatear_hace(-5) == "0min"

    def test_outlier_extremo(self):
        assert "dias" in formatear_hace(542944)


class TestCalcularResumen:
    def test_resumen_basico(self):
        r = calcular_resumen(_df())
        assert r["total"] == 5
        assert r["n_ok"] == 2
        assert r["n_advertencia"] == 1
        assert r["n_demorado"] == 1
        assert r["n_error"] == 1
        assert r["pct_ok"] == 40.0
        assert r["n_criticos"] == 2
        assert r["n_criticos_riesgo"] == 1  # B es critico y demorado

    def test_resumen_vacio(self):
        r = calcular_resumen(pd.DataFrame())
        assert r["total"] == 0
        assert r["n_ok"] == 0
        assert r["pct_ok"] == 0

    def test_promedio_excluye_outliers(self):
        # Un tablero con 20000 min (> 7 dias = 10080) no debe sesgar el promedio
        df = pd.DataFrame([
            {"tablero": "X", "critico": "0", "estado": "OK", "retraso_min": 20.0},
            {"tablero": "Y", "critico": "0", "estado": "Demorado", "retraso_min": 20000.0},
        ])
        r = calcular_resumen(df)
        assert r["promedio_retraso"] == 20.0  # solo X, Y descartado
        assert r["retraso_max"] == 20000.0  # pero el maximo si lo incluye


class TestRankingAtraso:
    def test_ordenado_por_ratio_desc(self):
        ranking = ranking_atraso(_df(), objetivo_min=30, top_n=10)
        assert len(ranking) == 4  # D tiene NaN y se excluye
        # B tiene 210/30 = 7x, C tiene 75/30 = 2.5x, A 1x, E 0.83x
        assert ranking[0]["tablero"] == "B"
        assert ranking[0]["ratio"] == 7.0
        assert ranking[-1]["tablero"] == "E"

    def test_top_n_limita(self):
        ranking = ranking_atraso(_df(), top_n=2)
        assert len(ranking) == 2

    def test_df_vacio(self):
        assert ranking_atraso(pd.DataFrame()) == []

    def test_incluye_hace(self):
        ranking = ranking_atraso(_df(), objetivo_min=30)
        assert "hace" in ranking[0]
        assert "min" in ranking[0]["hace"] or "h" in ranking[0]["hace"]


class TestRankingConstantes:
    def test_ordenado_por_menor_retraso(self):
        constantes = ranking_constantes(_df(), top_n=5)
        assert len(constantes) == 2  # A y E son OK
        assert constantes[0]["tablero"] == "E"  # 25 min
        assert constantes[1]["tablero"] == "A"  # 30 min

    def test_no_incluye_error(self):
        constantes = ranking_constantes(_df())
        tableros = [c["tablero"] for c in constantes]
        assert "D" not in tableros  # D es Error

    def test_df_vacio(self):
        assert ranking_constantes(pd.DataFrame()) == []


class TestCriticosEnRiesgo:
    def test_solo_criticos_con_problema(self):
        riesgo = criticos_en_riesgo(_df())
        assert len(riesgo) == 1
        assert riesgo[0]["tablero"] == "B"
        assert riesgo[0]["estado"] == "Demorado"

    def test_ordenado_por_retraso_desc(self):
        df = pd.DataFrame([
            {"tablero": "A", "critico": "1", "estado": "Demorado", "retraso_min": 100.0},
            {"tablero": "B", "critico": "1", "estado": "Advertencia", "retraso_min": 50.0},
        ])
        riesgo = criticos_en_riesgo(df)
        assert riesgo[0]["tablero"] == "A"
        assert riesgo[1]["tablero"] == "B"

    def test_no_hay_criticos(self):
        df = pd.DataFrame([
            {"tablero": "A", "critico": "0", "estado": "Demorado", "retraso_min": 100.0},
        ])
        assert criticos_en_riesgo(df) == []

    def test_df_vacio(self):
        assert criticos_en_riesgo(pd.DataFrame()) == []


class TestTendencia:
    def test_mejora(self):
        historico = [
            {"ts": "2026-01-01", "tableros": [{"tablero": "A", "retraso_min": 100, "estado": "Demorado"}]},
            {"ts": "2026-01-01T00:30", "tableros": [{"tablero": "A", "retraso_min": 50, "estado": "OK"}]},
        ]
        tend = calcular_tendencia(historico)
        assert tend["A"]["direccion"] == "mejora"
        assert tend["A"]["delta"] == -50.0

    def test_empeora(self):
        historico = [
            {"ts": "2026-01-01", "tableros": [{"tablero": "A", "retraso_min": 30, "estado": "OK"}]},
            {"ts": "2026-01-01T00:30", "tableros": [{"tablero": "A", "retraso_min": 90, "estado": "Demorado"}]},
        ]
        tend = calcular_tendencia(historico)
        assert tend["A"]["direccion"] == "empeora"
        assert tend["A"]["delta"] == 60.0

    def test_estable(self):
        historico = [
            {"ts": "2026-01-01", "tableros": [{"tablero": "A", "retraso_min": 30.0, "estado": "OK"}]},
            {"ts": "2026-01-01T00:30", "tableros": [{"tablero": "A", "retraso_min": 30.5, "estado": "OK"}]},
        ]
        tend = calcular_tendencia(historico)
        assert tend["A"]["direccion"] == "estable"

    def test_historico_vacio(self):
        assert calcular_tendencia([]) == {}

    def test_una_sola_corrida(self):
        historico = [{"ts": "2026-01-01", "tableros": [{"tablero": "A", "retraso_min": 30}]}]
        assert calcular_tendencia(historico) == {}

    def test_tablero_nuevo_no_tiene_tendencia(self):
        historico = [
            {"ts": "2026-01-01", "tableros": [{"tablero": "A", "retraso_min": 30}]},
            {"ts": "2026-01-01T00:30", "tableros": [{"tablero": "A", "retraso_min": 30}, {"tablero": "B", "retraso_min": 20}]},
        ]
        tend = calcular_tendencia(historico)
        assert "A" in tend
        assert "B" not in tend  # B es nuevo, no tiene anterior


class TestFiabilidad:
    def test_pct_ok(self):
        historico = [
            {"ts": "2026-01-01", "tableros": [{"tablero": "A", "estado": "OK"}]},
            {"ts": "2026-01-01T00:30", "tableros": [{"tablero": "A", "estado": "Demorado"}]},
            {"ts": "2026-01-01T01:00", "tableros": [{"tablero": "A", "estado": "OK"}]},
        ]
        fiab = calcular_fiabilidad(historico)
        assert fiab["A"]["n_corridas"] == 3
        assert fiab["A"]["n_ok"] == 2
        assert fiab["A"]["pct_ok"] == 66.7

    def test_dias_consecutivos_demorado(self):
        historico = [
            {"ts": "2026-01-01", "tableros": [{"tablero": "A", "estado": "OK"}]},
            {"ts": "2026-01-01T00:30", "tableros": [{"tablero": "A", "estado": "Demorado"}]},
            {"ts": "2026-01-01T01:00", "tableros": [{"tablero": "A", "estado": "Demorado"}]},
            {"ts": "2026-01-01T01:30", "tableros": [{"tablero": "A", "estado": "Error"}]},
        ]
        fiab = calcular_fiabilidad(historico)
        assert fiab["A"]["dias_consecutivos_demorado"] == 3  # Demorado+Demorado+Error

    def test_historico_vacio(self):
        assert calcular_fiabilidad([]) == {}


class TestEnriquecerTableros:
    def test_agrega_ratio_y_hace(self):
        tableros = enriquecer_tableros(_df(), objetivo_min=30)
        assert len(tableros) == 5
        # B tiene 210 min / 30 = 7.0
        b = next(t for t in tableros if t["tablero"] == "B")
        assert b["ratio"] == 7.0
        assert "hace" in b
        assert "h" in b["hace"]  # 210 min = 3h 30m

    def test_error_tiene_ratio_none(self):
        tableros = enriquecer_tableros(_df(), objetivo_min=30)
        d = next(t for t in tableros if t["tablero"] == "D")
        assert d["ratio"] is None
        assert d["hace"] == "--"

    def test_df_vacio(self):
        assert enriquecer_tableros(pd.DataFrame()) == []


class TestCalcularMetricasCompletas:
    def test_tiene_todas_las_claves(self):
        m = calcular_metricas_completas(_df(), historico=[], objetivo_min=30)
        for k in ("resumen", "ranking_atraso", "ranking_constantes",
                  "criticos_riesgo", "tendencia", "fiabilidad", "tableros"):
            assert k in m, f"Falta clave: {k}"

    def test_df_vacio(self):
        m = calcular_metricas_completas(pd.DataFrame(), historico=[])
        assert m["resumen"]["total"] == 0
        assert m["ranking_atraso"] == []
        assert m["tableros"] == []

    def test_con_historico(self):
        historico = [
            {"ts": "2026-01-01", "tableros": [{"tablero": "A", "retraso_min": 50, "estado": "Demorado"}]},
            {"ts": "2026-01-01T00:30", "tableros": [{"tablero": "A", "retraso_min": 30, "estado": "OK"}]},
        ]
        m = calcular_metricas_completas(_df(), historico=historico)
        assert "A" in m["tendencia"]
        assert m["tendencia"]["A"]["direccion"] == "mejora"
        assert "A" in m["fiabilidad"]
        assert m["fiabilidad"]["A"]["n_corridas"] == 2