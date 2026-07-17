"""
persistencia.py - Lectura y escritura de archivos JSON en disco.

Centraliza toda la persistencia del sistema: estado actual, snapshot anterior,
cambios recientes y metadata de corrida. Todas las escrituras son atomicas
(.tmp + copy + remove) para garantizar que nunca quede un JSON corrupto.
Compatible con bind mounts de Docker donde os.replace puede fallar con
Errno 16 (Device or resource busy).
"""
from __future__ import annotations

import json
import os
import shutil

import pandas as pd

from src import config


# ---------------------------------------------------------------------------
# Escritura atomica
# ---------------------------------------------------------------------------


def _atomic_write_json(path: str, data: dict) -> None:
    """
    Escribe un JSON a disco de forma atomica.

    Primero escribe a un archivo .tmp, luego copia sobre el destino y
    borra el .tmp. Usa shutil.copy en lugar de os.replace porque
    os.replace (rename) falla con ENODEV/EBUSY sobre bind mounts de
    archivos individuales en Docker.

    Args:
        path: Ruta destino del JSON.
        data: Diccionario a serializar.
    """
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    shutil.copy(tmp, path)
    os.remove(tmp)


# ---------------------------------------------------------------------------
# Snapshot de estados (para detectar cambios)
# ---------------------------------------------------------------------------


def cargar_snapshot(path: str | None = None) -> dict[str, dict]:
    """
    Lee el snapshot anterior de estados desde disco.

    Args:
        path: Ruta del snapshot. Si es None, usa config.SNAPSHOT_ESTADOS_JSON.

    Returns:
        dict: {nombre_tablero: {"estado": "OK"}} o {} si no existe o falla.
    """
    if path is None:
        path = config.SNAPSHOT_ESTADOS_JSON
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        raw = data.get("by_tablero") or {}
        out: dict[str, dict] = {}
        for nombre, info in raw.items():
            if isinstance(info, dict) and "estado" in info:
                out[str(nombre)] = {"estado": str(info["estado"])}
            elif isinstance(info, str):
                out[str(nombre)] = {"estado": info}
        return out
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return {}


def guardar_snapshot(df: pd.DataFrame, path: str | None = None) -> None:
    """
    Guarda el estado actual como snapshot para la proxima corrida.

    Args:
        df: DataFrame con los resultados de la corrida.
        path: Ruta del archivo de snapshot. Si es None, usa config.SNAPSHOT_ESTADOS_JSON.
    """
    if path is None:
        path = config.SNAPSHOT_ESTADOS_JSON
    by_tablero = {
        str(r["tablero"]): {"estado": str(r["estado"])}
        for _, r in df.iterrows()
    }
    _atomic_write_json(
        path,
        {
            "version": 1,
            "updated_at": pd.Timestamp.now().isoformat(),
            "by_tablero": by_tablero,
        },
    )


# ---------------------------------------------------------------------------
# Estado actual (lo lee el frontend)
# ---------------------------------------------------------------------------


def guardar_estado_actual(df: pd.DataFrame, path: str | None = None) -> None:
    """
    Serializa el DataFrame de resultados a JSON para que el frontend lo lea.

    Convierte timestamps a ISO strings y NaN a None para compatibilidad JSON.

    Args:
        df: DataFrame con los resultados de todos los tableros.
        path: Ruta del archivo de estado. Si es None, usa config.ESTADO_ACTUAL_JSON.
    """
    if path is None:
        path = config.ESTADO_ACTUAL_JSON
    tableros = []
    for _, row in df.iterrows():
        ua = row["ultima_actualizacion"]
        hc = row["hora_consulta"]
        rm = row["retraso_min"]
        try:
            crit = int(float(row["critico"]))
        except (TypeError, ValueError):
            crit = 0
        tableros.append(
            {
                "tablero": str(row["tablero"]),
                "critico": crit,
                "estado": str(row["estado"]),
                "ultima_actualizacion": None if pd.isna(ua) else pd.Timestamp(ua).isoformat(),
                "hora_consulta": pd.Timestamp(hc).isoformat(),
                "retraso_min": None if pd.isna(rm) else float(rm),
                "error_detalle": str(row.get("error_detalle") or ""),
            }
        )
    _atomic_write_json(
        path,
        {
            "version": 1,
            "updated_at": pd.Timestamp.now().isoformat(),
            "tableros": tableros,
        },
    )


