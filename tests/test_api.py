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
        r = client.post("/api/corrida")
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
        r = client.post("/api/corrida")
        assert r.status_code == 500
        assert "token" in r.json()["detail"].lower()

    def test_corrida_timeout(self, client, monkeypatch):
        import subprocess

        monkeypatch.setattr(
            "frontend.server.subprocess.run",
            lambda *a, **kw: (_ for _ in ()).throw(subprocess.TimeoutExpired(cmd="x", timeout=1))
        )
        r = client.post("/api/corrida")
        assert r.status_code == 504