"""
test_smoke.py - Smoke / salud general del proyecto.

Verifica que todos los modulos importen correctamente, que los archivos
de configuracion y persistencia existan y tengan la estructura esperada,
y que el entorno (.env, venv, dependencias) este completo.
"""
from __future__ import annotations

import importlib
import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ---------------------------------------------------------------------------
# 1. Imports: todos los modulos del paquete src deben cargar sin error
# ---------------------------------------------------------------------------

_MODULOS_SRC = [
    "src",
    "src.config",
    "src.logger",
    "src.auth",
    "src.powerbi",
    "src.estados",
    "src.persistencia",
    "src.cambios",
    "src.scheduler",
    "src.worker",
]

_MODULOS_FRONTEND = [
    "frontend",
    "frontend.server",
    "frontend.components.reactor_svg",
]


@pytest.mark.parametrize("modulo", _MODULOS_SRC + _MODULOS_FRONTEND)
def test_modulo_importa_ok(modulo):
    importlib.import_module(modulo)


# ---------------------------------------------------------------------------
# 2. Dependencias externas
# ---------------------------------------------------------------------------

_DEPS = ["pandas", "requests", "msal", "fastapi", "uvicorn", "dotenv"]


@pytest.mark.parametrize("dep", _DEPS)
def test_dependencia_instalada(dep):
    importlib.import_module(dep)


# ---------------------------------------------------------------------------
# 3. Archivos de configuracion y persistencia
# ---------------------------------------------------------------------------

_ARCHIVOS_BASE = [
    "config_tableros.csv",
    ".env.example",
    "requirements.txt",
    "src/__init__.py",
    "frontend/server.py",
    "frontend/templates/index.html",
    "frontend/static/app.js",
    "frontend/static/style.css",
]


@pytest.mark.parametrize("rel", _ARCHIVOS_BASE)
def test_archivo_base_existe(rel):
    p = os.path.join(_ROOT, rel)
    assert os.path.isfile(p), f"Falta archivo base: {rel}"
    assert os.path.getsize(p) > 0, f"Archivo vacio: {rel}"


def test_env_example_tiene_variables_clave():
    with open(os.path.join(_ROOT, ".env.example"), encoding="utf-8") as f:
        txt = f.read()
    for clave in ["AZURE_CLIENT_ID"]:
        assert clave in txt, f".env.example deberia mencionar {clave}"


# ---------------------------------------------------------------------------
# 4. config_tableros.csv: estructura y coherencia
# ---------------------------------------------------------------------------

def test_csv_tiene_columnas_esperadas():
    import pandas as pd
    df = pd.read_csv(os.path.join(_ROOT, "config_tableros.csv"), sep=";")
    cols = {"tablero", "workspace_id", "dataset_id", "tabla_dax",
            "columna_dax", "critico", "activo"}
    assert cols.issubset(set(df.columns)), f"Faltan columnas: {cols - set(df.columns)}"


def test_csv_no_duplicados_tablero():
    import pandas as pd
    df = pd.read_csv(os.path.join(_ROOT, "config_tableros.csv"), sep=";")
    dups = df["tablero"].duplicated()
    assert not dups.any(), f"Tableros duplicados: {df[dups]['tablero'].tolist()}"


def test_csv_ids_son_uuids_validos():
    import pandas as pd
    import re
    df = pd.read_csv(os.path.join(_ROOT, "config_tableros.csv"), sep=";")
    uuid_re = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
                         r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
    for col in ("workspace_id", "dataset_id"):
        bad = df[~df[col].astype(str).str.match(uuid_re)]
        assert bad.empty, f"IDs invalidos en {col}: {bad[['tablero', col]].to_dict('records')}"


def test_csv_critico_es_0_o_1():
    import pandas as pd
    df = pd.read_csv(os.path.join(_ROOT, "config_tableros.csv"), sep=";")
    validos = df["critico"].isin([0, 1])
    assert validos.all(), f"critico != 0/1: {df[~validos]['tablero'].tolist()}"


def test_csv_activo_tiene_al_menos_uno():
    import pandas as pd
    df = pd.read_csv(os.path.join(_ROOT, "config_tableros.csv"), sep=";")
    assert (df["activo"] == 1).any(), "No hay tableros activos en el CSV"


# ---------------------------------------------------------------------------
# 5. JSON de estado: estructura y coherencia
# ---------------------------------------------------------------------------

def test_estado_actual_json_estructura():
    import json
    p = os.path.join(_ROOT, "estado_actual.json")
    if not os.path.isfile(p):
        pytest.skip("estado_actual.json no existe (todavia no hay corrida)")
    with open(p, encoding="utf-8") as f:
        data = json.load(f)
    assert "tableros" in data and isinstance(data["tableros"], list)
    assert "updated_at" in data
    for t in data["tableros"]:
        for k in ("tablero", "estado", "critico", "retraso_min"):
            assert k in t, f"Falta clave {k} en entrada de {t.get('tablero','?')}"
        assert t["estado"] in ("OK", "Advertencia", "Demorado", "Error"), \
            f"Estado invalido: {t['estado']} en {t['tablero']}"


def test_snapshot_json_estructura():
    import json
    p = os.path.join(_ROOT, "estado_tableros_snapshot.json")
    if not os.path.isfile(p):
        pytest.skip("snapshot no existe")
    with open(p, encoding="utf-8") as f:
        data = json.load(f)
    assert "by_tablero" in data
    for nombre, info in data["by_tablero"].items():
        assert "estado" in info, f"Snapshot de {nombre} sin 'estado'"


def test_cambios_recientes_json_estructura():
    import json
    p = os.path.join(_ROOT, "cambios_recientes.json")
    if not os.path.isfile(p):
        pytest.skip("cambios_recientes.json no existe")
    with open(p, encoding="utf-8") as f:
        data = json.load(f)
    assert "lineas_cambios_ui" in data
    assert "lineas_fallos" in data
    assert isinstance(data["lineas_cambios_ui"], list)
    assert isinstance(data["lineas_fallos"], list)


def test_meta_corrida_json_estructura():
    import json
    p = os.path.join(_ROOT, "corrida_monitor_meta.json")
    if not os.path.isfile(p):
        pytest.skip("meta_corrida no existe")
    with open(p, encoding="utf-8") as f:
        data = json.load(f)
    for k in ("exito", "n_tableros", "duracion_s"):
        assert k in data, f"meta_corrida sin '{k}'"
    assert isinstance(data["exito"], bool)
    assert isinstance(data["n_tableros"], int)
    assert isinstance(data["duracion_s"], (int, float))