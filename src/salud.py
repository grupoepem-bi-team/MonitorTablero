"""
salud.py - Salud del propio monitor (meta-vigilancia).

El monitor vigila la frescura de los tableros de Power BI. Este modulo vigila
al monitor: con que datos puede confiar el usuario.

Responde a las preguntas:
  - ¿La ultima corrida fue exitosa?
  - ¿Fue hace poco (fresca) o hace demasiado (desactualizada / caida)?

Se usa en dos lugares:
  1. El endpoint /healthz (para que Docker sepa si el pipeline esta sano de verdad).
  2. La franja de salud de la UI (para que el usuario no confie en datos viejos).

NO envia alertas todavia: el aviso por Telegram (Fase 3) queda para mas adelante.
"""
from __future__ import annotations

from datetime import datetime

from src import config

# Codigos de salud (el frontend los mapea a colores)
OK = "ok"
DESACTUALIZADO = "desactualizado"
CAIDO = "caido"
SIN_DATOS = "sin_datos"


def edad_minutos(ts_iso: str | None) -> float | None:
    """
    Edad en minutos de un timestamp ISO, o None si no se puede calcular.

    Se calcula contra la hora local (los JSON se escriben con hora local).
    """
    if not ts_iso:
        return None
    try:
        t = datetime.fromisoformat(str(ts_iso))
    except (TypeError, ValueError):
        return None
    # Restar la tzinfo si vino con zona, porque comparamos contra now() local
    if t.tzinfo is not None:
        t = t.replace(tzinfo=None)
    delta = datetime.now() - t
    return round(delta.total_seconds() / 60, 1)


def calcular_salud(meta: dict | None) -> dict:
    """
    Evalua la salud del monitor a partir de la meta de la ultima corrida.

    Args:
        meta: Contenido de corrida_monitor_meta.json (o {} / None).

    Returns:
        dict: {
            "codigo": "ok" | "desactualizado" | "caido" | "sin_datos",
            "exito": bool,
            "edad_min": float | None,
            "ultima_corrida_fin": str | None,
            "error": str | None,
        }
    """
    meta = meta or {}
    fin = meta.get("ultima_corrida_fin")
    exito = bool(meta.get("exito"))
    edad = edad_minutos(fin)

    if fin is None or edad is None:
        return {
            "codigo": SIN_DATOS,
            "exito": exito,
            "edad_min": None,
            "ultima_corrida_fin": fin,
            "error": meta.get("error"),
        }

    if not exito:
        codigo = CAIDO
    elif edad >= config.SALUD_CAIDO_MIN:
        codigo = CAIDO
    elif edad >= config.SALUD_FRESCURA_MIN:
        codigo = DESACTUALIZADO
    else:
        codigo = OK

    return {
        "codigo": codigo,
        "exito": exito,
        "edad_min": edad,
        "ultima_corrida_fin": fin,
        "error": meta.get("error"),
    }


def esta_sano(salud: dict) -> bool:
    """True si el monitor esta sano (healthcheck 200). NO usa el detalle de la corrida."""
    return salud.get("codigo") in (OK, DESACTUALIZADO)
