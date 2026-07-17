"""
server.py - Servidor FastAPI del dashboard.

Sirve la pagina HTML del dashboard y los endpoints de API que leen los JSON
generados por el worker. Tambien permite lanzar una corrida manual del worker
desde el boton "Actualizar ahora".

Uso:
    uvicorn frontend.server:app --host 0.0.0.0 --port 8501
"""
from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from src import config
from src.logger import get_logger, log_frontend
from src.persistencia import cargar_datos_para_frontend, leer_historico
from src.metricas import calcular_metricas_completas

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Configuracion de rutas del frontend
# ---------------------------------------------------------------------------

_FRONTEND_DIR = Path(__file__).parent
_STATIC_DIR = _FRONTEND_DIR / "static"
_TEMPLATES_DIR = _FRONTEND_DIR / "templates"
_WORKER_MODULE = "src.worker"

# ---------------------------------------------------------------------------
# App FastAPI
# ---------------------------------------------------------------------------

app = FastAPI(title="Dashboard Control", version="2.0.0")

# Lock para evitar corridas manuales simultaneas (auto-refresh + click manual,
# o multiples pestañas). Sin esto, dos workers en paralelo pueden intercalar
# lineas en historico_corridas.jsonl y perder datos en el truncado.
_corrida_lock = asyncio.Lock()

# Montar archivos estaticos (CSS, JS, iconos)
app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")


@app.middleware("http")
async def log_requests(request, call_next):
    """Middleware que loguea cada peticion HTTP con su duracion."""
    import time as _time
    t0 = _time.perf_counter()
    response = await call_next(request)
    dur_ms = (_time.perf_counter() - t0) * 1000
    log_frontend(request.method, request.url.path, response.status_code, dur_ms)
    return response


# ---------------------------------------------------------------------------
# Pagina principal
# ---------------------------------------------------------------------------


@app.get("/")
async def index():
    """Sirve la pagina HTML principal del dashboard."""
    index_path = _TEMPLATES_DIR / "index.html"
    if not index_path.is_file():
        raise HTTPException(status_code=404, detail="index.html no encontrado")
    return FileResponse(str(index_path), media_type="text/html")


# ---------------------------------------------------------------------------
# Endpoint principal de API (lectura de JSON del worker)
# ---------------------------------------------------------------------------


@app.get("/api/todos")
async def api_todos():
    """
    Devuelve estado + cambios + meta + metricas en una sola llamada.

    Es el endpoint principal que usa el frontend para renderizar todo
    en una sola peticion, evitando multiples round-trips.
    """
    df, lineas_cambios, lineas_fallos, meta, err = cargar_datos_para_frontend()

    if df is None:
        return {
            "estado": None,
            "cambios": {"lineas_cambios_ui": lineas_cambios, "lineas_fallos": lineas_fallos},
            "meta": meta,
            "metricas": None,
            "error": err,
        }

    # Leer historico (ultimas 200 corridas para tendencia/fiabilidad)
    historico = leer_historico(ultimas_n=200)

    # Calcular metricas derivadas
    metricas = calcular_metricas_completas(df, historico)

    return {
        "estado": metricas["tableros"],
        "cambios": {"lineas_cambios_ui": lineas_cambios, "lineas_fallos": lineas_fallos},
        "meta": meta,
        "metricas": {
            "resumen": metricas["resumen"],
            "ranking_atraso": metricas["ranking_atraso"],
            "ranking_constantes": metricas["ranking_constantes"],
            "criticos_riesgo": metricas["criticos_riesgo"],
            "tendencia": metricas["tendencia"],
            "fiabilidad": metricas["fiabilidad"],
        },
        "error": None,
    }


# ---------------------------------------------------------------------------
# Endpoint de accion: lanzar corrida manual
# ---------------------------------------------------------------------------


@app.post("/api/corrida")
async def api_corrida():
    """
    Lanza una corrida manual del worker en primer plano.

    Ejecuta el worker como subproceso con el mismo interprete de Python.
    El frontend muestra un spinner mientras espera la respuesta.

    El lock asegura que no haya dos corridas manuales simultaneas
    (auto-refresh + click manual, o multiples pestañas). Si ya hay una
    corrida en curso, se rechaza con 409 Conflict.
    """
    if _corrida_lock.locked():
        raise HTTPException(
            status_code=409,
            detail="Ya hay una corrida en curso. Espera a que termine.",
        )

    async with _corrida_lock:
        try:
            result = subprocess.run(
                [sys.executable, "-m", _WORKER_MODULE],
                cwd=config._ROOT_DIR,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=config.MONITOR_MANUAL_TIMEOUT_S,
                env=os.environ.copy(),
            )
        except subprocess.TimeoutExpired:
            raise HTTPException(
                status_code=504,
                detail=f"La corrida supero el tiempo maximo ({config.MONITOR_MANUAL_TIMEOUT_S} s).",
            )

        if result.returncode != 0:
            detalle = (result.stderr or "").strip() or (result.stdout or "").strip()
            raise HTTPException(
                status_code=500,
                detail=detalle or f"El worker termino con codigo {result.returncode}",
            )

        # Recargar datos despues de la corrida y devolverlos al frontend
        df, lineas_cambios, lineas_fallos, meta, err = cargar_datos_para_frontend()

        tableros = []
        metricas = None
        if df is not None:
            historico = leer_historico(ultimas_n=200)
            metricas = calcular_metricas_completas(df, historico)
            tableros = metricas["tableros"]

        return {
            "ok": True,
            "mensaje": (result.stdout or "").strip() or "Corrida OK",
            "estado": tableros,
            "cambios": {"lineas_cambios_ui": lineas_cambios, "lineas_fallos": lineas_fallos},
            "meta": meta,
            "metricas": {
                "resumen": metricas["resumen"],
                "ranking_atraso": metricas["ranking_atraso"],
                "ranking_constantes": metricas["ranking_constantes"],
                "criticos_riesgo": metricas["criticos_riesgo"],
                "tendencia": metricas["tendencia"],
                "fiabilidad": metricas["fiabilidad"],
            } if metricas else None,
        }


