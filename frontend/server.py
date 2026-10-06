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
import secrets
import subprocess
import sys
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from src import config
from src.logger import get_logger, log_frontend
from src.persistencia import cargar_datos_para_frontend, leer_historico, leer_meta_corrida
from src.metricas import calcular_metricas_completas
from src.salud import calcular_salud, esta_sano

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

# ---------------------------------------------------------------------------
# Proteccion de las acciones que disparan trabajo real (corrida manual)
# ---------------------------------------------------------------------------
# Contexto: el puerto 8070 queda expuesto a toda la red interna y POST
# /api/corrida NO pedia ninguna credencial. Cualquiera podia lanzar corridas
# contra la API de Power BI (quema cuota y puede bloquear el panel). Verificado
# el 06/10/2026: un POST sin credenciales devolvia 200 y corria el worker.
#
# Solucion elegida (doble envio, sin pedir contraseña al usuario):
#   1. La primera visita al panel deja una cookie con un token aleatorio.
#   2. La pagina trae ese mismo token en un <meta> (solo la misma sesion lo ve).
#   3. Para disparar una corrida, el navegador manda el token en la cabecera
#      X-CSRF-Token; el servidor exige que coincida con la cookie.
# Asi un script externo (curl, bot) recibe 403: no tiene la cookie de la sesion.
# Un navegador que abrio el panel sigue funcionando, sin ningun login.
_CSRF_COOKIE = "monitor_csrf"
_CSRF_HEADER = "X-CSRF-Token"


def _token_de_sesion(request: Request) -> str:
    """Devuelve el token de sesion existente o genera uno nuevo."""
    return request.cookies.get(_CSRF_COOKIE) or secrets.token_urlsafe(32)

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


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """
    Sirve la pagina HTML principal del dashboard.

    Inyecta un token de sesion (cookie + <meta>) para que solo el panel pueda
    disparar la corrida manual. En la primera visita se deja la cookie; en las
    siguientes se reusa la misma, asi el token es estable dentro de la sesion.
    """
    index_path = _TEMPLATES_DIR / "index.html"
    if not index_path.is_file():
        raise HTTPException(status_code=404, detail="index.html no encontrado")

    token = _token_de_sesion(request)
    html = index_path.read_text(encoding="utf-8")
    # El <meta> le da el token a app.js. El script del tema del <head> no depende
    # de esto, asi que no se altera el comportamiento visual.
    html = html.replace(
        "</head>",
        f'    <meta name="csrf-token" content="{token}">\n</head>',
        1,
    )

    response = HTMLResponse(
        content=html,
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )
    response.set_cookie(
        _CSRF_COOKIE,
        token,
        httponly=True,      # el JS no necesita leer la cookie: ya tiene el <meta>
        samesite="strict",  # no viaja desde otros sitios
        path="/",
    )
    return response


@app.get("/favicon.ico")
async def favicon():
    """
    Sirve el favicon tambien en la ruta raiz /favicon.ico.

    Algunos navegadores (y los marcadores/atajos guardados) piden /favicon.ico
    por su cuenta, sin mirar el <link> del HTML. Sin esta ruta respondia 404 y la
    pestaña quedaba sin icono. Regla del proyecto: NINGUNA pagina sin favicon.
    """
    ico = _STATIC_DIR / "icons8-power-bi-50.ico"
    if not ico.is_file():
        raise HTTPException(status_code=404, detail="favicon no encontrado")
    return FileResponse(str(ico), media_type="image/vnd.microsoft.icon")


@app.get("/healthz")
async def healthz():
    """
    Healthcheck REAL: valida la ULTIMA CORRIDA, no solo que el proceso viva.

    Devuelve 200 si el monitor esta sano (ultima corrida exitosa y fresca).
    Devuelve 503 si la ultima corrida fallo o esta desactualizada: asi Docker
    marca el contenedor como unhealthy y deja de mentir "healthy" con el
    pipeline caido (el fallo que dejo 2 semanas ciego al monitor, 23/09-06/10/2026).
    """
    salud = calcular_salud(leer_meta_corrida())
    if not esta_sano(salud):
        raise HTTPException(status_code=503, detail=salud)
    return salud


# ---------------------------------------------------------------------------
# Endpoint principal de API (lectura de JSON del worker)
# ---------------------------------------------------------------------------


@app.get("/api/todos")
async def api_todos():
    """
    Devuelve estado + cambios + meta + metricas + salud en una sola llamada.

    Es el endpoint principal que usa el frontend para renderizar todo
    en una sola peticion, evitando multiples round-trips.
    """
    df, lineas_cambios, lineas_fallos, meta, err = cargar_datos_para_frontend()
    salud = calcular_salud(meta)

    if df is None:
        return {
            "estado": None,
            "cambios": {"lineas_cambios_ui": lineas_cambios, "lineas_fallos": lineas_fallos},
            "meta": meta,
            "metricas": None,
            "salud": salud,
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
        "salud": salud,
        "error": None,
    }


# ---------------------------------------------------------------------------
# Endpoint de accion: lanzar corrida manual
# ---------------------------------------------------------------------------


@app.post("/api/corrida")
async def api_corrida(request: Request):
    """
    Lanza una corrida manual del worker en primer plano.

    Requiere el token de sesion (doble envio): la cabecera X-CSRF-Token debe
    coincidir con la cookie que el panel dejo al cargar la pagina. Un cliente
    externo sin esa cookie recibe 403 (ver comentario de _CSRF_COOKIE).

    Ejecuta el worker como subproceso con el mismo interprete de Python.
    El frontend muestra un spinner mientras espera la respuesta.

    El lock asegura que no haya dos corridas manuales simultaneas
    (auto-refresh + click manual, o multiples pestañas). Si ya hay una
    corrida en curso, se rechaza con 409 Conflict.
    """
    # --- Puerta de seguridad: solo el panel puede disparar la corrida ---
    enviado = request.headers.get(_CSRF_HEADER)
    esperado = request.cookies.get(_CSRF_COOKIE)
    if not config.ACCION_TOKEN_REQUERIDO:
        log.warning("ACCION_TOKEN_REQUERIDO=false: /api/corrida SIN proteccion")
    elif not esperado or not enviado or not secrets.compare_digest(enviado, esperado):
        # Sin cookie, sin cabecera, o no coinciden -> NO se corre nada.
        # (Ojo: si ambos faltan, "enviado != esperado" seria FALSO y dejaria pasar;
        #  por eso se exige que los dos existan antes de comparar.)
        raise HTTPException(
            status_code=403,
            detail="Accion no autorizada: falta el token de sesion del panel.",
        )

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


