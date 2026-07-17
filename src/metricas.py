"""
metricas.py - Metricas derivadas para el tablero de control de actualizacion.

Calcula KPIs y rankings a partir del DataFrame de estado actual + config CSV
+ historico de corridas. No consulta APIs externas: todo se deriva de los
datos que el worker ya persistio en disco.
"""
from __future__ import annotations

import math
from collections import defaultdict

import pandas as pd

from src import config


# ---------------------------------------------------------------------------
# Helpers de formato
# ---------------------------------------------------------------------------


def formatear_hace(retraso_min: float) -> str:
    """
    Convierte minutos de retraso a texto humano compacto.

    Ej: 25 -> "25min", 90 -> "1h 30m", 1500 -> "1 dia 1h", 542944 -> "378 dias".

    Args:
        retraso_min: Minutos de retraso (puede ser NaN).

    Returns:
        str: Texto humano, o "--" si es NaN/None.
    """
    if retraso_min is None or (isinstance(retraso_min, float) and math.isnan(retraso_min)):
        return "--"
    m = float(retraso_min)
    if m < 0:
        return "0min"
    if m < 60:
        return f"{int(m)}min"
    if m < 1440:
        h = int(m / 60)
        mm = int(m % 60)
        return f"{h}h {mm}m" if mm > 0 else f"{h}h"
    dias = int(m / 1440)
    resto_h = int((m % 1440) / 60)
    if dias == 1:
        return f"1 dia {resto_h}h" if resto_h > 0 else "1 dia"
    return f"{dias} dias" if resto_h == 0 else f"{dias} dias {resto_h}h"


# ---------------------------------------------------------------------------
# Metricas de resumen global
# ---------------------------------------------------------------------------


def calcular_resumen(df: pd.DataFrame) -> dict:
    """
    Calcula KPIs globales a partir del DataFrame de estado.

    Args:
        df: DataFrame con columnas tablero, critico, estado, retraso_min.

    Returns:
        dict: total, n_ok, n_advertencia, n_demorado, n_error,
              pct_ok, pct_problema, n_criticos, n_criticos_riesgo,
              promedio_retraso (excluyendo >7 dias), retraso_max.
    """
    if df.empty:
        return _resumen_vacio()

    conteo = df["estado"].value_counts().to_dict()
    total = len(df)
    n_ok = int(conteo.get("OK", 0))
    n_adv = int(conteo.get("Advertencia", 0))
    n_dem = int(conteo.get("Demorado", 0))
    n_err = int(conteo.get("Error", 0))

    criticos = df[df["critico"].astype(str).isin(["1", "1.0"])]
    n_criticos = len(criticos)
    n_criticos_riesgo = len(criticos[criticos["estado"].isin(
        ["Advertencia", "Demorado", "Error"]
    )])

    # Promedio excluyendo outliers > 7 dias (10080 min)
    retr_validos = df["retraso_min"].dropna()
    sin_outliers = retr_validos[retr_validos < 10080]
    promedio = round(float(sin_outliers.mean()), 1) if not sin_outliers.empty else 0.0

    retr_max = float(retr_validos.max()) if not retr_validos.empty else 0.0

    return {
        "total": total,
        "n_ok": n_ok,
        "n_advertencia": n_adv,
        "n_demorado": n_dem,
        "n_error": n_err,
        "pct_ok": round(100 * n_ok / total, 1) if total > 0 else 0,
        "pct_problema": round(100 * (n_adv + n_dem + n_err) / total, 1) if total > 0 else 0,
        "n_criticos": n_criticos,
        "n_criticos_riesgo": n_criticos_riesgo,
        "promedio_retraso": promedio,
        "retraso_max": retr_max,
    }


def _resumen_vacio() -> dict:
    return {
        "total": 0, "n_ok": 0, "n_advertencia": 0, "n_demorado": 0, "n_error": 0,
        "pct_ok": 0, "pct_problema": 0, "n_criticos": 0, "n_criticos_riesgo": 0,
        "promedio_retraso": 0, "retraso_max": 0,
    }


# ---------------------------------------------------------------------------
# Rankings
# ---------------------------------------------------------------------------


