"""
worker.py - Orquestador de una corrida completa del monitor.

Ejecuta el flujo completo: auth -> consulta Power BI -> calcula estados ->
detecta cambios -> guarda JSON. Es el punto de entrada para el CLI y para
el boton "Actualizar ahora" del frontend.
"""
from __future__ import annotations

import time

import pandas as pd

from src import config
from src.auth import obtener_token
from src.cambios import detectar_cambios, texto_cambio
from src.estados import ordenar_por_prioridad_estado
from src.logger import get_logger, log_corrida_inicio, log_corrida_fin
from src.persistencia import (
    append_corrida_historico,
    cargar_snapshot,
    guardar_cambios_recientes,
    guardar_estado_actual,
    guardar_meta_corrida,
    guardar_snapshot,
    leer_meta_corrida,
)
from src.powerbi import consultar_tableros_en_paralelo

log = get_logger(__name__)


def ejecutar_corrida(path_csv: str | None = None) -> None:
    """
    Ejecuta una corrida completa del monitor de principio a fin.

    Flujo:
        1. Obtiene token de Azure AD
        2. Lee config_tableros.csv y filtra los activos
        3. Consulta Power BI en paralelo (12 hilos max)
        4. Calcula estados y retrasos
        5. Compara con snapshot anterior para detectar cambios
        6. Guarda snapshot, estado actual, cambios recientes y metadata

    Args:
        path_csv: Ruta alternativa al CSV de config (opcional).

    Raises:
        RuntimeError: Si no se puede obtener el token de Azure AD.
    """
    t0 = time.perf_counter()
    path_csv = path_csv or config.CONFIG_TABLEROS_CSV

    # 1. Autenticacion
    try:
        token = obtener_token()
        log.info("Token de Azure AD obtenido OK")
    except Exception as e:
        log.critical("No se pudo obtener token: %s", e)
        raise

    # 2. Cargar configuracion de tableros
    config_df = pd.read_csv(path_csv, sep=";")
    config_df = config_df[config_df["activo"] == 1].copy()
    records = config_df.to_dict("records")
    log_corrida_inicio(len(records))

    # 3-4. Consultar y calcular estados (en paralelo)
    if not records:
        df = ordenar_por_prioridad_estado(pd.DataFrame())
    else:
        resultados = consultar_tableros_en_paralelo(records, token)
        df = ordenar_por_prioridad_estado(pd.DataFrame(resultados))

    # 5. Detectar cambios vs snapshot anterior
    prev = cargar_snapshot()
    cambios = detectar_cambios(df, prev)
    lineas_cambios = [texto_cambio(a, b, c) for a, b, c, _ in cambios]
    lineas_fallos: list[str] = []

    # 6. Persistir resultados
    try:
        guardar_snapshot(df)
    except OSError as e:
        lineas_fallos.append(f"Snapshot local: {e}")
        log.error("No se pudo guardar snapshot: %s", e)

    try:
        guardar_cambios_recientes(lineas_cambios, lineas_fallos)
    except OSError as e:
        lineas_fallos.append(f"Cambios recientes: {e}")
        log.error("No se pudo guardar cambios recientes: %s", e)

    try:
        guardar_estado_actual(df)
    except OSError as e:
        lineas_fallos.append(f"Estado actual: {e}")
        log.error("No se pudo guardar estado actual: %s", e)

    dur = time.perf_counter() - t0
    guardar_meta_corrida(
        exito=True,
        duracion_s=dur,
        n_tableros=len(df),
        n_cambios=len(cambios),
    )

    # Guardar entrada en historico (append-only)
    try:
        meta_h = {"duracion_s": dur, "exito": True, "n_cambios_estado": len(cambios)}
        append_corrida_historico(df, meta_h)
    except OSError as e:
        log.error("No se pudo agregar entrada al historico: %s", e)

    # Log de salud: contar estados
    if not df.empty:
        conteo = df["estado"].value_counts().to_dict()
        log_corrida_fin(
            n_tableros=len(df),
            n_ok=int(conteo.get("OK", 0)),
            n_advertencia=int(conteo.get("Advertencia", 0)),
            n_demorado=int(conteo.get("Demorado", 0)),
            n_error=int(conteo.get("Error", 0)),
            duracion_s=dur,
            n_cambios=len(cambios),
        )


def ejecutar_corrida_con_manejo_error(path_csv: str | None = None) -> tuple[bool, str | None]:
    """
    Ejecuta una corrida capturando excepciones. Para uso desde CLI.

    Si la corrida falla, registra el error en la metadata pero no borra
    el estado_actual.json anterior (el frontend sigue mostrando el ultimo
    estado valido).

    Args:
        path_csv: Ruta alternativa al CSV de config (opcional).

    Returns:
        tuple: (exito, mensaje_error). mensaje_error es None si todo OK.
    """
    try:
        ejecutar_corrida(path_csv)
        return True, None
    except Exception as e:
        msg = str(e)
        log.critical("Corrida fallo: %s", msg)
        guardar_meta_corrida(
            exito=False,
            duracion_s=0,
            n_tableros=0,
            n_cambios=0,
            error=msg,
        )
        return False, msg


def main(argv: list[str] | None = None) -> int:
    """
    Entry point para uso como CLI: python -m src.worker

    Returns:
        int: 0 si exito, 1 si error.
    """
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Monitor Power BI -> JSON")
    parser.add_argument(
        "--config",
        default=None,
        help="Ruta a config_tableros.csv (por defecto: junto al proyecto)",
    )
    args = parser.parse_args(argv)

    ok, err = ejecutar_corrida_con_manejo_error(args.config)
    if ok:
        meta = leer_meta_corrida()
        print(
            "Corrida OK -",
            meta.get("n_tableros", 0),
            "tableros -",
            meta.get("n_cambios_estado", 0),
            "cambios de estado -",
            f"{meta.get('duracion_s', 0)} s",
        )
        return 0
    print(f"Error: {err}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())