def cargar_estado_actual(path: str | None = None) -> pd.DataFrame | None:
    """
    Lee el estado actual desde disco y lo reconstruye como DataFrame.

    Args:
        path: Ruta del archivo. Si es None, usa config.ESTADO_ACTUAL_JSON.

    Returns:
        pd.DataFrame | None: DataFrame con los tableros, o None si no existe
        o el JSON esta corrupto.
    """
    if path is None:
        path = config.ESTADO_ACTUAL_JSON
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError, TypeError):
        return None
    rows = data.get("tableros")
    if not isinstance(rows, list):
        return None

    from src.estados import ordenar_por_prioridad_estado

    if not rows:
        return ordenar_por_prioridad_estado(pd.DataFrame())

    recs = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        ua = r.get("ultima_actualizacion")
        hc = r.get("hora_consulta")
        rm = r.get("retraso_min")
        recs.append(
            {
                "tablero": r.get("tablero", ""),
                "critico": r.get("critico", 0),
                "estado": r.get("estado", ""),
                "ultima_actualizacion": pd.NaT if ua is None else pd.to_datetime(ua, utc=False),
                "hora_consulta": pd.to_datetime(hc, utc=False) if hc else pd.NaT,
                "retraso_min": float("nan") if rm is None else float(rm),
                "error_detalle": str(r.get("error_detalle") or ""),
            }
        )
    return ordenar_por_prioridad_estado(pd.DataFrame(recs))


# ---------------------------------------------------------------------------
# Cambios recientes (lo lee el frontend)
# ---------------------------------------------------------------------------


def guardar_cambios_recientes(
    lineas_cambios: list[str], lineas_fallos: list[str]
) -> None:
    """
    Guarda las transiciones de estado detectadas para mostrar en la UI.

    Args:
        lineas_cambios: Lista de textos Markdown con los cambios.
        lineas_fallos: Lista de textos con errores de persistencia.
    """
    _atomic_write_json(
        config.CAMBIOS_RECIENTES_JSON,
        {
            "version": 1,
            "corrida_finalizada_at": pd.Timestamp.now().isoformat(),
            "lineas_cambios_ui": lineas_cambios,
            "lineas_fallos": lineas_fallos,
            "hubo_cambios": bool(lineas_cambios),
        },
    )


def leer_cambios_recientes(path: str | None = None) -> tuple[list[str], list[str]]:
    """
    Lee los cambios recientes desde disco.

    Args:
        path: Ruta del archivo. Si es None, usa config.CAMBIOS_RECIENTES_JSON.

    Returns:
        tuple: (lineas_cambios, lineas_fallos), listas vacias si no existe.
    """
    if path is None:
        path = config.CAMBIOS_RECIENTES_JSON
    if not os.path.isfile(path):
        return [], []
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        lc = data.get("lineas_cambios_ui") or []
        lf = data.get("lineas_fallos") or []
        return [str(x) for x in (lc if isinstance(lc, list) else [])], [
            str(x) for x in (lf if isinstance(lf, list) else [])
        ]
    except (OSError, json.JSONDecodeError, TypeError):
        return [], []


# ---------------------------------------------------------------------------
# Metadata de corrida (lo lee el frontend)
# ---------------------------------------------------------------------------


def guardar_meta_corrida(
    exito: bool,
    duracion_s: float,
    n_tableros: int,
    n_cambios: int,
    error: str | None = None,
) -> None:
    """
    Guarda metadata de la ultima corrida para mostrar en la UI.

    Args:
        exito: Si la corrida termino bien.
        duracion_s: Duracion en segundos.
        n_tableros: Cantidad de tableros consultados.
        n_cambios: Cantidad de cambios de estado detectados.
        error: Mensaje de error si fallo, None si exito.
    """
    _atomic_write_json(
        config.CORRIDA_MONITOR_META_JSON,
        {
            "version": 1,
            "ultima_corrida_fin": pd.Timestamp.now().isoformat(),
            "duracion_s": round(duracion_s, 3),
            "exito": exito,
            "error": error,
            "n_tableros": n_tableros,
            "n_cambios_estado": n_cambios,
        },
    )