def ranking_atraso(df: pd.DataFrame, objetivo_min: float = None, top_n: int = 10) -> list[dict]:
    """
    Ranking de tableros mas atrasados por ratio retraso/objetivo.

    Args:
        df: DataFrame de estado.
        objetivo_min: Objetivo en minutos (default: config.RETASO_OK_MAX_MIN).
        top_n: Cuantos devolver.

    Returns:
        list[dict]: [{tablero, critico, estado, retraso_min, ratio, hace}], ordenado desc.
    """
    if objetivo_min is None:
        objetivo_min = config.RETASO_OK_MAX_MIN
    if df.empty:
        return []
    d = df.copy()
    d["ratio"] = d["retraso_min"] / objetivo_min
    d = d.dropna(subset=["retraso_min"]).sort_values("ratio", ascending=False).head(top_n)
    out = []
    for _, r in d.iterrows():
        out.append({
            "tablero": str(r["tablero"]),
            "critico": int(float(r["critico"])) if _es_num(r["critico"]) else 0,
            "estado": str(r["estado"]),
            "retraso_min": round(float(r["retraso_min"]), 1),
            "ratio": round(float(r["ratio"]), 1),
            "hace": formatear_hace(float(r["retraso_min"])),
        })
    return out


def ranking_constantes(df: pd.DataFrame, top_n: int = 5) -> list[dict]:
    """
    Ranking de tableros mas constantes (menor retraso, excluyendo Error).

    Args:
        df: DataFrame de estado.
        top_n: Cuantos devolver.

    Returns:
        list[dict]: [{tablero, critico, estado, retraso_min, hace}], ordenado asc.
    """
    if df.empty:
        return []
    d = df[(df["estado"] == "OK") & df["retraso_min"].notna()].copy()
    if d.empty:
        return []
    d = d.sort_values("retraso_min", ascending=True).head(top_n)
    out = []
    for _, r in d.iterrows():
        out.append({
            "tablero": str(r["tablero"]),
            "critico": int(float(r["critico"])) if _es_num(r["critico"]) else 0,
            "retraso_min": round(float(r["retraso_min"]), 1),
            "hace": formatear_hace(float(r["retraso_min"])),
        })
    return out


def criticos_en_riesgo(df: pd.DataFrame) -> list[dict]:
    """
    Lista de tableros criticos en Advertencia/Demorado/Error.

    Returns:
        list[dict]: [{tablero, estado, retraso_min, hace}], ordenado por retraso desc.
    """
    if df.empty:
        return []
    d = df[
        (df["critico"].astype(str).isin(["1", "1.0"]))
        & (df["estado"].isin(["Advertencia", "Demorado", "Error"]))
    ].copy()
    if d.empty:
        return []
    d = d.sort_values("retraso_min", ascending=False, na_position="last")
    out = []
    for _, r in d.iterrows():
        rm = r["retraso_min"]
        out.append({
            "tablero": str(r["tablero"]),
            "estado": str(r["estado"]),
            "retraso_min": None if pd.isna(rm) else round(float(rm), 1),
            "hace": formatear_hace(rm),
        })
    return out


# ---------------------------------------------------------------------------
# Metricas con historico (tendencia + fiabilidad)
# ---------------------------------------------------------------------------


def calcular_tendencia(historico: list[dict]) -> dict[str, dict]:
    """
    Calcula la tendencia de cada tablero comparando el retraso actual
    con el de la corrida anterior.

    Args:
        historico: Lista de entradas de leer_historico().

    Returns:
        dict: {nombre_tablero: {"retraso_anterior": float, "retraso_actual": float,
                "delta": float, "direccion": "mejora"|"empeora"|"estable"}}
    """
    if len(historico) < 2:
        return {}
    ultima = historico[-1]
    anteultima = historico[-2]
    actual_map = {t["tablero"]: t for t in ultima.get("tableros", [])}
    prev_map = {t["tablero"]: t for t in anteultima.get("tableros", [])}

    out = {}
    for nombre, t_actual in actual_map.items():
        t_prev = prev_map.get(nombre)
        if not t_prev:
            continue
        r_actual = t_actual.get("retraso_min")
        r_prev = t_prev.get("retraso_min")
        if r_actual is None or r_prev is None:
            continue
        delta = round(r_actual - r_prev, 1)
        if abs(delta) < 1:
            direccion = "estable"
        elif delta > 0:
            direccion = "empeora"
        else:
            direccion = "mejora"
        out[nombre] = {
            "retraso_anterior": round(r_prev, 1),
            "retraso_actual": round(r_actual, 1),
            "delta": delta,
            "direccion": direccion,
        }
    return out


