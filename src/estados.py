"""
estados.py - Calculo de estados y retrasos de los tableros.

Define la logica de negocio: a partir del retraso en minutos, asigna un
estado (OK, Advertencia, Demorado, Error). Los umbrales pueden venir del
CSV por tablero, o usar los valores por defecto de config.py como fallback.
"""
from __future__ import annotations

import pandas as pd

from src import config


def calcular_estado(retraso_min: float, ok_max: int = None, adv_max: int = None) -> str:
    """
    Asigna un estado segun el retraso en minutos.

    Si el tablero define sus propios umbrales en el CSV (ok_max, adv_max),
    se usan esos. Si no, se usan los globales de config.py.

    Args:
        retraso_min: Minutos transcurridos desde la ultima actualizacion.
        ok_max: Umbral maximo para OK (opcional, del CSV).
        adv_max: Umbral maximo para Advertencia (opcional, del CSV).

    Returns:
        str: "OK", "Advertencia", o "Demorado".
    """
    ok = ok_max if ok_max is not None else config.RETASO_OK_MAX_MIN
    adv = adv_max if adv_max is not None else config.RETASO_ADVERTENCIA_MAX_MIN

    if retraso_min <= ok:
        return "OK"
    if retraso_min <= adv:
        return "Advertencia"
    return "Demorado"


def calcular_estado_y_fila(
    row_config: dict, hora_consulta: pd.Timestamp, ultima_actualizacion: pd.Timestamp
) -> dict:
    """
    Calcula el retraso y el estado de un tablero y construye la fila de resultado.

    Lee los umbrales del CSV (frecuencia_objetivo_min, demorado_min) si estan
    disponibles, con fallback a los valores globales de config.py.

    Args:
        row_config: Fila del CSV con config del tablero.
        hora_consulta: Momento en que se ejecuto la consulta.
        ultima_actualizacion: Fecha maxima devuelta por Power BI.

    Returns:
        dict: Fila con tablero, critico, estado, fechas, retraso y error_detalle.
    """
    retraso_min = round(
        (hora_consulta - ultima_actualizacion).total_seconds() / 60, 2
    )

    ok_max = _leer_umbral(row_config, "frecuencia_objetivo_min")
    adv_max = _leer_umbral(row_config, "demorado_min")

    estado = calcular_estado(retraso_min, ok_max, adv_max)

    return {
        "tablero": row_config["tablero"],
        "critico": row_config["critico"],
        "estado": estado,
        "ultima_actualizacion": ultima_actualizacion,
        "hora_consulta": hora_consulta,
        "retraso_min": retraso_min,
        "error_detalle": "",
    }


def _leer_umbral(row_config: dict, columna: str) -> int | None:
    """
    Lee un umbral del CSV si esta presente y es valido.

    Args:
        row_config: Fila del CSV.
        columna: Nombre de la columna (frecuencia_objetivo_min o demorado_min).

    Returns:
        int | None: El valor del umbral, o None si no existe o no es valido.
    """
    valor = row_config.get(columna)
    if valor is None:
        return None
    try:
        return int(float(valor))
    except (TypeError, ValueError):
        return None


def ordenar_por_prioridad_estado(df: pd.DataFrame) -> pd.DataFrame:
    """
    Ordena el DataFrame: Error primero, luego Demorado, Advertencia, OK al final.
    Dentro de cada estado, ordena por retraso descendente (mas demorado arriba).

    Args:
        df: DataFrame con los resultados de todos los tableros.

    Returns:
        pd.DataFrame: DataFrame ordenado, sin la columna auxiliar.
    """
    if df.empty:
        return df
    df = df.copy()
    df["_prio_estado"] = df["estado"].map(config.ORDEN_ESTADO)
    return (
        df.sort_values(
            by=["_prio_estado", "retraso_min"],
            ascending=[True, False],
            na_position="last",
        )
        .drop(columns=["_prio_estado"])
        .reset_index(drop=True)
    )