def leer_meta_corrida(path: str | None = None) -> dict:
    """
    Lee la metadata de la ultima corrida.

    Args:
        path: Ruta del archivo. Si es None, usa config.CORRIDA_MONITOR_META_JSON.

    Returns:
        dict: Metadata con exito, duracion, n_tableros, etc. Vacia si no existe.
    """
    if path is None:
        path = config.CORRIDA_MONITOR_META_JSON
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError, TypeError):
        return {}


# ---------------------------------------------------------------------------
# Historico de corridas (append-only, una linea JSON por corrida)
# ---------------------------------------------------------------------------


def append_corrida_historico(df: pd.DataFrame, meta: dict) -> None:
    """
    Agrega una entrada al historico de corridas (formato JSONL).

    Cada linea contiene: timestamp, duracion_s, exito, y por cada tablero su
    estado y retraso_min. Si el archivo supera HISTORICO_MAX_CORRIDAS lineas,
    se truncan las mas antiguas.

    Args:
        df: DataFrame con los resultados de la corrida.
        meta: Metadata de la corrida (exito, duracion_s, n_cambios, etc.).
    """
    entrada = {
        "ts": pd.Timestamp.now().isoformat(),
        "duracion_s": meta.get("duracion_s", 0),
        "exito": meta.get("exito", True),
        "n_cambios": meta.get("n_cambios_estado", 0),
        "tableros": [],
    }
    for _, r in df.iterrows():
        rm = r["retraso_min"]
        entrada["tableros"].append({
            "tablero": str(r["tablero"]),
            "estado": str(r["estado"]),
            "critico": int(float(r["critico"])) if str(r["critico"]).replace(".", "").isdigit() else 0,
            "retraso_min": None if pd.isna(rm) else float(rm),
        })

    path = config.HISTORICO_CORRIDAS_JSONL
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entrada, ensure_ascii=False) + "\n")

    _truncar_historico(path)


def _truncar_historico(path: str) -> None:
    """Si el historico supera el maximo, elimina las lineas mas antiguas."""
    maximo = config.HISTORICO_MAX_CORRIDAS
    try:
        with open(path, encoding="utf-8") as f:
            lineas = f.readlines()
    except OSError:
        return
    if len(lineas) <= maximo:
        return
    lineas = lineas[-maximo:]
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.writelines(lineas)
    shutil.copy(tmp, path)
    os.remove(tmp)


def leer_historico(path: str | None = None, ultimas_n: int = 0) -> list[dict]:
    """
    Lee el historico de corridas.

    Args:
        path: Ruta del archivo. Si es None, usa config.HISTORICO_CORRIDAS_JSONL.
        ultimas_n: Si > 0, devuelve solo las ultimas N corridas.

    Returns:
        list[dict]: Lista de entradas, de la mas antigua a la mas reciente.
    """
    if path is None:
        path = config.HISTORICO_CORRIDAS_JSONL
    if not os.path.isfile(path):
        return []
    try:
        with open(path, encoding="utf-8") as f:
            lineas = f.readlines()
    except OSError:
        return []
    if ultimas_n > 0:
        lineas = lineas[-ultimas_n:]
    out = []
    for linea in lineas:
        linea = linea.strip()
        if not linea:
            continue
        try:
            out.append(json.loads(linea))
        except (json.JSONDecodeError, TypeError):
            continue
    return out


def cargar_datos_para_frontend() -> tuple[
    pd.DataFrame | None, list[str], list[str], dict, str | None
]:
    """
    Carga todo lo que el frontend necesita en una sola llamada.

    Lee estado_actual.json, cambios_recientes.json y corrida_monitor_meta.json.

    Returns:
        tuple: (df, lineas_cambios, lineas_fallos, meta, mensaje_error).
        df es None si no hay estado guardado. mensaje_error es None si todo OK.
    """
    meta = leer_meta_corrida()
    lc, lf = leer_cambios_recientes()
    df = cargar_estado_actual()
    if df is None:
        return (
            None,
            lc,
            lf,
            meta,
            "No se encontro estado_actual.json o esta corrupto. "
            "Ejecuta el worker: python -m src.worker",
        )
    return df, lc, lf, meta, None