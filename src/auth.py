"""
auth.py - Autenticacion con Azure AD (Microsoft Entra ID) via MSAL.

Centraliza la obtencion del token de acceso para la API de Power BI.

Hay DOS modos, elegidos automaticamente por config.AUTH_MODE:

  1. service_principal (recomendado, sin usuario humano):
     Usa el client_id + client_secret de la app de Azure para pedir un token
     app-only. NO depende de que un humano se loguee, NO caduca por inactividad
     de usuario. Es el modo que evita que el monitor se caiga solo.

  2. device_flow (fallback, con usuario humano):
     Usa el token_cache.bin (refresh token) generado una vez por login de
     dispositivo. Requiere que alguien se vuelva a loguear cada ~90 dias.

En AMBOS casos el token de acceso dura ~1 hora y se renueva solo.
"""
from __future__ import annotations

import os

from msal import (
    ConfidentialClientApplication,
    PublicClientApplication,
    SerializableTokenCache,
)

from src import config
from src.logger import get_logger

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------


def obtener_token() -> str:
    """
    Obtiene un token de acceso para la API de Power BI.

    Elige el modo segun config.AUTH_MODE:
      - service_principal -> token app-only (client_credentials).
      - device_flow       -> token silencioso desde token_cache.bin.

    Returns:
        str: Token JWT para usar como Bearer en la API de Power BI.

    Raises:
        RuntimeError: Si no se puede obtener el token en ningun modo.
    """
    if config.AUTH_MODE == "service_principal":
        return _obtener_token_service_principal()
    return _obtener_token_device_flow()


# ---------------------------------------------------------------------------
# Modo 1: Service Principal (app-only, sin usuario)
# ---------------------------------------------------------------------------


def _obtener_token_service_principal() -> str:
    """
    Token app-only con las credenciales del Service Principal (client_credentials).

    No requiere usuario ni cache en disco: pide el token directo a Azure usando
    el client_id + client_secret + authority. Primero intenta el cache en memoria
    de MSAL; si no hay, pide uno nuevo.

    Returns:
        str: Token JWT.

    Raises:
        RuntimeError: Si Azure rechaza las credenciales o no devuelve token.
    """
    app = ConfidentialClientApplication(
        client_id=config.CLIENT_ID,
        client_credential=config.AZURE_CLIENT_SECRET,
        authority=config.AUTHORITY,
    )

    result = app.acquire_token_silent([config.POWERBI_SCOPE], account=None)
    if not result:
        result = app.acquire_token_for_client(scopes=[config.POWERBI_SCOPE])

    if result and "access_token" in result:
        log.info("Token obtenido via Service Principal OK")
        return result["access_token"]

    detalle = (result or {}).get("error_description") or (result or {}).get("error") or result
    log.critical("Service Principal sin token: %s", detalle)
    raise RuntimeError(
        "El Service Principal no pudo obtener token. "
        f"Detalle: {detalle}. "
        "Revisa AZURE_CLIENT_SECRET, el consentimiento de admin y el tenant setting "
        "'Service principals can use Power BI APIs'."
    )


# ---------------------------------------------------------------------------
# Modo 2: Device flow (con usuario, cache en disco)
# ---------------------------------------------------------------------------


def _crear_aplicacion_msal() -> tuple[PublicClientApplication, SerializableTokenCache]:
    """Crea la aplicacion MSAL publica con el cache de token cargado desde disco."""
    cache = SerializableTokenCache()
    if os.path.exists(config.CACHE_FILE):
        with open(config.CACHE_FILE, encoding="utf-8") as f:
            cache.deserialize(f.read())

    app = PublicClientApplication(
        client_id=config.CLIENT_ID,
        authority=config.AUTHORITY,
        token_cache=cache,
    )
    return app, cache


def _persistir_cache(cache: SerializableTokenCache) -> None:
    """
    Guarda en disco el cache de MSAL si cambio.

    ESTE ES EL FIX DEL BUG DE RAIZ: obtener_token() leia el cache, pedia el token
    silencioso y NUNCA volvia a guardar los refresh tokens renovados que MSAL
    devuelve. Con el tiempo el refresh token de disco envejecia hasta caducar y
    el monitor moria en silencio (incidente del 23/09/2026).
    """
    if cache.has_state_changed:
        with open(config.CACHE_FILE, "w", encoding="utf-8") as f:
            f.write(cache.serialize())


def _obtener_token_device_flow() -> str:
    """
    Obtiene un token silencioso desde el cache de MSAL (device flow).

    Usa el refresh token guardado para pedir un access token nuevo sin
    interaccion del usuario. Persiste el cache actualizado (fix del bug de raiz).

    Returns:
        str: Token JWT.

    Raises:
        RuntimeError: Si no hay cache valido o el refresh expiro.
    """
    app, cache = _crear_aplicacion_msal()
    accounts = app.get_accounts()

    if accounts:
        result = app.acquire_token_silent(config.SCOPES, account=accounts[0])
        if result and "access_token" in result:
            _persistir_cache(cache)
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
