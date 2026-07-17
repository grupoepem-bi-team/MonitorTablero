"""
cambios.py - Deteccion de cambios de estado entre corridas.

Compara el estado actual de los tableros con el snapshot anterior para
detectar transiciones (ej: OK -> Demorado). Estas transiciones son lo que
se muestra en la UI y lo que disparaba las notificaciones (eliminadas).
"""
from __future__ import annotations

import pandas as pd

from src import config


def detectar_cambios(
    df: pd.DataFrame, prev: dict[str, dict]
) -> list[tuple[str, str, str, bool]]:
    """
    Compara el estado actual con el snapshot anterior y detecta transiciones.

    Args:
        df: DataFrame con el estado actual de todos los tableros.
        prev: Diccionario {nombre_tablero: {"estado": "OK"}} del snapshot anterior.

    Returns:
        list[tuple]: Lista de cambios como (nombre, estado_anterior, estado_nuevo, es_critico).
    """
    if df.empty:
        return []
    cambios = []
    for _, row in df.iterrows():
        nombre = str(row["tablero"])
        nuevo = str(row["estado"])
        old_entry = prev.get(nombre)
        if not old_entry:
            continue
        anterior = str(old_entry.get("estado", ""))
        if anterior == nuevo:
            continue
        try:
            crit = int(float(row["critico"])) == 1
        except (TypeError, ValueError):
            crit = False
        cambios.append((nombre, anterior, nuevo, crit))
    return cambios


def texto_cambio(nombre: str, anterior: str, nuevo: str) -> str:
    """
    Genera un texto legible para mostrar un cambio de estado en la UI.

    Args:
        nombre: Nombre del tablero.
        anterior: Estado anterior.
        nuevo: Estado nuevo.

    Returns:
        str: Texto formateado en Markdown, ej: "**Facturacion** paso de OK a Demorado".
    """
    return f"**{nombre}** paso de {config.LABEL_ESTADO.get(anterior, anterior)} a {config.LABEL_ESTADO.get(nuevo, nuevo)}"