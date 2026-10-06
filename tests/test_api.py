"""
test_api.py - Tests de los endpoints del frontend FastAPI.

Usa TestClient para verificar que los endpoints respondan correctamente,
que el JSON tenga la estructura esperada y que los casos borde (sin estado,
estado corrupto) no rompan el servidor.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Cliente de test con JSON redirigidos a tmp_path."""
    from src import config

    monkeypatch.setattr(config, "ESTADO_ACTUAL_JSON", str(tmp_path / "estado.json"))
    monkeypatch.setattr(config, "SNAPSHOT_ESTADOS_JSON", str(tmp_path / "snapshot.json"))
    monkeypatch.setattr(config, "CAMBIOS_RECIENTES_JSON", str(tmp_path / "cambios.json"))
    monkeypatch.setattr(config, "CORRIDA_MONITOR_META_JSON", str(tmp_path / "meta.json"))

    from frontend.server import app
    return TestClient(app)


class TestIndex:
    def test_index_devuelve_html(self, client):
        r = client.get("/")
        assert r.status_code == 200
        assert "text/html" in r.headers.get("content-type", "")


class TestAPITodos:
    def test_sin_estado_devuelve_error(self, client):
        r = client.get("/api/todos")
        assert r.status_code == 200
        data = r.json()
        assert data["estado"] is None
        assert data["error"] is not None
        assert "estado_actual.json" in data["error"]

    def test_con_estado(self, client, tmp_path):
        # Escribir un estado_actual.json valido
        estado = {
            "version": 1,
            "updated_at": "2026-01-01T10:00:00",
            "tableros": [
                {"tablero": "A", "critico": 1, "estado": "OK",
                 "ultima_actualizacion": "2026-01-01T09:00:00",
                 "hora_consulta": "2026-01-01T10:00:00",
                 "retraso_min": 60.0, "error_detalle": ""},
                {"tablero": "B", "critico": 0, "estado": "Error",
                 "ultima_actualizacion": None,
                 "hora_consulta": "2026-01-01T10:00:00",
                 "retraso_min": None, "error_detalle": "timeout"},
            ],
        }
        p = os.path.join(str(tmp_path), "estado.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump(estado, f)

        r = client.get("/api/todos")
        assert r.status_code == 200
        data = r.json()
        assert data["estado"] is not None
        assert len(data["estado"]) == 2
        assert data["error"] is None
        estados = {t["tablero"]: t["estado"] for t in data["estado"]}
        assert estados["A"] == "OK"
        assert estados["B"] == "Error"

    def test_estado_corrupto_devuelve_error(self, client, tmp_path):
        p = os.path.join(str(tmp_path), "estado.json")
        with open(p, "w") as f:
            f.write("{corrupto")
        r = client.get("/api/todos")
        assert r.status_code == 200
        assert r.json()["estado"] is None
        assert r.json()["error"] is not None


class TestAPICorrida:
    def test_corrida_sin_token_sesion_da_403(self, client):
        """
        Sin la cookie/meta del panel, la corrida manual se rechaza.

        Es el caso del atacante en la red: puede llegar al puerto, pero no
        dispara trabajo contra la API de Power BI.
        """
        r = client.post("/api/corrida")
        assert r.status_code == 403
        assert "no autorizada" in r.json()["detail"].lower()

    def test_corrida_con_token_falso_da_403(self, client):
        """Con cookie de sesion pero cabecera distinta -> 403 (no coincide)."""
        client.cookies.set("monitor_csrf", "token-real")
        r = client.post("/api/corrida", headers={"X-CSRF-Token": "otro-token"})
        assert r.status_code == 403

    def test_index_entrega_token_de_sesion(self, client):
        """La pagina deja la cookie y el <meta> con el MISMO token."""
        r = client.get("/")
        assert r.status_code == 200
        assert "monitor_csrf" in r.cookies
        assert 'name="csrf-token"' in r.text
        # El token del meta debe coincidir con la cookie
        import re
        m = re.search(r'name="csrf-token" content="([^"]+)"', r.text)
        assert m, "el <meta> csrf-token no esta en el HTML"
        assert m.group(1) == r.cookies["monitor_csrf"]

    def test_corrida_con_token_valido_pasa(self, client, monkeypatch):
        """El panel (cookie + meta iguales) SI puede lanzar la corrida."""
        class FakeResult:
            returncode = 0
            stdout = "Corrida OK - 21 tableros"
            stderr = ""

        monkeypatch.setattr(
            "frontend.server.subprocess.run",
            lambda *a, **kw: FakeResult()
        )
        r = client.get("/")  # deja la cookie
        token = client.cookies.get("monitor_csrf")
        r = client.post("/api/corrida", headers={"X-CSRF-Token": token})
        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_corrida_sin_worker_real_mock_ok(self, client, monkeypatch):
        """Mockea subprocess.run para simular una corrida exitosa."""
        from frontend import server

        class FakeResult:
            returncode = 0
            stdout = "Corrida OK - 23 tableros"
            stderr = ""

        monkeypatch.setattr(
            "frontend.server.subprocess.run",
            lambda *a, **kw: FakeResult()
        )
        client.get("/")  # cookie de sesion
        r = client.post(
            "/api/corrida",
            headers={"X-CSRF-Token": client.cookies.get("monitor_csrf")},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True

    def test_corrida_fallo_worker(self, client, monkeypatch):
        from frontend import server

        class FakeResult:
            returncode = 1
            stdout = ""
            stderr = "Error: token expired"

        monkeypatch.setattr(
            "frontend.server.subprocess.run",
            lambda *a, **kw: FakeResult()
        )
        client.get("/")
        r = client.post(
            "/api/corrida",
            headers={"X-CSRF-Token": client.cookies.get("monitor_csrf")},
        )
        assert r.status_code == 500
        assert "token" in r.json()["detail"].lower()

    def test_corrida_timeout(self, client, monkeypatch):
        import subprocess

        monkeypatch.setattr(
            "frontend.server.subprocess.run",
            lambda *a, **kw: (_ for _ in ()).throw(subprocess.TimeoutExpired(cmd="x", timeout=1))
        )
        client.get("/")
        r = client.post(
            "/api/corrida",
            headers={"X-CSRF-Token": client.cookies.get("monitor_csrf")},
        )
        assert r.status_code == 504


def _escribir_meta(tmp_path, hace_min, exito=True, error=None):
    """Escribe un corrida_monitor_meta.json con la ultima corrida hecha hace N min."""
    from datetime import datetime, timedelta

    ts = datetime.now() - timedelta(minutes=hace_min)
    meta = {
        "version": 1,
        "ultima_corrida_fin": ts.isoformat(),
        "exito": exito,
        "error": error,
        "n_tableros": 21,
        "n_cambios_estado": 0,
    }
    with open(os.path.join(str(tmp_path), "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f)


class TestHealthz:
    """El healthcheck real valida la ULTIMA CORRIDA, no solo que el proceso viva."""

    def test_sin_datos_da_503(self, client):
        r = client.get("/healthz")
        assert r.status_code == 503

    def test_corrida_fresca_ok_da_200(self, client, tmp_path):
        _escribir_meta(tmp_path, hace_min=1, exito=True)
        r = client.get("/healthz")
        assert r.status_code == 200
        assert r.json()["codigo"] == "ok"

    def test_corrida_fallida_da_503_aunque_sea_reciente(self, client, tmp_path):
        # El caso del incidente: proceso vivo, corrida reciente, pero FALLO
        _escribir_meta(tmp_path, hace_min=2, exito=False, error="token silencioso")
        r = client.get("/healthz")
        assert r.status_code == 503
        assert r.json()["detail"]["codigo"] == "caido"

    def test_corrida_vieja_da_503(self, client, tmp_path):
        _escribir_meta(tmp_path, hace_min=500, exito=True)
        r = client.get("/healthz")
        assert r.status_code == 503


class TestAPITodosSalud:
    def test_api_todos_incluye_salud(self, client, tmp_path):
        _escribir_meta(tmp_path, hace_min=1, exito=True)
        r = client.get("/api/todos")
        assert r.status_code == 200
        assert "salud" in r.json()
        assert r.json()["salud"]["codigo"] == "ok"