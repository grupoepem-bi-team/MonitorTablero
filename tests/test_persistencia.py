"""
test_persistencia.py - Tests de lectura/escritura atomica de JSON.

Verifica el round-trip: guardar -> cargar -> comparar. Tambien prueba
casos borde: archivos corruptos, DataFrames vacios, NaT/NaN, y que las
escrituras sean atomicas (no queda .tmp suelto).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd
import pytest

from src import config
from src.persistencia import (
    cargar_estado_actual,
    cargar_snapshot,
    guardar_cambios_recientes,
    guardar_estado_actual,
    guardar_meta_corrida,
    guardar_snapshot,
    leer_cambios_recientes,
    leer_meta_corrida,
)


@pytest.fixture
def tmp_json(tmp_path, monkeypatch):
    """Redirige todos los JSON a un directorio temporal."""
    paths = {
        "estado": str(tmp_path / "estado.json"),
        "snapshot": str(tmp_path / "snapshot.json"),
        "cambios": str(tmp_path / "cambios.json"),
        "meta": str(tmp_path / "meta.json"),
    }
    monkeypatch.setattr(config, "ESTADO_ACTUAL_JSON", paths["estado"])
    monkeypatch.setattr(config, "SNAPSHOT_ESTADOS_JSON", paths["snapshot"])
    monkeypatch.setattr(config, "CAMBIOS_RECIENTES_JSON", paths["cambios"])
    monkeypatch.setattr(config, "CORRIDA_MONITOR_META_JSON", paths["meta"])
    return paths


# ---------------------------------------------------------------------------
# Estado actual
# ---------------------------------------------------------------------------

class TestEstadoActual:
    def test_round_trip_basico(self, tmp_json):
        df = pd.DataFrame([
            {"tablero": "A", "critico": "1", "estado": "OK",
             "ultima_actualizacion": pd.Timestamp("2026-01-01 10:00"),
             "hora_consulta": pd.Timestamp("2026-01-01 10:05"),
             "retraso_min": 5.0, "error_detalle": ""},
            {"tablero": "B", "critico": "0", "estado": "Error",
             "ultima_actualizacion": pd.NaT,
             "hora_consulta": pd.Timestamp("2026-01-01 10:05"),
             "retraso_min": float("nan"), "error_detalle": "timeout"},
        ])
        guardar_estado_actual(df, path=tmp_json["estado"])
        df2 = cargar_estado_actual(path=tmp_json["estado"])
        assert df2 is not None
        assert len(df2) == 2
        assert set(df2["tablero"]) == {"A", "B"}
        assert df2[df2["tablero"] == "A"]["estado"].iloc[0] == "OK"
        assert df2[df2["tablero"] == "B"]["estado"].iloc[0] == "Error"

    def test_no_deja_tmp_suelto(self, tmp_json):
        df = pd.DataFrame([
            {"tablero": "X", "critico": "0", "estado": "OK",
             "ultima_actualizacion": pd.Timestamp.now(),
             "hora_consulta": pd.Timestamp.now(),
             "retraso_min": 1.0, "error_detalle": ""}
        ])
        guardar_estado_actual(df, path=tmp_json["estado"])
        assert not os.path.exists(tmp_json["estado"] + ".tmp")

    def test_cargar_inexistente_devuelve_none(self, tmp_json):
        assert cargar_estado_actual(path="/no/existe.json") is None

    def test_cargar_corrupto_devuelve_none(self, tmp_json):
        p = tmp_json["estado"]
        with open(p, "w") as f:
            f.write("{no es json")
        assert cargar_estado_actual(path=p) is None

    def test_df_vacio(self, tmp_json):
        df = pd.DataFrame(columns=["tablero", "critico", "estado",
                                    "ultima_actualizacion", "hora_consulta",
                                    "retraso_min", "error_detalle"])
        guardar_estado_actual(df, path=tmp_json["estado"])
        df2 = cargar_estado_actual(path=tmp_json["estado"])
        assert df2 is not None
        assert df2.empty

    def test_nat_y_nan_se_serializan_como_null(self, tmp_json):
        df = pd.DataFrame([
            {"tablero": "E", "critico": "0", "estado": "Error",
             "ultima_actualizacion": pd.NaT,
             "hora_consulta": pd.Timestamp("2026-01-01 10:05"),
             "retraso_min": float("nan"), "error_detalle": "err"}
        ])
        guardar_estado_actual(df, path=tmp_json["estado"])
        with open(tmp_json["estado"], encoding="utf-8") as f:
            raw = json.load(f)
        assert raw["tableros"][0]["ultima_actualizacion"] is None
        assert raw["tableros"][0]["retraso_min"] is None


# ---------------------------------------------------------------------------
# Snapshot
# ---------------------------------------------------------------------------

class TestSnapshot:
    def test_round_trip(self, tmp_json):
        df = pd.DataFrame([
            {"tablero": "A", "estado": "OK"},
            {"tablero": "B", "estado": "Demorado"},
        ])
        guardar_snapshot(df, path=tmp_json["snapshot"])
        snap = cargar_snapshot(path=tmp_json["snapshot"])
        assert snap["A"]["estado"] == "OK"
        assert snap["B"]["estado"] == "Demorado"

    def test_cargar_inexistente_devuelve_vacio(self, tmp_json):
        assert cargar_snapshot(path="/no/existe.json") == {}

    def test_cargar_corrupto_devuelve_vacio(self, tmp_json):
        p = tmp_json["snapshot"]
        with open(p, "w") as f:
            f.write("corrupto")
        assert cargar_snapshot(path=p) == {}

    def test_formato_legacy_str(self, tmp_json):
        # Si el snapshot tiene valores como string en vez de dict
        p = tmp_json["snapshot"]
        with open(p, "w", encoding="utf-8") as f:
            json.dump({"by_tablero": {"A": "OK"}}, f)
        snap = cargar_snapshot(path=p)
        assert snap["A"]["estado"] == "OK"


# ---------------------------------------------------------------------------
# Cambios recientes
# ---------------------------------------------------------------------------

class TestCambiosRecientes:
    def test_round_trip(self, tmp_json):
        guardar_cambios_recientes(["**X** paso de OK a Demorado"], ["fallo algo"])
        lc, lf = leer_cambios_recientes()
        assert lc == ["**X** paso de OK a Demorado"]
        assert lf == ["fallo algo"]

    def test_inexistente_devuelve_vacio(self, tmp_json):
        lc, lf = leer_cambios_recientes(path="/no/existe.json")
        assert lc == [] and lf == []

    def test_corrupto_devuelve_vacio(self, tmp_json):
        p = tmp_json["cambios"]
        with open(p, "w") as f:
            f.write("xxx")
        assert leer_cambios_recientes(path=p) == ([], [])


# ---------------------------------------------------------------------------
# Meta corrida
# ---------------------------------------------------------------------------

class TestMetaCorrida:
    def test_round_trip_exito(self, tmp_json):
        guardar_meta_corrida(exito=True, duracion_s=4.5, n_tableros=23, n_cambios=1)
        meta = leer_meta_corrida()
        assert meta["exito"] is True
        assert meta["n_tableros"] == 23
        assert meta["n_cambios_estado"] == 1
        assert meta["error"] is None

    def test_round_trip_fallo(self, tmp_json):
        guardar_meta_corrida(exito=False, duracion_s=0, n_tableros=0,
                             n_cambios=0, error="No se pudo obtener token")
        meta = leer_meta_corrida()
        assert meta["exito"] is False
        assert "token" in meta["error"]

    def test_inexistente_devuelve_vacio(self, tmp_json):
        assert leer_meta_corrida(path="/no/existe.json") == {}