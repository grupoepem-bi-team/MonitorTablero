"""
auth.py - Autenticacion con Azure AD (Microsoft Entra ID) via MSAL.

Centraliza la obtencion del token de acceso para la API de Power BI.
El token se cachea en disco (token_cache.bin) para no requerir login
en cada corrida. Solo la primera vez se necesita el flujo de dispositivo.
"""
from __future__ import annotations

import os

from msal import PublicClientApplication, SerializableTokenCache

from src import config
from src.logger import get_logger

log = get_logger(__name__)


def _crear_aplicacion_msal() -> PublicClientApplication:
    """Crea la aplicacion MSAL con el cache de token cargado desde disco."""
    cache = SerializableTokenCache()
    if os.path.exists(config.CACHE_FILE):
        with open(config.CACHE_FILE, encoding="utf-8") as f:
            cache.deserialize(f.read())

    return PublicClientApplication(
        client_id=config.CLIENT_ID,
        authority=config.AUTHORITY,
        token_cache=cache,
    )


def obtener_token() -> str:
    """
    Obtiene un token de acceso silencioso desde el cache de MSAL.

    Usa el refresh token guardado para pedir un access token nuevo sin
    requerir interaccion del usuario. Si no hay cache o el refresh expiro,
    lanza RuntimeError indicando que hay que ejecutar auth_test.py.

    Returns:
        str: Token JWT para usar como Bearer en la API de Power BI.

    Raises:
        RuntimeError: Si no se puede obtener el token silenciosamente.
    """
    app = _crear_aplicacion_msal()
    accounts = app.get_accounts()

    if accounts:
        result = app.acquire_token_silent(config.SCOPES, account=accounts[0])
        if result and "access_token" in result:
            log.info("Token obtenido silenciosamente OK")
            return result["access_token"]

    log.critical("No se pudo obtener token silencioso - se requiere re-autenticacion")
    raise RuntimeError(
        "No se pudo obtener token silencioso. "
        "Ejecuta scripts/auth_test.py para volver a loguearte."
    )


def login_device_flow() -> dict:
    """
    Ejecuta el flujo de dispositivo (device flow) de Azure AD.

    Muestra en consola una URL y un codigo que el usuario debe ingresar
    en el navegador. Una vez autenticado, guarda el cache en disco.

    Returns:
        dict: Resultado de MSAL con el access_token y refresh_token.

    Raises:
        RuntimeError: Si no se puede iniciar el device flow.
    """
    cache = SerializableTokenCache()
    if os.path.exists(config.CACHE_FILE):
        with open(config.CACHE_FILE, encoding="utf-8") as f:
            cache.deserialize(f.read())

    app = PublicClientApplication(
        client_id=config.CLIENT_ID,
        authority=config.AUTHORITY,
        token_cache=cache,
    )

    flow = app.initiate_device_flow(scopes=config.SCOPES)
    if "user_code" not in flow:
        raise RuntimeError("No se pudo iniciar el device flow de Azure AD.")

    print("Abri este link en tu navegador:")
    print(flow["verification_uri"])
    print()
    print("Y pega este codigo:")
    print(flow["user_code"])
    print()

    result = app.acquire_token_by_device_flow(flow)

    if cache.has_state_changed:
        with open(config.CACHE_FILE, "w", encoding="utf-8") as f:
            f.write(cache.serialize())

    return result