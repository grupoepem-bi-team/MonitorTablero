"""
scheduler.py - Ejecuta el worker del monitor cada N minutos en loop infinito.

Se puede correr solo:
    python -m src.scheduler

O junto con el frontend desde DashboardControl.bat.

El intervalo por defecto es 30 minutos. Se puede cambiar con:
    SCHEDULER_INTERVAL_MIN=15  (en .env o variable de entorno)

Si una corrida tarda mas que el intervalo, la siguiente espera a que termine.
Los errores no frenan el scheduler: se loguean y se sigue iterando.
"""
from __future__ import annotations

import os
import signal
import sys
import time
import traceback

from src import config
from src.logger import get_logger
from src.worker import ejecutar_corrida_con_manejo_error

log = get_logger("scheduler")

_running = True
"""Flag para detener el scheduler limpiamente con Ctrl+C."""


def _handle_sigint(sig, frame):
    """Handler para Ctrl+C que detiene el scheduler sin error."""
    global _running
    _running = False
    log.info("Senal de detencion recibida (Ctrl+C), cerrando scheduler...")


def _get_interval() -> int:
    """Lee el intervalo del scheduler desde .env o usa 30 min por defecto."""
    return config.env_int("SCHEDULER_INTERVAL_MIN", 30)


def run() -> int:
    """
    Loop principal del scheduler. Corre el worker cada N minutos.

    Returns:
        int: 0 si se detuvo limpiamente, 1 si hubo error fatal.
    """
    interval_min = _get_interval()
    interval_s = interval_min * 60

    log.info("Scheduler iniciado - intervalo=%d min", interval_min)
    print(f"Scheduler iniciado - corrida cada {interval_min} minutos.")
    print(f"Presiona Ctrl+C para detener.")
    print()

    signal.signal(signal.SIGINT, _handle_sigint)

    corrida_n = 0
    while _running:
        corrida_n += 1
        t0 = time.perf_counter()

        log.info("--- Scheduler: corrida #%d ---", corrida_n)
        print(f"[{time.strftime('%H:%M:%S')}] Corrida #{corrida_n}...")

        try:
            ok, err = ejecutar_corrida_con_manejo_error()
            if ok:
                log.info("Scheduler: corrida #%d OK", corrida_n)
            else:
                log.error("Scheduler: corrida #%d fallo: %s", corrida_n, err)
        except Exception as e:
            log.error("Scheduler: excepcion no capturada en corrida #%d: %s", corrida_n, e)
            log.debug("Traceback: %s", traceback.format_exc())

        if not _running:
            break

        # Calcular cuanto esperar (si la corrida tardo mas que el intervalo, no esperar)
        duracion = time.perf_counter() - t0
        espera = max(0, interval_s - duracion)

        log.info("Scheduler: proxima corrida en %.0f segundos", espera)

        # Esperar en bloques de 1s para poder responder a Ctrl+C rapidamente
        while _running and espera > 0:
            time.sleep(1)
            espera -= 1

    log.info("Scheduler detenido")
    print("\nScheduler detenido.")
    return 0


def main() -> int:
    return run()


if __name__ == "__main__":
    raise SystemExit(main())