def calcular_fiabilidad(historico: list[dict]) -> dict[str, dict]:
    """
    Calcula la fiabilidad de cada tablero: % de corridas en OK.

    Args:
        historico: Lista de entradas de leer_historico().

    Returns:
        dict: {nombre: {"n_corridas": int, "n_ok": int, "pct_ok": float,
                "dias_consecutivos_demorado": int}}
    """
    if not historico:
        return {}
    por_tablero: dict[str, list[str]] = defaultdict(list)
    for entrada in historico:
        for t in entrada.get("tableros", []):
            nombre = t.get("tablero")
            if nombre:
                por_tablero[nombre].append(t.get("estado", ""))

    out = {}
    for nombre, estados in por_tablero.items():
        n = len(estados)
        n_ok = sum(1 for e in estados if e == "OK")
        # Dias consecutivos demorado: contar desde el final
        consec = 0
        for e in reversed(estados):
            if e in ("Demorado", "Error"):
                consec += 1
            else:
                break
        out[nombre] = {
            "n_corridas": n,
            "n_ok": n_ok,
            "pct_ok": round(100 * n_ok / n, 1) if n > 0 else 0,
            "dias_consecutivos_demorado": consec,
        }
    return out


# ---------------------------------------------------------------------------
# Enriquecer DataFrame para la tabla
# ---------------------------------------------------------------------------


def enriquecer_tableros(df: pd.DataFrame, objetivo_min: float = None) -> list[dict]:
    """
    Agrega ratio y hace a cada tablero para mostrar en la tabla.

    Returns:
        list[dict]: Una entrada por tablero con todos los campos + ratio + hace.
    """
    if objetivo_min is None:
        objetivo_min = config.RETASO_OK_MAX_MIN
    if df.empty:
        return []
    out = []
    for _, r in df.iterrows():
        rm = r["retraso_min"]
        rm_val = float(rm) if not pd.isna(rm) else None
        out.append({
            "tablero": str(r["tablero"]),
            "critico": int(float(r["critico"])) if _es_num(r["critico"]) else 0,
            "estado": str(r["estado"]),
            "ultima_actualizacion": None if pd.isna(r["ultima_actualizacion"])
            else str(r["ultima_actualizacion"]),
            "hora_consulta": str(r["hora_consulta"]) if not pd.isna(r["hora_consulta"]) else "",
            "retraso_min": rm_val,
            "ratio": round(rm_val / objetivo_min, 1) if rm_val is not None else None,
            "hace": formatear_hace(rm),
            "error_detalle": str(r.get("error_detalle") or ""),
        })
    return out


# ---------------------------------------------------------------------------
# Metricas completas para el frontend
# ---------------------------------------------------------------------------


def calcular_metricas_completas(
    df: pd.DataFrame,
    historico: list[dict] | None = None,
    objetivo_min: float = None,
) -> dict:
    """
    Calcula todas las metricas que el frontend necesita en una sola llamada.

    Args:
        df: DataFrame de estado actual.
        historico: Lista de entradas de leer_historico() (opcional).
        objetivo_min: Objetivo en minutos (default: config.RETASO_OK_MAX_MIN).

    Returns:
        dict: {
            resumen: {...},
            ranking_atraso: [...],
            ranking_constantes: [...],
            criticos_riesgo: [...],
            tendencia: {...},
            fiabilidad: {...},
            tableros: [...],
        }
    """
    if objetivo_min is None:
        objetivo_min = config.RETASO_OK_MAX_MIN
    historico = historico or []
    return {
        "resumen": calcular_resumen(df),
        "ranking_atraso": ranking_atraso(df, objetivo_min),
        "ranking_constantes": ranking_constantes(df),
        "criticos_riesgo": criticos_en_riesgo(df),
        "tendencia": calcular_tendencia(historico),
        "fiabilidad": calcular_fiabilidad(historico),
        "tableros": enriquecer_tableros(df, objetivo_min),
    }


# ---------------------------------------------------------------------------
# Helper interno
# ---------------------------------------------------------------------------


def _es_num(val) -> bool:
    """True si el valor se puede convertir a float."""
    try:
        float(val)
        return True
    except (TypeError, ValueError):
        return False