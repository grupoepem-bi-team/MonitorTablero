"""
powerbi.py - Consulta a la API REST de Power BI.

Ejecuta consultas DAX contra los datasets de Power BI para obtener la fecha
de ultima actualizacion de cada tablero. Maneja el paralelismo con
ThreadPoolExecutor para consultar multiples tableros a la vez.
"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from functools import partial

import pandas as pd
import requests

from src import config
from src.auth import obtener_token
from src.logger import log_tablero_error, log_tablero_estado


def consultar_tablero(row: dict, access_token: str) -> pd.Timestamp:
    """
    Consulta la fecha maxima de una columna de un dataset de Power BI.

    Ejecuta un DAX del tipo:
        EVALUATE ROW("ultima_actualizacion", MAX('tabla'[columna]))

    Args:
        row: Diccionario con workspace_id, dataset_id, tabla_dax, columna_dax.
        access_token: Token JWT de Azure AD para autenticar la llamada.

    Returns:
        pd.Timestamp: La fecha/hora mas reciente encontrada en la columna.

    Raises:
        requests.RequestException: Si la llamada HTTP falla.
        KeyError: Si la respuesta no tiene la estructura esperada.
    """
    url = (
        f"https://api.powerbi.com/v1.0/myorg/groups/{row['workspace_id']}"
        f"/datasets/{row['dataset_id']}/executeQueries"
    )
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    query = f"EVALUATE ROW(\"ultima_actualizacion\", MAX('{row['tabla_dax']}'[{row['columna_dax']}]))"
    payload = {
        "queries": [{"query": query}],
        "serializerSettings": {"includeNulls": True},
    }

    resp = _post_con_reintentos(url, headers, payload, timeout=config.POWERBI_API_TIMEOUT_S)
    resp.raise_for_status()

    data = resp.json()
    raw_value = data["results"][0]["tables"][0]["rows"][0]["[ultima_actualizacion]"]
    return pd.to_datetime(raw_value)


def _post_con_reintentos(
    url: str, headers: dict, payload: dict, timeout: int
) -> requests.Response:
    """
    Hace un POST a Power BI reintentando ante fallos transitorios.

    Reintenta ante errores de red/timeout (requests.RequestException) y ante
    respuestas HTTP 429/500/502/503/504. NO reintenta ante errores permanentes
    (400 DAX mal formado, 401 token, 403 permisos, 404).

    Args:
        url: Endpoint de executeQueries.
        headers: Cabeceras (incluye el Bearer token).
        payload: Cuerpo JSON de la consulta DAX.
        timeout: Timeout en segundos por intento.

    Returns:
        requests.Response: La respuesta (puede ser 4xx si no es reintentable).

    Raises:
        requests.RequestException: Si agota los reintentos.
    """
    intentos = max(1, config.POWERBI_RETRIES + 1)
    ultimo_error: Exception | None = None

    for intento in range(intentos):
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
            if resp.status_code in _RETRYABLE_STATUS and intento < intentos - 1:
                _esperar_backoff(intento)
                continue
            return resp
        except requests.RequestException as e:
            ultimo_error = e
            if intento < intentos - 1:
                _esperar_backoff(intento)
                continue
            raise

    if ultimo_error is not None:
        raise ultimo_error
    raise requests.RequestException("La consulta a Power BI fallo sin detalle")


_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})
"""Codigos HTTP que vale la pena reintentar (transitorios del lado de Power BI)."""


def _esperar_backoff(intento: int) -> None:
    """Espera exponencial: base, 2x base, 4x base..."""
    time.sleep(config.POWERBI_BACKOFF_S * (2 ** intento))


def _es_error_401(error: Exception) -> bool:
    """True si la excepcion es un 401 (token vencido) de la API de Power BI."""
    if isinstance(error, requests.HTTPError):
        resp = getattr(error, "response", None)
        if resp is not None and getattr(resp, "status_code", None) == 401:
            return True
        return "401" in str(error)
    return False


def consultar_tableros_en_paralelo(
    records: list[dict], access_token: str
) -> list[dict]:
    """
    Consulta todos los tableros en paralelo usando ThreadPoolExecutor.

    Cada tablero se consulta en un hilo independiente. Si uno falla, no
    afecta a los demas: el error se captura y se registra en el resultado.

    Args:
        records: Lista de diccionarios (uno por tablero del CSV).
        access_token: Token JWT de Azure AD.

    Returns:
        list[dict]: Resultados por tablero con estado, retraso, error, etc.
    """
    if not records:
        return []

    hora_consulta = pd.Timestamp.now()
    workers = max(1, min(config.MAX_WORKERS_POWERBI, len(records)))
    worker_fn = partial(
        _procesar_un_tablero,
        access_token=access_token,
        hora_consulta=hora_consulta,
    )

    with ThreadPoolExecutor(max_workers=workers) as executor:
        return list(executor.map(worker_fn, records))


def _consultar_con_renovacion(row_dict: dict, access_token: str) -> pd.Timestamp:
    """
    Consulta un tablero; si el token vencio (401), lo renueva y reintenta UNA vez.

    Evita que un token expirado a mitad de la corrida marque tableros en Error.

    Args:
        row_dict: Configuracion del tablero.
        access_token: Token actual (posiblemente vencido).

    Returns:
        pd.Timestamp: La fecha/hora mas reciente encontrada.

    Raises:
        Exception: El error original si no es 401, o el del reintento.
    """
    try:
        return consultar_tablero(row_dict, access_token)
    except Exception as e:
        if not _es_error_401(e):
            raise
        log_tablero_error(
            str(row_dict["tablero"]), "401: token vencido, renovando y reintentando"
        )
        token_nuevo = obtener_token()
        return consultar_tablero(row_dict, token_nuevo)


def _procesar_un_tablero(
    row_dict: dict, access_token: str, hora_consulta: pd.Timestamp
) -> dict:
    """
    Procesa un solo tablero: consulta Power BI y calcula su estado.

    Si la consulta falla, retorna una fila con estado 'Error' y el detalle
    del error, sin propagar la excepcion.

    Args:
        row_dict: Configuracion del tablero (del CSV).
        access_token: Token JWT.
        hora_consulta: Timestamp de inicio de la corrida.

    Returns:
        dict: Fila de resultado con tablero, estado, retraso, error, etc.
    """
    from src.estados import calcular_estado_y_fila

    try:
        ultima_actualizacion = _consultar_con_renovacion(row_dict, access_token)
        resultado = calcular_estado_y_fila(row_dict, hora_consulta, ultima_actualizacion)
        log_tablero_estado(
            str(row_dict["tablero"]),
            str(resultado["estado"]),
            float(resultado["retraso_min"]) if resultado["retraso_min"] == resultado["retraso_min"] else None,
            str(row_dict.get("critico", "0")) == "1",
        )
        return resultado
    except Exception as e:
        log_tablero_error(str(row_dict["tablero"]), str(e))
        return _fila_resultado_error(row_dict, hora_consulta, str(e))


def _fila_resultado_error(
    row_config: dict, hora_consulta: pd.Timestamp, mensaje_error: str
) -> dict:
    """Construye una fila de resultado para un tablero que fallo la consulta."""
    return {
        "tablero": row_config["tablero"],
        "critico": row_config["critico"],
        "estado": "Error",
        "ultima_actualizacion": pd.NaT,
        "hora_consulta": hora_consulta,
        "retraso_min": float("nan"),
        "error_detalle": mensaje_error,
    }