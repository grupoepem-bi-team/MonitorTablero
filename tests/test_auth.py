"""
test_auth.py - Tests de la autenticacion (device flow + Service Principal).

Cubre:
  - el fix del bug de raiz: persistir el token cache renovado en cada corrida
  - el nuevo modo Service Principal (client_credentials, sin usuario)
  - que el modo device flow (fallback) siga funcionando

Ninguno toca la red: MSAL se reemplaza por dobles (fakes).
"""
from __future__ import annotations

from src import auth, config


# ---------------------------------------------------------------------------
# Modo Service Principal (app-only)
# ---------------------------------------------------------------------------


def test_sp_usa_confidential_client(monkeypatch):
    """En modo service_principal debe usar ConfidentialClientApplication con el secret."""
    monkeypatch.setattr(config, "AUTH_MODE", "service_principal", raising=False)
    monkeypatch.setattr(config, "AZURE_CLIENT_SECRET", "secreto-de-prueba", raising=False)

    capturado = {}

    class FakeConf:
        def __init__(self, client_id=None, client_credential=None, authority=None, **k):
            capturado["client_id"] = client_id
            capturado["client_credential"] = client_credential
            capturado["authority"] = authority

        def acquire_token_silent(self, scopes, account=None):
            return None

        def acquire_token_for_client(self, scopes=None):
            return {"access_token": "TOKEN-SP"}

    monkeypatch.setattr(auth, "ConfidentialClientApplication", FakeConf, raising=False)

    token = auth.obtener_token()

    assert token == "TOKEN-SP"
    assert capturado["client_credential"] == "secreto-de-prueba"
    assert capturado["authority"] == config.AUTHORITY


def test_sp_sin_token_lanza_error(monkeypatch):
    """Si el Service Principal no devuelve token, debe lanzar RuntimeError claro."""
    monkeypatch.setattr(config, "AUTH_MODE", "service_principal", raising=False)
    monkeypatch.setattr(config, "AZURE_CLIENT_SECRET", "x", raising=False)

    class FakeConf:
        def __init__(self, **k):
            pass

        def acquire_token_silent(self, scopes, account=None):
            return None

        def acquire_token_for_client(self, scopes=None):
            return {"error": "invalid_client", "error_description": "bad secret"}

    monkeypatch.setattr(auth, "ConfidentialClientApplication", FakeConf, raising=False)

    try:
        auth.obtener_token()
        assert False, "deberia haber lanzado RuntimeError"
    except RuntimeError as e:
        assert "bad secret" in str(e)


# ---------------------------------------------------------------------------
# Fix del bug de raiz: persistir el cache en el device flow
# ---------------------------------------------------------------------------


def test_device_flow_persiste_cache(tmp_path, monkeypatch):
    """
    BUG DE RAIZ: obtener_token() debe GUARDAR el cache renovado en disco.

    Sin esto, el refresh token de disco envejece hasta caducar y el monitor
    muere en silencio (el incidente del 23/09/2026).
    """
    cache_file = tmp_path / "token_cache.bin"
    monkeypatch.setattr(config, "CACHE_FILE", str(cache_file), raising=False)
    monkeypatch.setattr(config, "AUTH_MODE", "device_flow", raising=False)

    class FakeCache:
        has_state_changed = True

        def deserialize(self, s):
            pass

        def serialize(self):
            return "CACHE-SERIALIZADO"

    monkeypatch.setattr(auth, "SerializableTokenCache", lambda: FakeCache(), raising=False)

    class FakePCA:
        def __init__(self, **k):
            pass

        def get_accounts(self):
            return [{"username": "alguien@GRUPOIDEM.onmicrosoft.com"}]

        def acquire_token_silent(self, scopes, account=None):
            return {"access_token": "TOKEN-DF"}

    monkeypatch.setattr(auth, "PublicClientApplication", FakePCA, raising=False)

    token = auth.obtener_token()

    assert token == "TOKEN-DF"
    assert cache_file.read_text(encoding="utf-8") == "CACHE-SERIALIZADO"


def test_device_flow_sin_cache_no_escribe(tmp_path, monkeypatch):
    """Si MSAL no cambio el cache, no hay que reescribir el archivo."""
    cache_file = tmp_path / "token_cache.bin"
    monkeypatch.setattr(config, "CACHE_FILE", str(cache_file), raising=False)
    monkeypatch.setattr(config, "AUTH_MODE", "device_flow", raising=False)

    class FakeCache:
        has_state_changed = False

        def deserialize(self, s):
            pass

        def serialize(self):
            return "NO-DEBERIA"

    monkeypatch.setattr(auth, "SerializableTokenCache", lambda: FakeCache(), raising=False)

    class FakePCA:
        def __init__(self, **k):
            pass

        def get_accounts(self):
            return [{"username": "x"}]

        def acquire_token_silent(self, scopes, account=None):
            return {"access_token": "TOKEN-DF"}

    monkeypatch.setattr(auth, "PublicClientApplication", FakePCA, raising=False)

    auth.obtener_token()

    assert not cache_file.exists()


def test_device_flow_sin_cuenta_lanza_error(monkeypatch):
    """Sin cuentas en el cache, debe indicar que hace falta re-loguear."""
    monkeypatch.setattr(config, "AUTH_MODE", "device_flow", raising=False)

    class FakeCache:
        has_state_changed = False

        def deserialize(self, s):
            pass

        def serialize(self):
            return ""

    monkeypatch.setattr(auth, "SerializableTokenCache", lambda: FakeCache(), raising=False)

    class FakePCA:
        def __init__(self, **k):
            pass

        def get_accounts(self):
            return []

    monkeypatch.setattr(auth, "PublicClientApplication", FakePCA, raising=False)

    try:
        auth.obtener_token()
        assert False, "deberia haber lanzado RuntimeError"
    except RuntimeError as e:
        assert "loguearte" in str(e).lower() or "token silencioso" in str(e).lower()
