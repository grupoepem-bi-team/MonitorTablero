import html
import math
import os
import subprocess
import sys

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from streamlit_autorefresh import st_autorefresh

import monitor_common as mc
import mobile_push_server

mobile_push_server.ensure_embedded_server_started()

FAVICON_ICO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons8-power-bi-50.ico")

# Re-exportados desde monitor_common (misma lógica de negocio).
ORDEN_ESTADO = mc.ORDEN_ESTADO
ESTADOS_PROBLEMA = mc.ESTADOS_PROBLEMA
NTFY_ENABLED = mc.NTFY_ENABLED
EXPO_PUSH_ENABLED = mc.EXPO_PUSH_ENABLED

# Celdas de estado sobre fondo oscuro (alto contraste, legibles).
PALETA_ESTADO = {
    "OK": ("rgba(34, 197, 94, 0.12)", "#4ade80"),
    "Advertencia": ("rgba(251, 191, 36, 0.14)", "#fbbf24"),
    "Demorado": ("rgba(248, 113, 113, 0.14)", "#fca5a5"),
    "Error": ("rgba(244, 114, 182, 0.14)", "#f9a8d4"),
}

ALTURA_TABLA_PX = 300

_APP_ROOT = os.path.dirname(os.path.abspath(__file__))
_MONITOR_WORKER_PY = os.path.join(_APP_ROOT, "monitor_worker.py")


def _timeout_corrida_monitor_manual_s() -> int:
    try:
        return int(os.environ.get("MONITOR_MANUAL_TIMEOUT_SEC", "900"))
    except ValueError:
        return 900


def _ejecutar_corrida_monitor_manual() -> tuple[bool, str]:
    """
    Lanza monitor_worker.py con el mismo intérprete y cwd del proyecto.
    Retorna (éxito, mensaje o salida de error).
    """
    if not os.path.isfile(_MONITOR_WORKER_PY):
        return False, f"No se encontró monitor_worker.py en {_MONITOR_WORKER_PY}"
    timeout = _timeout_corrida_monitor_manual_s()
    try:
        r = subprocess.run(
            [sys.executable, _MONITOR_WORKER_PY],
            cwd=_APP_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=os.environ.copy(),
        )
    except subprocess.TimeoutExpired:
        return False, f"El monitor superó el tiempo máximo ({timeout} s)."
    if r.returncode != 0:
        detalle = (r.stderr or "").strip() or (r.stdout or "").strip()
        if not detalle:
            detalle = f"Proceso terminó con código {r.returncode}"
        return False, detalle
    out = (r.stdout or "").strip()
    return True, out or "Corrida OK"


def _query_param_value(key: str) -> str:
    """Primer valor de un query param (Streamlit puede devolver str o lista)."""
    try:
        v = st.query_params.get(key)
    except Exception:
        return ""
    if v is None:
        return ""
    if isinstance(v, list):
        return str(v[0]).strip().lower() if v else ""
    return str(v).strip().lower()


def _layout_mobile_streamlit() -> bool:
    """
    Streamlit no expone el ancho del viewport en Python: no hay detección fiable
    de “pantalla angosta” sin query param, entorno o componente cliente.

    Activación explícita:
    - DASHBOARD_MOBILE_LAYOUT=1 (o true/yes) en el entorno del proceso Streamlit.
    - URL: ?dc_layout=mobile, ?layout=mobile, o ?mobile=1 (útil WebView / app móvil).
    """
    env = os.environ.get("DASHBOARD_MOBILE_LAYOUT", "").strip().lower()
    if env in ("1", "true", "yes"):
        return True
    if _query_param_value("dc_layout") == "mobile":
        return True
    if _query_param_value("layout") == "mobile":
        return True
    if _query_param_value("mobile") in ("1", "true", "yes"):
        return True
    return False


def _css_command_center() -> str:
    """Tema dark premium / command center. Clases con prefijo dc- para mantenimiento."""
    return """
    <style>
    /* === Shell: fondo y tipografía base (sin CDN; Segoe / SF en SO) === */
    html, body, [data-testid="stAppViewContainer"] {
        font-family: system-ui, -apple-system, "Segoe UI", "Segoe UI Variable", sans-serif;
    }
    [data-testid="stAppViewContainer"] {
        position: relative;
        background:
            radial-gradient(ellipse 90% 60% at 85% 15%, rgba(59, 130, 246, 0.09) 0%, transparent 50%),
            radial-gradient(ellipse 70% 50% at 10% 80%, rgba(129, 140, 248, 0.07) 0%, transparent 45%),
            radial-gradient(ellipse 120% 80% at 50% -20%, #1a2332 0%, transparent 55%),
            linear-gradient(180deg, #0a0c0f 0%, #0d1117 35%, #0a0c0f 100%) !important;
        color: #e6edf3;
    }
    /* Capa JS (#dc-live-bg-host) queda detrás; el contenido Streamlit encima */
    #dc-live-bg-host {
        position: fixed !important;
        inset: 0 !important;
        width: 100% !important;
        height: 100% !important;
        pointer-events: none !important;
        z-index: 0 !important;
        overflow: hidden !important;
    }
    #dc-live-bg-canvas {
        display: block !important;
        width: 100% !important;
        height: 100% !important;
        opacity: 0.62;
        filter: saturate(1.15);
    }
    @media (prefers-reduced-motion: reduce) {
        #dc-live-bg-canvas { opacity: 0.32; filter: none; }
    }
    .main .block-container {
        padding-top: 0.25rem;
        padding-bottom: 0.85rem;
        max-width: 100%;
    }
    [data-testid="stHeader"] {
        background: rgba(10, 12, 15, 0.85);
        border-bottom: 1px solid #21262d;
    }

    /* === Header ejecutivo — alto impacto: borde animado, shimmer, scan === */
    @keyframes dc-hero-border-spin {
        0%   { background-position: 0% 50%; }
        50%  { background-position: 100% 50%; }
        100% { background-position: 0% 50%; }
    }
    @keyframes dc-hero-shimmer {
        0%   { transform: translateX(-100%) skewX(-12deg); opacity: 0; }
        18%  { opacity: 0.55; }
        40%  { transform: translateX(220%) skewX(-12deg); opacity: 0; }
        100% { transform: translateX(220%) skewX(-12deg); opacity: 0; }
    }
    @keyframes dc-hero-scan {
        0%   { top: -4px; opacity: 0.6; }
        100% { top: 110%; opacity: 0; }
    }
    @keyframes dc-kicker-pulse {
        0%, 100% { opacity: 1; }
        50%       { opacity: 0.65; }
    }
    .dc-hero {
        position: relative;
        overflow: hidden;
        margin-bottom: 0.55rem;
        padding: 0.55rem 1.1rem 0.6rem;
        background: linear-gradient(135deg, rgba(15, 23, 42, 0.88) 0%, rgba(7, 11, 22, 0.96) 100%);
        border-radius: 12px;
        box-shadow:
            0 0 0 1px rgba(88, 166, 255, 0.22),
            0 8px 40px rgba(0, 0, 0, 0.7),
            0 0 60px rgba(56, 130, 246, 0.1),
            inset 0 1px 0 rgba(255, 255, 255, 0.07);
    }
    /* Borde superior luminoso animado */
    .dc-hero::before {
        content: "";
        position: absolute;
        inset: 0;
        border-radius: 8px;
        padding: 1px;
        background: linear-gradient(100deg, #1e3a5f, #3b82f6, #22d3ee, #6366f1, #3b82f6, #1e3a5f);
        background-size: 300% 300%;
        -webkit-mask: linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0);
        -webkit-mask-composite: destination-out;
        mask-composite: exclude;
        animation: dc-hero-border-spin 5s ease infinite;
        pointer-events: none;
    }
    /* Shimmer sweep */
    .dc-hero::after {
        content: "";
        position: absolute;
        top: 0; left: 0;
        width: 35%;
        height: 100%;
        background: linear-gradient(105deg, transparent 30%, rgba(255,255,255,0.09) 50%, transparent 70%);
        animation: dc-hero-shimmer 4.5s ease-in-out infinite;
        pointer-events: none;
    }
    /* Línea de scan */
    .dc-hero-scan {
        position: absolute;
        left: 0; right: 0;
        height: 1px;
        background: linear-gradient(90deg, transparent, rgba(88,166,255,0.35) 40%, rgba(34,211,238,0.35) 60%, transparent);
        animation: dc-hero-scan 3.5s linear infinite;
        pointer-events: none;
        z-index: 1;
    }
    /* div (no h1): legible y claro sin competir con Streamlit */
    .dc-hero-title {
        position: relative;
        z-index: 2;
        font-size: 1.9rem !important;
        font-weight: 900;
        letter-spacing: -0.04em;
        color: #f0f6fc;
        margin: 0 0 0.08rem 0;
        line-height: 1.1;
        text-shadow: 0 0 40px rgba(56, 189, 248, 0.35), 0 2px 6px rgba(0,0,0,0.7);
    }
    .dc-hero-sub {
        position: relative;
        z-index: 2;
        font-size: 0.78rem;
        color: #6b7280;
        margin: 0;
        line-height: 1.35;
        letter-spacing: 0.01em;
    }
    .dc-hero-kicker {
        position: relative;
        z-index: 2;
        font-size: 0.56rem;
        font-weight: 700;
        letter-spacing: 0.22em;
        text-transform: uppercase;
        color: #38bdf8;
        margin-bottom: 0.06rem;
        animation: dc-kicker-pulse 3s ease-in-out infinite;
    }
    .dc-hero-accent {
        position: relative;
        z-index: 2;
        height: 2px;
        width: 48px;
        margin-top: 0.1rem;
        border-radius: 2px;
        background: linear-gradient(90deg, #3b82f6, #22d3ee, #6366f1);
        box-shadow: 0 0 10px rgba(56, 130, 246, 0.55);
    }

    /* === Barra de control: una fila (label | consulta | botón), bloque único vía :has === */
    .main div[data-testid="stHorizontalBlock"]:has(.dc-control-bar__label) {
        align-items: center !important;
        background: linear-gradient(135deg, rgba(22, 27, 34, 0.95) 0%, rgba(13, 17, 23, 0.98) 100%);
        border: 1px solid rgba(48, 54, 61, 0.9);
        border-radius: 10px;
        padding: 0.2rem 0.65rem 0.2rem 0.75rem;
        margin-bottom: 0.3rem;
        box-shadow: 0 4px 16px rgba(0,0,0,0.35), inset 0 1px 0 rgba(255,255,255,0.04);
        gap: 0.28rem !important;
        backdrop-filter: blur(8px);
    }
    .main div[data-testid="stHorizontalBlock"]:has(.dc-control-bar__label) > div[data-testid="column"]:nth-child(2) {
        border-left: 1px solid #21262d;
        padding-left: 0.65rem;
        margin-left: 0.1rem;
        min-width: 0;
    }
    .main div[data-testid="stHorizontalBlock"]:has(.dc-control-bar__label) > div[data-testid="column"]:last-child {
        display: flex !important;
        align-items: center !important;
        justify-content: flex-end !important;
        flex-shrink: 0;
    }
    .dc-control-bar__label {
        font-size: 0.7rem;
        font-weight: 700;
        letter-spacing: 0.09em;
        text-transform: uppercase;
        color: #8b949e;
        white-space: nowrap;
        line-height: 1.15;
    }
    .dc-control-bar__time {
        font-size: 0.74rem;
        color: #c9d1d9;
        line-height: 1.25;
    }
    .dc-control-bar__time strong {
        color: #f0f6fc;
        font-weight: 600;
        font-variant-numeric: tabular-nums;
    }
    .dc-control-bar__empty {
        font-size: 0.74rem;
        color: #8b949e;
        line-height: 1.25;
    }

    /* === Métricas compactas — glow, hover lift, número pulsante === */
    @keyframes dc-metric-appear {
        from { opacity: 0; transform: translateY(6px) scale(0.97); }
        to   { opacity: 1; transform: translateY(0) scale(1); }
    }
    @keyframes dc-metric-ok-pulse {
        0%, 100% { box-shadow: 0 4px 16px rgba(0,0,0,0.4), 0 0 0 0 rgba(74,222,128,0); border-color: rgba(48,54,61,0.8); }
        50%       { box-shadow: 0 4px 20px rgba(0,0,0,0.5), 0 0 22px 4px rgba(74,222,128,0.22); border-color: rgba(74,222,128,0.35); }
    }
    @keyframes dc-metric-warn-pulse {
        0%, 100% { box-shadow: 0 4px 16px rgba(0,0,0,0.4), 0 0 0 0 rgba(251,191,36,0); border-color: rgba(48,54,61,0.8); }
        50%       { box-shadow: 0 4px 20px rgba(0,0,0,0.5), 0 0 22px 4px rgba(251,191,36,0.22); border-color: rgba(251,191,36,0.35); }
    }
    @keyframes dc-metric-late-pulse {
        0%, 100% { box-shadow: 0 4px 16px rgba(0,0,0,0.4), 0 0 0 0 rgba(248,113,113,0); border-color: rgba(48,54,61,0.8); }
        50%       { box-shadow: 0 4px 20px rgba(0,0,0,0.5), 0 0 22px 4px rgba(248,113,113,0.28); border-color: rgba(248,113,113,0.35); }
    }
    @keyframes dc-metric-err-pulse {
        0%, 100% { box-shadow: 0 4px 16px rgba(0,0,0,0.4), 0 0 0 0 rgba(244,114,182,0); border-color: rgba(48,54,61,0.8); }
        50%       { box-shadow: 0 4px 20px rgba(0,0,0,0.5), 0 0 22px 4px rgba(244,114,182,0.28); border-color: rgba(244,114,182,0.35); }
    }
    .dc-metrics-row {
        display: grid;
        grid-template-columns: repeat(5, 1fr);
        gap: 0.55rem;
        margin-bottom: 0.2rem;
        margin-top: 0.1rem;
    }
    @media (max-width: 1100px) {
        .dc-metrics-row { grid-template-columns: repeat(3, 1fr); }
    }
    @media (max-width: 700px) {
        .dc-metrics-row { grid-template-columns: repeat(2, 1fr); }
    }
    .dc-metric-card {
        position: relative;
        overflow: hidden;
        padding: 0.7rem 0.85rem 0.75rem;
        background: linear-gradient(155deg, rgba(22, 27, 34, 0.95) 0%, rgba(13, 17, 23, 0.98) 100%);
        border: 1px solid rgba(48, 54, 61, 0.8);
        border-radius: 12px;
        box-shadow: 0 4px 16px rgba(0, 0, 0, 0.4), inset 0 1px 0 rgba(255,255,255,0.05);
        transition: transform 0.22s cubic-bezier(0.34,1.56,0.64,1), border-color 0.2s ease, box-shadow 0.2s ease;
        animation: dc-metric-appear 0.45s ease both;
        backdrop-filter: blur(8px);
    }
    .dc-metric-card:hover {
        transform: translateY(-4px) scale(1.02);
        border-color: rgba(88,166,255,0.5);
        box-shadow: 0 12px 36px rgba(0, 0, 0, 0.6), 0 0 24px rgba(88,166,255,0.14);
    }
    /* Barra de color superior más gruesa y más brillante */
    .dc-metric-card::before {
        content: "";
        position: absolute;
        top: 0; left: 0; right: 0;
        height: 3px;
        border-radius: 12px 12px 0 0;
        opacity: 1;
    }
    /* Shimmer diagonal interno */
    .dc-metric-card::after {
        content: "";
        position: absolute;
        top: -40%; left: -20%;
        width: 60%;
        height: 180%;
        background: linear-gradient(105deg, transparent 0%, rgba(255,255,255,0.055) 50%, transparent 100%);
        pointer-events: none;
        transform: skewX(-15deg);
    }
    /* Glow de fondo por color */
    .dc-metric-card--total { --card-glow: rgba(148,163,184,0.06); }
    .dc-metric-card--ok    { --card-glow: rgba(74,222,128,0.07); }
    .dc-metric-card--warn  { --card-glow: rgba(251,191,36,0.07); }
    .dc-metric-card--late  { --card-glow: rgba(248,113,113,0.07); }
    .dc-metric-card--err   { --card-glow: rgba(244,114,182,0.07); }

    .dc-metric-card--total::before { background: linear-gradient(90deg, #334155, #94a3b8, #64748b); box-shadow: 0 0 10px rgba(148,163,184,0.4); }
    .dc-metric-card--ok::before    { background: linear-gradient(90deg, #16a34a, #4ade80, #22d3ee); box-shadow: 0 0 12px rgba(74,222,128,0.55); }
    .dc-metric-card--warn::before  { background: linear-gradient(90deg, #b45309, #fbbf24, #fde68a); box-shadow: 0 0 12px rgba(251,191,36,0.5); }
    .dc-metric-card--late::before  { background: linear-gradient(90deg, #b91c1c, #f87171, #fca5a5); box-shadow: 0 0 12px rgba(248,113,113,0.5); }
    .dc-metric-card--err::before   { background: linear-gradient(90deg, #9d174d, #f472b6, #fbcfe8); box-shadow: 0 0 12px rgba(244,114,182,0.5); }

    .dc-metric-card--ok   { animation: dc-metric-ok-pulse 4s ease-in-out infinite; }
    .dc-metric-card--warn { animation: dc-metric-warn-pulse 3.5s ease-in-out infinite; }
    .dc-metric-card--late { animation: dc-metric-late-pulse 2.8s ease-in-out infinite; }
    .dc-metric-card--err  { animation: dc-metric-err-pulse 2.2s ease-in-out infinite; }

    .dc-metric-label {
        display: block;
        font-size: 0.65rem;
        font-weight: 700;
        color: #6b7280;
        letter-spacing: 0.1em;
        text-transform: uppercase;
        line-height: 1.2;
        margin-bottom: 0.3rem;
    }
    .dc-metric-value {
        display: block;
        font-size: clamp(1.35rem, 2.4vw, 1.65rem);
        font-weight: 800;
        line-height: 1.08;
        letter-spacing: -0.03em;
        color: #f0f6fc;
        font-variant-numeric: tabular-nums;
        text-shadow: 0 0 16px currentColor;
    }
    .dc-metric-card--total .dc-metric-value { color: #cbd5e1; }
    .dc-metric-card--ok .dc-metric-value    { color: #4ade80; text-shadow: 0 0 14px rgba(74,222,128,0.45); }
    .dc-metric-card--warn .dc-metric-value  { color: #fbbf24; text-shadow: 0 0 14px rgba(251,191,36,0.45); }
    .dc-metric-card--late .dc-metric-value  { color: #f87171; text-shadow: 0 0 14px rgba(248,113,113,0.45); }
    .dc-metric-card--err .dc-metric-value   { color: #f472b6; text-shadow: 0 0 14px rgba(244,114,182,0.45); }

    /* === Sección críticos: banner compacto — más agresivo en alerta === */
    @keyframes dc-banner-alert-pulse {
        0%, 100% { box-shadow: 0 6px 22px rgba(0,0,0,0.42), 0 0 0 0 rgba(220,38,38,0); }
        50%       { box-shadow: 0 6px 28px rgba(0,0,0,0.52), 0 0 20px 4px rgba(220,38,38,0.18); }
    }
    @keyframes dc-rail-alert-flow {
        0%   { background-position: 0% 0%; }
        100% { background-position: 0% 200%; }
    }
    .dc-section-gap { margin-top: 0; }
    .dc-divider {
        border: none;
        height: 1px;
        background: linear-gradient(90deg, transparent, rgba(88,166,255,0.2) 20%, rgba(34,211,238,0.15) 50%, rgba(88,166,255,0.2) 80%, transparent);
        margin: 0.55rem 0 0.45rem;
        box-shadow: 0 1px 8px rgba(56,189,248,0.08);
    }

    /* === Cambios recientes: contenido unificado (lista HTML) === */
    .dc-cambios-section-label {
        font-size: 0.82rem;
        color: #e6edf3;
        margin: 0.35rem 0 0.2rem 0;
    }
    .dc-cambios-list {
        margin: 0.15rem 0 0.25rem 0;
        padding-left: 1.15rem;
        color: #c9d1d9;
        font-size: 0.8rem;
        line-height: 1.35;
    }
    .dc-cambios-list li { margin: 0.12rem 0; }
    .dc-cambios-caption {
        font-size: 0.68rem;
        color: #8b949e;
        margin: 0.35rem 0 0 0;
        line-height: 1.3;
    }
    .dc-cambios-warn-box {
        margin-top: 0.45rem;
        padding: 0.45rem 0.55rem;
        border-radius: 8px;
        background: rgba(251, 191, 36, 0.08);
        border: 1px solid rgba(251, 191, 36, 0.35);
        color: #e6edf3;
        font-size: 0.78rem;
        line-height: 1.35;
    }
    .dc-info-callout {
        padding: 0.55rem 0.65rem;
        border-radius: 8px;
        background: rgba(56, 139, 253, 0.12);
        border: 1px solid rgba(56, 139, 253, 0.35);
        color: #c9d1d9;
        font-size: 0.82rem;
        line-height: 1.35;
        margin-top: 0.25rem;
    }

    .dc-banner {
        display: flex;
        align-items: stretch;
        gap: 0;
        margin-bottom: 0.15rem;
        border-radius: 9px;
        overflow: hidden;
        border: 1px solid #30363d;
        box-shadow: 0 6px 22px rgba(0, 0, 0, 0.42);
        transition: box-shadow 0.3s ease;
    }
    .dc-banner__rail {
        width: 4px;
        flex-shrink: 0;
        background: linear-gradient(180deg, #f59e0b, #dc2626, #f59e0b);
        background-size: 100% 200%;
        animation: dc-rail-alert-flow 2s linear infinite;
    }
    .dc-banner--clear .dc-banner__rail {
        background: linear-gradient(180deg, #22c55e, #0d9488, #22c55e);
        background-size: 100% 200%;
        animation: dc-rail-alert-flow 3.5s linear infinite;
    }
    .dc-banner__inner {
        flex: 1;
        padding: 0.28rem 0.65rem 0.32rem;
        background: linear-gradient(125deg, #1c1214 0%, #161b22 45%, #0d1117 100%);
    }
    .dc-banner--clear .dc-banner__inner {
        background: linear-gradient(125deg, #0f1a14 0%, #161b22 50%, #0d1117 100%);
    }
    .dc-banner__kicker {
        font-size: 0.58rem;
        font-weight: 700;
        letter-spacing: 0.14em;
        text-transform: uppercase;
        color: #f87171;
        margin-bottom: 0.04rem;
    }
    .dc-banner--clear .dc-banner__kicker { color: #4ade80; }
    .dc-banner__title {
        font-size: 1.08rem !important;
        font-weight: 700;
        color: #f0f6fc;
        margin: 0 0 0.06rem 0;
        letter-spacing: -0.02em;
        line-height: 1.22;
    }
    .dc-banner__meta {
        font-size: 0.72rem;
        color: #8b949e;
        margin: 0;
        line-height: 1.28;
    }
    .dc-banner__badge {
        display: inline-block;
        margin-top: 0.1rem;
        padding: 0.06rem 0.3rem;
        font-size: 0.58rem;
        font-weight: 700;
        border-radius: 4px;
        background: rgba(220, 38, 38, 0.2);
        color: #fca5a5;
        border: 1px solid rgba(248, 113, 113, 0.35);
    }
    .dc-banner--clear .dc-banner__badge {
        background: rgba(34, 197, 94, 0.15);
        color: #86efac;
        border-color: rgba(74, 222, 128, 0.3);
    }

    /* === Críticos + reactor (un solo bloque) — glow en alerta === */
    @keyframes dc-crit-alert-border {
        0%, 100% { box-shadow: 0 10px 36px rgba(0,0,0,0.48), 0 0 0 1px rgba(220,38,38,0.18); }
        50%       { box-shadow: 0 10px 42px rgba(0,0,0,0.56), 0 0 28px 2px rgba(220,38,38,0.16), 0 0 0 1px rgba(220,38,38,0.35); }
    }
    @keyframes dc-crit-clear-border {
        0%, 100% { box-shadow: 0 10px 36px rgba(0,0,0,0.48), 0 0 0 1px rgba(34,197,94,0.12); }
        50%       { box-shadow: 0 10px 42px rgba(0,0,0,0.52), 0 0 20px 2px rgba(34,197,94,0.12), 0 0 0 1px rgba(34,197,94,0.28); }
    }
    .dc-criticos-unificado {
        display: flex;
        align-items: stretch;
        margin-bottom: 0.18rem;
        border-radius: 12px;
        overflow: hidden;
        border: 1px solid #30363d;
        box-shadow: 0 10px 36px rgba(0, 0, 0, 0.48);
    }
    .dc-criticos-unificado--alert {
        animation: dc-crit-alert-border 2.4s ease-in-out infinite;
    }
    .dc-criticos-unificado--clear {
        animation: dc-crit-clear-border 4s ease-in-out infinite;
    }
    .dc-criticos-unificado__rail {
        width: 5px;
        flex-shrink: 0;
        background: linear-gradient(180deg, #f59e0b, #dc2626, #f59e0b);
        background-size: 100% 200%;
        animation: dc-rail-alert-flow 2s linear infinite;
    }
    .dc-criticos-unificado--clear .dc-criticos-unificado__rail {
        background: linear-gradient(180deg, #22c55e, #0d9488, #22c55e);
        background-size: 100% 200%;
        animation: dc-rail-alert-flow 3.5s linear infinite;
    }
    .dc-criticos-unificado--empty .dc-criticos-unificado__rail {
        background: linear-gradient(180deg, #6b7280, #374151);
        animation: none;
    }
    .dc-criticos-unificado__body {
        display: flex;
        flex: 1;
        flex-wrap: wrap;
        align-items: stretch;
        min-width: 0;
    }
    .dc-criticos-unificado__left {
        flex: 1 1 240px;
        min-width: 0;
        padding: 0.5rem 0.75rem 0.55rem 0.65rem;
        background: linear-gradient(125deg, #1c1214 0%, #161b22 45%, #0d1117 100%);
    }
    .dc-criticos-unificado--clear .dc-criticos-unificado__left {
        background: linear-gradient(125deg, #0f1a14 0%, #161b22 50%, #0d1117 100%);
    }
    .dc-criticos-unificado--empty .dc-criticos-unificado__left {
        background: linear-gradient(125deg, #141820 0%, #161b22 50%, #0d1117 100%);
    }
    .dc-criticos-unificado__reactor-host {
        flex: 0 0 clamp(168px, 26vw, 210px);
        min-width: 0;
        max-width: 210px;
        border-left: 1px solid rgba(48, 54, 61, 0.95);
        display: flex;
        align-items: stretch;
        justify-content: center;
        background: #0a0e14;
        overflow: hidden;
    }
    @media (max-width: 720px) {
        .dc-criticos-unificado__reactor-host {
            max-width: none;
            flex: 1 1 100%;
            border-left: none;
            border-top: 1px solid rgba(48, 54, 61, 0.95);
        }
    }
    .dc-criticos-unificado--alert .dc-banner__kicker { color: #f87171; }
    .dc-criticos-unificado--clear .dc-banner__kicker { color: #4ade80; }
    .dc-criticos-unificado--empty .dc-banner__kicker { color: #9ca3af; }
    .dc-criticos-unificado--clear .dc-banner__badge {
        background: rgba(34, 197, 94, 0.15);
        color: #86efac;
        border-color: rgba(74, 222, 128, 0.3);
    }
    .dc-criticos-unificado--empty .dc-banner__badge {
        background: rgba(107, 114, 128, 0.22);
        color: #d1d5db;
        border: 1px solid rgba(156, 163, 175, 0.35);
    }

    /* === Sección título — más prominente === */
    .dc-section-title {
        font-size: 1.0rem;
        font-weight: 700;
        color: #e6edf3;
        margin: 0.1rem 0 0.35rem 0;
        letter-spacing: -0.02em;
        padding-left: 0.6rem;
        border-left: 3px solid #3b82f6;
    }

    /* === Cambios section: glass card === */
    .dc-cambios-card {
        background: linear-gradient(135deg, rgba(22, 27, 34, 0.9) 0%, rgba(13, 17, 23, 0.95) 100%);
        border: 1px solid rgba(48, 54, 61, 0.8);
        border-left: 3px solid rgba(56, 189, 248, 0.6);
        border-radius: 10px;
        padding: 0.6rem 0.85rem 0.65rem;
        margin-bottom: 0.15rem;
        box-shadow: 0 4px 20px rgba(0,0,0,0.4), inset 0 1px 0 rgba(255,255,255,0.04);
    }
    .dc-cambios-card-title {
        font-size: 0.65rem;
        font-weight: 700;
        letter-spacing: 0.12em;
        text-transform: uppercase;
        color: #38bdf8;
        margin-bottom: 0.25rem;
    }
    .dc-cambios-card-empty {
        font-size: 0.78rem;
        color: #4b5563;
        font-style: italic;
    }

    /* DataFrames: glassmorphism premium */
    .main [data-testid="stDataFrame"] {
        border: 1px solid rgba(88, 166, 255, 0.15) !important;
        border-radius: 12px;
        overflow: hidden;
        background: rgba(13, 17, 23, 0.85);
        box-shadow:
            0 8px 32px rgba(0, 0, 0, 0.55),
            inset 0 1px 0 rgba(255,255,255,0.06),
            inset 0 0 0 1px rgba(255,255,255,0.03);
        font-size: 0.8rem;
        backdrop-filter: blur(12px);
    }
    /* Glow sutil en foco del dataframe */
    .main [data-testid="stDataFrame"]:focus-within {
        border-color: rgba(59,130,246,0.45) !important;
        box-shadow: 0 8px 32px rgba(0,0,0,0.55), 0 0 0 3px rgba(59,130,246,0.14) !important;
    }

    /* Radio y botón compactos */
    [data-testid="stRadio"] label,
    [data-testid="stRadio"] p {
        color: #c9d1d9 !important;
    }
    [data-testid="stRadio"] div[role="radiogroup"] {
        gap: 0.35rem;
    }
    .main div[data-testid="stHorizontalBlock"] {
        align-items: center !important;
    }
    .stButton > button {
        background: linear-gradient(135deg, rgba(30, 41, 59, 0.95) 0%, rgba(15, 23, 42, 0.98) 100%) !important;
        color: #93c5fd !important;
        border: 1px solid rgba(59, 130, 246, 0.4) !important;
        font-weight: 700 !important;
        font-size: 0.75rem !important;
        letter-spacing: 0.03em !important;
        padding: 0.3rem 0.75rem !important;
        min-height: 2rem !important;
        border-radius: 8px !important;
        transition: all 0.2s cubic-bezier(0.34,1.56,0.64,1) !important;
        box-shadow: 0 2px 8px rgba(0,0,0,0.4), 0 0 0 0 rgba(59,130,246,0) !important;
    }
    .stButton > button:hover {
        border-color: #60a5fa !important;
        color: #dbeafe !important;
        box-shadow: 0 4px 20px rgba(0,0,0,0.5), 0 0 20px rgba(59,130,246,0.2) !important;
        background: linear-gradient(135deg, rgba(37, 52, 80, 0.98) 0%, rgba(20, 30, 55, 0.99) 100%) !important;
        transform: translateY(-1px);
    }

    /* Alerts / info */
    div[data-testid="stAlert"] {
        background: #161b22 !important;
        border: 1px solid #30363d !important;
        color: #c9d1d9 !important;
        padding: 0.4rem 0.55rem !important;
    }

    /* Spinner */
    .stSpinner > div { border-color: #58a6ff transparent transparent !important; }

    /* Menos aire entre bloques de markdown consecutivos en el cuerpo */
    .main [data-testid="stMarkdownContainer"] p { margin-bottom: 0.12rem; }

    </style>
    """


def _svg_flat_hex_path(cx: float, cy: float, r: float) -> str:
    """Hexágono plano-top (flat-top), viewBox 0–100."""
    pts: list[str] = []
    for k in range(6):
        ang = math.radians(-90 + k * 60)
        pts.append(f"{cx + r * math.cos(ang):.3f},{cy + r * math.sin(ang):.3f}")
    return "M " + " L ".join(pts) + " Z"


def _svg_hex_rivets(cx: float, cy: float, r: float, fill: str, r_dot: float = 1.1) -> str:
    parts: list[str] = []
    for k in range(6):
        ang = math.radians(-90 + k * 60)
        vx = cx + r * math.cos(ang)
        vy = cy + r * math.sin(ang)
        # rivet con highlight interno
        parts.append(
            f'<circle cx="{vx:.3f}" cy="{vy:.3f}" r="{r_dot}" fill="{fill}"/>'
            f'<circle cx="{vx - 0.28:.3f}" cy="{vy - 0.28:.3f}" r="{r_dot * 0.38:.3f}" fill="rgba(255,255,255,0.22)"/>'
        )
    return "".join(parts)


def _svg_tangent_slot_marks(cx: float, cy: float, r: float, n: int = 16, half_len: float = 1.6) -> str:
    """Muescas tangentes de alta precisión — graduaciones industriales."""
    parts: list[str] = []
    for k in range(n):
        ang = -math.pi / 2 + math.tau * k / n
        px = cx + r * math.cos(ang)
        py = cy + r * math.sin(ang)
        tx = -math.sin(ang)
        ty = math.cos(ang)
        # marcas largas cada 4, cortas el resto
        hl = half_len if k % 4 == 0 else half_len * 0.55
        x1, y1 = px - hl * tx, py - hl * ty
        x2, y2 = px + hl * tx, py + hl * ty
        w = "0.75" if k % 4 == 0 else "0.4"
        parts.append(
            f'<line x1="{x1:.3f}" y1="{y1:.3f}" x2="{x2:.3f}" y2="{y2:.3f}" '
            f'stroke-linecap="round" stroke-width="{w}"/>'
        )
    return "".join(parts)


def _svg_conduit_arcs(cx: float, cy: float, r: float, n: int = 10, span_deg: float = 22) -> str:
    """Arcos de conducto energético — más delgados y precisos."""
    parts: list[str] = []
    half = math.radians(span_deg / 2)
    for k in range(n):
        mid = -math.pi / 2 + math.tau * k / n
        a0, a1 = mid - half, mid + half
        x0 = cx + r * math.cos(a0)
        y0 = cy + r * math.sin(a0)
        x1 = cx + r * math.cos(a1)
        y1 = cy + r * math.sin(a1)
        parts.append(
            f'<path fill="none" stroke="url(#dcReactPlasma)" stroke-width="1.6" stroke-linecap="round" '
            f'd="M {x0:.3f} {y0:.3f} A {r:.3f} {r:.3f} 0 0 1 {x1:.3f} {y1:.3f}" opacity="0.55"/>'
        )
    return "".join(parts)


def _svg_containment_brackets(cx: float, cy: float, r: float) -> str:
    """4 soportes de contención mecánica en los ejes cardinales."""
    parts: list[str] = []
    for ang_deg in [0, 90, 180, 270]:
        ang = math.radians(ang_deg - 90)
        # base del soporte (punto en el anillo)
        bx = cx + r * math.cos(ang)
        by = cy + r * math.sin(ang)
        # punta interna
        inner_r = r - 4.5
        ix = cx + inner_r * math.cos(ang)
        iy = cy + inner_r * math.sin(ang)
        # aletas transversales
        perp_ang = ang + math.pi / 2
        aw = 2.2
        ax1 = bx + aw * math.cos(perp_ang)
        ay1 = by + aw * math.sin(perp_ang)
        ax2 = bx - aw * math.cos(perp_ang)
        ay2 = by - aw * math.sin(perp_ang)
        iw = 1.1
        ix1 = ix + iw * math.cos(perp_ang)
        iy1 = iy + iw * math.sin(perp_ang)
        ix2 = ix - iw * math.cos(perp_ang)
        iy2 = iy - iw * math.sin(perp_ang)
        parts.append(
            f'<path d="M {ax1:.3f},{ay1:.3f} L {ix1:.3f},{iy1:.3f} L {ix2:.3f},{iy2:.3f} L {ax2:.3f},{ay2:.3f}" '
            f'fill="none" stroke="url(#dcBracketGrad)" stroke-width="0.7" stroke-linejoin="round" opacity="0.7"/>'
        )
    return "".join(parts)


def _svg_energy_filaments(cx: float, cy: float, core_r: float, n: int = 6) -> str:
    """Filamentos de energía que emergen del core hacia el sello."""
    parts: list[str] = []
    for k in range(n):
        ang = math.tau * k / n + math.pi / 12
        # punto en superficie del core
        sx = cx + core_r * math.cos(ang)
        sy = cy + core_r * math.sin(ang)
        # punto destino (sello exterior)
        seal_r = core_r + 4.5
        ex = cx + seal_r * math.cos(ang + 0.18)
        ey = cy + seal_r * math.sin(ang + 0.18)
        # control bezier
        mid_r = core_r + 2.2
        mx = cx + mid_r * math.cos(ang + 0.09)
        my = cy + mid_r * math.sin(ang + 0.09)
        parts.append(
            f'<path d="M {sx:.3f},{sy:.3f} Q {mx:.3f},{my:.3f} {ex:.3f},{ey:.3f}" '
            f'fill="none" stroke="url(#dcFilamentGrad)" stroke-width="0.55" stroke-linecap="round" opacity="0.62"/>'
        )
    return "".join(parts)


def _svg_nucleo_reactor(mod: str) -> str:
    """
    Núcleo SVG 92×92 — celda energética de alta precisión.
    Capas (interior → exterior):
      1. Bloom ambiental
      2. Placa de fondo hexagonal (metal oscuro)
      3. Anillos técnicos concéntricos (3 velocidades)
      4. Conductos de plasma (contra-rotación)
      5. Graduaciones de medición (slot marks)
      6. Soportes de contención mecánica (brackets)
      7. Carcasa hex externa (housing)
      8. Remaches en vértices
      9. Sello de contención (seal ring)
      10. Filamentos de energía core→sello
      11. Núcleo (core sphere con gradiente radial)
      12. Highlight de glint (especular)
      13. Número overlay
    """
    P = {
        "offline": {
            "c0": "#3a404a", "c1": "#252b33", "c2": "#141820", "c3": "#0a0d12",
            "o_a": "rgba(100,116,139,0.18)", "o_b": "rgba(30,41,59,0.08)",
            "pl_a": "rgba(148,163,184,0.22)", "pl_b": "rgba(71,85,105,0.08)",
            "s1": "rgba(148,163,184,0.22)", "s2": "rgba(100,116,139,0.14)", "s3": "rgba(71,85,105,0.1)",
            "hout": "rgba(120,136,155,0.42)", "hin": "rgba(51,65,85,0.45)",
            "rivet": "rgba(180,196,212,0.28)", "slot": "rgba(140,155,170,0.38)",
            "bracket": "rgba(100,116,139,0.4)", "seal": "rgba(80,96,110,0.35)",
            "fil_a": "rgba(148,163,184,0.0)", "fil_b": "rgba(148,163,184,0.0)",
            "bloom": "rgba(60,80,100,0.0)",
        },
        "idle": {
            "c0": "#38383f", "c1": "#25252b", "c2": "#171719", "c3": "#09090b",
            "o_a": "rgba(82,82,91,0.16)", "o_b": "rgba(0,0,0,0)",
            "pl_a": "rgba(120,120,130,0.16)", "pl_b": "rgba(60,60,70,0.06)",
            "s1": "rgba(100,100,110,0.18)", "s2": "rgba(70,70,78,0.12)", "s3": "rgba(50,50,58,0.1)",
            "hout": "rgba(100,100,110,0.32)", "hin": "rgba(36,36,42,0.5)",
            "rivet": "rgba(180,180,188,0.2)", "slot": "rgba(130,130,140,0.3)",
            "bracket": "rgba(80,80,90,0.35)", "seal": "rgba(60,60,68,0.3)",
            "fil_a": "rgba(120,120,130,0.0)", "fil_b": "rgba(120,120,130,0.0)",
            "bloom": "rgba(50,50,60,0.0)",
        },
        "estable": {
            "c0": "#052e16", "c1": "#0d4a22", "c2": "#16a34a", "c3": "#052e16",
            "o_a": "rgba(34,211,238,0.22)", "o_b": "rgba(74,222,128,0.28)",
            "pl_a": "rgba(52,211,153,0.55)", "pl_b": "rgba(22,163,74,0.22)",
            "s1": "rgba(52,211,153,0.38)", "s2": "rgba(74,222,128,0.24)", "s3": "rgba(21,128,61,0.18)",
            "hout": "rgba(74,222,128,0.5)", "hin": "rgba(6,78,59,0.7)",
            "rivet": "rgba(167,243,208,0.45)", "slot": "rgba(52,211,153,0.55)",
            "bracket": "rgba(34,211,238,0.45)", "seal": "rgba(45,212,191,0.45)",
            "fil_a": "rgba(34,211,238,0.7)", "fil_b": "rgba(74,222,128,0.0)",
            "bloom": "rgba(34,197,94,0.28)",
        },
        "inestable": {
            "c0": "#422006", "c1": "#7c3503", "c2": "#f59e0b", "c3": "#422006",
            "o_a": "rgba(251,191,36,0.32)", "o_b": "rgba(248,113,113,0.16)",
            "pl_a": "rgba(253,224,71,0.5)", "pl_b": "rgba(234,88,12,0.24)",
            "s1": "rgba(251,191,36,0.42)", "s2": "rgba(245,158,11,0.28)", "s3": "rgba(248,113,113,0.18)",
            "hout": "rgba(251,191,36,0.52)", "hin": "rgba(120,53,15,0.65)",
            "rivet": "rgba(254,243,199,0.42)", "slot": "rgba(253,224,71,0.52)",
            "bracket": "rgba(253,186,53,0.5)", "seal": "rgba(245,158,11,0.48)",
            "fil_a": "rgba(253,224,71,0.75)", "fil_b": "rgba(234,88,12,0.0)",
            "bloom": "rgba(245,158,11,0.32)",
        },
        "critico": {
            "c0": "#1c0703", "c1": "#6b1500", "c2": "#ea580c", "c3": "#1c0703",
            "o_a": "rgba(239,68,68,0.28)", "o_b": "rgba(249,115,22,0.32)",
            "pl_a": "rgba(252,165,165,0.52)", "pl_b": "rgba(220,38,38,0.3)",
            "s1": "rgba(239,68,68,0.5)", "s2": "rgba(249,115,22,0.34)", "s3": "rgba(185,28,28,0.22)",
            "hout": "rgba(248,113,113,0.58)", "hin": "rgba(67,20,7,0.72)",
            "rivet": "rgba(254,215,170,0.45)", "slot": "rgba(252,165,165,0.6)",
            "bracket": "rgba(249,115,22,0.55)", "seal": "rgba(239,68,68,0.52)",
            "fil_a": "rgba(252,165,165,0.8)", "fil_b": "rgba(220,38,38,0.0)",
            "bloom": "rgba(220,38,38,0.38)",
        },
        "meltdown": {
            "c0": "#1a0204", "c1": "#7f1d1d", "c2": "#dc2626", "c3": "#1a0204",
            "o_a": "rgba(244,114,182,0.22)", "o_b": "rgba(220,38,38,0.38)",
            "pl_a": "rgba(254,202,202,0.55)", "pl_b": "rgba(190,24,93,0.3)",
            "s1": "rgba(248,113,113,0.55)", "s2": "rgba(220,38,38,0.4)", "s3": "rgba(251,113,133,0.26)",
            "hout": "rgba(252,165,165,0.6)", "hin": "rgba(69,10,10,0.78)",
            "rivet": "rgba(254,202,202,0.48)", "slot": "rgba(252,165,165,0.65)",
            "bracket": "rgba(244,114,182,0.6)", "seal": "rgba(220,38,38,0.58)",
            "fil_a": "rgba(254,202,202,0.9)", "fil_b": "rgba(190,24,93,0.0)",
            "bloom": "rgba(220,38,38,0.45)",
        },
    }
    p = P.get(mod, P["offline"])
    cx, cy = 50.0, 50.0

    # Radios de capas
    R_OUTER_BLOOM = 49.5
    R_HEX_OUT = 46.5
    R_HEX_IN  = 41.2
    R_RING1   = 47.8
    R_RING2   = 44.6
    R_RING3   = 39.8
    R_CONDUIT = 36.8
    R_SLOTS   = 42.5
    R_BRACKET = 41.8
    R_SEAL    = 30.8
    R_CORE    = 27.2

    hex_o = _svg_flat_hex_path(cx, cy, R_HEX_OUT)
    hex_i = _svg_flat_hex_path(cx, cy, R_HEX_IN)
    # Placa de fondo hex (relleno metálico oscuro)
    hex_bg = _svg_flat_hex_path(cx, cy, R_HEX_IN - 0.4)

    rivets   = _svg_hex_rivets(cx, cy, R_HEX_OUT, p["rivet"])
    slots    = _svg_tangent_slot_marks(cx, cy, R_SLOTS, n=24)
    conduits = _svg_conduit_arcs(cx, cy, R_CONDUIT, n=10, span_deg=20)
    brackets = _svg_containment_brackets(cx, cy, R_BRACKET)
    filaments = _svg_energy_filaments(cx, cy, R_CORE, n=8)

    rings = (
        f'<circle cx="{cx}" cy="{cy}" r="{R_RING1}" fill="none" stroke="{p["s1"]}" stroke-width="0.5" stroke-dasharray="2.8 7.5" opacity="0.8"/>'
        f'<circle cx="{cx}" cy="{cy}" r="{R_RING2}" fill="none" stroke="{p["s2"]}" stroke-width="0.38" stroke-dasharray="1.2 5" opacity="0.65"/>'
        f'<circle cx="{cx}" cy="{cy}" r="{R_RING3}" fill="none" stroke="{p["s3"]}" stroke-width="0.6" stroke-dasharray="7 12" opacity="0.5"/>'
    )

    # Anillo de graduación fino extra (entre ring3 y seal)
    tick_r = 34.5
    tick_ring = f'<circle cx="{cx}" cy="{cy}" r="{tick_r}" fill="none" stroke="{p["seal"]}" stroke-width="0.28" stroke-dasharray="0.6 3.8" opacity="0.55"/>'

    core_cls = {
        "estable":  "dc-r-svg-core dc-r-svg-core--drift",
        "inestable":"dc-r-svg-core dc-r-svg-core--pulse",
        "critico":  "dc-r-svg-core dc-r-svg-core--shake",
        "meltdown": "dc-r-svg-core dc-r-svg-core--melt",
    }.get(mod, "dc-r-svg-core")

    # Glint especular (doble arco: principal + reflejo tenue)
    g_r = R_CORE
    glint_main = (
        f'<path fill="none" stroke="rgba(255,255,255,0.18)" stroke-width="0.5" stroke-linecap="round" '
        f'd="M {cx - g_r*0.62:.3f} {cy - g_r*0.75:.3f} A {g_r*0.88:.3f} {g_r*0.88:.3f} 0 0 1 '
        f'{cx + g_r*0.62:.3f} {cy - g_r*0.75:.3f}"/>'
    )
    glint_soft = (
        f'<path fill="none" stroke="rgba(255,255,255,0.07)" stroke-width="0.9" stroke-linecap="round" '
        f'd="M {cx - g_r*0.38:.3f} {cy - g_r*0.62:.3f} A {g_r*0.6:.3f} {g_r*0.6:.3f} 0 0 1 '
        f'{cx + g_r*0.38:.3f} {cy - g_r*0.62:.3f}"/>'
    )
    # Reflejo inferior tenue (fresnel)
    glint_fresnel = (
        f'<path fill="none" stroke="rgba(255,255,255,0.04)" stroke-width="1.2" stroke-linecap="round" '
        f'd="M {cx - g_r*0.45:.3f} {cy + g_r*0.65:.3f} A {g_r*0.72:.3f} {g_r*0.72:.3f} 0 0 0 '
        f'{cx + g_r*0.45:.3f} {cy + g_r*0.65:.3f}"/>'
    )

    defs = (
        # Filtro bloom ambiente
        '<filter id="dcBloom" x="-80%" y="-80%" width="260%" height="260%">'
        '<feGaussianBlur in="SourceGraphic" stdDeviation="3.5" result="bl"/>'
        '<feMerge><feMergeNode in="bl"/></feMerge>'
        '</filter>'
        # Filtro glow del core (blur + merge con original)
        '<filter id="dcCoreGlow" x="-60%" y="-60%" width="220%" height="220%">'
        '<feGaussianBlur in="SourceGraphic" stdDeviation="1.2" result="b"/>'
        '<feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>'
        '</filter>'
        # Filtro glow suave para filamentos
        '<filter id="dcFilGlow" x="-40%" y="-40%" width="180%" height="180%">'
        '<feGaussianBlur in="SourceGraphic" stdDeviation="0.7" result="b"/>'
        '<feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>'
        '</filter>'
        # Core gradient radial
        f'<radialGradient id="dcCore" cx="44%" cy="40%" r="64%" fx="42%" fy="38%">'
        f'<stop offset="0%" stop-color="{p["c1"]}"/>'
        f'<stop offset="22%" stop-color="{p["c1"]}"/>'
        f'<stop offset="48%" stop-color="{p["c2"]}"/>'
        f'<stop offset="70%" stop-color="{p["c1"]}"/>'
        f'<stop offset="88%" stop-color="{p["c0"]}"/>'
        f'<stop offset="100%" stop-color="{p["c3"]}"/>'
        f'</radialGradient>'
        # Bloom ambiental radial
        f'<radialGradient id="dcOuter" cx="50%" cy="48%" r="56%">'
        f'<stop offset="0%" stop-color="{p["o_a"]}"/>'
        f'<stop offset="50%" stop-color="{p["o_b"]}"/>'
        f'<stop offset="100%" stop-color="rgba(0,0,0,0)"/>'
        f'</radialGradient>'
        # Gradiente plasma conductos
        f'<linearGradient id="dcReactPlasma" x1="0%" y1="0%" x2="100%" y2="0%">'
        f'<stop offset="0%" stop-color="{p["pl_a"]}"/>'
        f'<stop offset="100%" stop-color="{p["pl_b"]}"/>'
        f'</linearGradient>'
        # Gradiente bracket (metálico)
        f'<linearGradient id="dcBracketGrad" x1="0%" y1="0%" x2="0%" y2="100%">'
        f'<stop offset="0%" stop-color="{p["bracket"]}"/>'
        f'<stop offset="100%" stop-color="rgba(0,0,0,0)"/>'
        f'</linearGradient>'
        # Gradiente filamentos
        f'<linearGradient id="dcFilamentGrad" x1="0%" y1="0%" x2="100%" y2="0%">'
        f'<stop offset="0%" stop-color="{p["fil_a"]}"/>'
        f'<stop offset="100%" stop-color="{p["fil_b"]}"/>'
        f'</linearGradient>'
        # Gradiente sello (ring highlight)
        f'<linearGradient id="dcSealGrad" x1="0%" y1="0%" x2="100%" y2="100%">'
        f'<stop offset="0%" stop-color="{p["seal"]}"/>'
        f'<stop offset="50%" stop-color="rgba(255,255,255,0.08)"/>'
        f'<stop offset="100%" stop-color="{p["seal"]}"/>'
        f'</linearGradient>'
        # Placa hex de fondo
        f'<linearGradient id="dcHexBg" x1="30%" y1="0%" x2="70%" y2="100%">'
        f'<stop offset="0%" stop-color="rgba(10,14,20,0.98)"/>'
        f'<stop offset="100%" stop-color="rgba(6,9,14,0.99)"/>'
        f'</linearGradient>'
    )

    return (
        f'<svg class="dc-reactor-svg" viewBox="0 0 100 100" width="92" height="92" '
        f'xmlns="http://www.w3.org/2000/svg" focusable="false" aria-hidden="true">'
        f'<defs>{defs}</defs>'

        # 1. Bloom ambiental exterior
        f'<circle class="dc-r-svg-outer" cx="{cx}" cy="{cy}" r="{R_OUTER_BLOOM}" '
        f'fill="url(#dcOuter)" opacity="0.65" filter="url(#dcBloom)"/>'

        # 2. Placa hex de fondo (metal)
        f'<path d="{hex_bg}" fill="url(#dcHexBg)" opacity="0.96"/>'

        # 3. Anillos técnicos (3 velocidades distintas)
        f'<g class="dc-r-svg-rot dc-r-svg-rot--rings">{rings}</g>'

        # 4. Conductos de plasma (contra-rotación)
        f'<g class="dc-r-svg-rot dc-r-svg-rot--plasma">{conduits}</g>'

        # 5. Graduaciones de medición
        f'<g class="dc-r-svg-rot dc-r-svg-rot--slots" stroke="{p["slot"]}">{slots}</g>'

        # 6. Soportes de contención mecánica (fijos)
        f'<g class="dc-r-svg-housing">{brackets}</g>'

        # 7. Carcasa hex (doble: interior shadow + exterior highlight)
        f'<g class="dc-r-svg-housing">'
        f'<path fill="none" stroke="{p["hin"]}" stroke-width="1.1" d="{hex_i}"/>'
        f'<path fill="none" stroke="{p["hout"]}" stroke-width="1.3" d="{hex_o}"/>'
        f'{rivets}'
        f'</g>'

        # 8. Anillo de graduación fino
        f'{tick_ring}'

        # 9. Sello de contención (triple anillo concéntrico)
        f'<circle cx="{cx}" cy="{cy}" r="{R_SEAL + 2.2}" fill="none" '
        f'stroke="{p["seal"]}" stroke-width="0.32" opacity="0.45"/>'
        f'<circle cx="{cx}" cy="{cy}" r="{R_SEAL}" fill="none" '
        f'stroke="url(#dcSealGrad)" stroke-width="1.2" opacity="0.72"/>'
        f'<circle cx="{cx}" cy="{cy}" r="{R_SEAL - 1.8}" fill="none" '
        f'stroke="rgba(0,0,0,0.5)" stroke-width="0.8" opacity="0.9"/>'

        # 10. Filamentos de energía (filtro glow)
        f'<g class="dc-r-svg-filaments" filter="url(#dcFilGlow)">{filaments}</g>'

        # 11. Núcleo con animación según estado
        f'<g class="{core_cls}">'
        f'<circle cx="{cx}" cy="{cy}" r="{R_CORE}" fill="url(#dcCore)" filter="url(#dcCoreGlow)"/>'
        # Capa de saturación interna (profundidad extra)
        f'<circle cx="{cx}" cy="{cy}" r="{R_CORE * 0.62:.3f}" fill="{p["c2"]}" opacity="0.22"/>'
        f'<circle cx="{cx}" cy="{cy}" r="{R_CORE}" fill="none" '
        f'stroke="rgba(255,255,255,0.12)" stroke-width="0.5"/>'
        # 12. Glints especulares
        f'{glint_main}{glint_soft}{glint_fresnel}'
        f'</g>'
        f'</svg>'
    )


def _css_reactor_panel() -> str:
    """Reactor de salud crítica — celda energética encapsulada, look sci-fi premium."""
    return """
    <style>
    @media (prefers-reduced-motion: reduce) {
        .dc-reactor, .dc-reactor *, .dc-r-svg-rot, .dc-r-svg-filaments {
            animation: none !important;
            transition: none !important;
        }
    }

    /* ══════════════════════════════════════════════════════
       CONTENEDOR EMBEBIDO
    ══════════════════════════════════════════════════════ */
    .dc-criticos-unificado__reactor-host .dc-reactor--embedded {
        position: relative;
        overflow: hidden;
        flex: 1 1 auto;
        width: 100%;
        max-width: 100%;
        min-height: 0;
        min-width: 0;
        display: flex;
        align-items: center;
        justify-content: center;
        border: none;
        border-radius: 0;
        box-shadow: none;
        contain: layout paint;
    }

    /* ══════════════════════════════════════════════════════
       CAMPO DE GLOW AMBIENTAL (fondo del panel derecho)
    ══════════════════════════════════════════════════════ */
    .dc-reactor__glow-field {
        position: absolute;
        inset: -18%;
        pointer-events: none;
        z-index: 0;
        opacity: 0.6;
        background:
            radial-gradient(ellipse 65% 55% at 42% 35%, rgba(255,255,255,0.055) 0%, transparent 48%),
            radial-gradient(circle at 50% 50%, rgba(56,189,248,0.12) 0%, rgba(56,189,248,0.03) 45%, transparent 70%);
        filter: saturate(1.08);
        animation: dc-r-glow-drift 11s ease-in-out infinite;
    }
    @keyframes dc-r-glow-drift {
        0%, 100% { transform: scale(1) translate(0,0); opacity: 0.52; }
        33%       { transform: scale(1.04) translate(0.8%,-0.8%); opacity: 0.64; }
        66%       { transform: scale(1.02) translate(-0.5%, 0.5%); opacity: 0.58; }
    }

    /* ══════════════════════════════════════════════════════
       SCANLINES CRT (overlay cinematográfico)
    ══════════════════════════════════════════════════════ */
    .dc-reactor__scan {
        position: absolute;
        inset: 0;
        pointer-events: none;
        z-index: 6;
        background: repeating-linear-gradient(
            0deg,
            transparent,
            transparent 2px,
            rgba(255,255,255,0.018) 2px,
            rgba(255,255,255,0.018) 3px
        );
        opacity: 0.28;
        mix-blend-mode: overlay;
    }

    /* ══════════════════════════════════════════════════════
       LÍNEA DE SCAN HORIZONTAL (sweep cinematic)
    ══════════════════════════════════════════════════════ */
    .dc-reactor__sweep {
        position: absolute;
        left: 0; right: 0;
        height: 1px;
        background: linear-gradient(90deg,
            transparent 0%,
            rgba(56,189,248,0.0) 8%,
            rgba(56,189,248,0.28) 35%,
            rgba(34,211,238,0.35) 50%,
            rgba(56,189,248,0.28) 65%,
            rgba(56,189,248,0.0) 92%,
            transparent 100%);
        pointer-events: none;
        z-index: 7;
        animation: dc-r-sweep 5.5s linear infinite;
        opacity: 0;
    }
    @keyframes dc-r-sweep {
        0%   { top: 5%;  opacity: 0; }
        8%   { opacity: 0.7; }
        92%  { opacity: 0.5; }
        100% { top: 95%; opacity: 0; }
    }

    /* ══════════════════════════════════════════════════════
       VIÑETA DE BORDES (profundidad)
    ══════════════════════════════════════════════════════ */
    .dc-reactor__vignette {
        position: absolute;
        inset: 0;
        pointer-events: none;
        z-index: 5;
        background: radial-gradient(ellipse 85% 85% at 50% 50%,
            transparent 55%,
            rgba(0,0,0,0.28) 80%,
            rgba(0,0,0,0.52) 100%);
    }

    /* ══════════════════════════════════════════════════════
       STACK PRINCIPAL (SVG + status)
    ══════════════════════════════════════════════════════ */
    .dc-reactor__embedded-stack {
        position: relative;
        z-index: 2;
        display: flex;
        flex-direction: row;
        flex-wrap: nowrap;
        align-items: center;
        justify-content: center;
        width: 100%;
        max-width: 100%;
        min-width: 0;
        box-sizing: border-box;
        padding: 0.35rem 0.42rem;
        gap: 0.38rem;
    }
    @media (max-width: 720px) {
        .dc-reactor__embedded-stack {
            flex-direction: column;
            padding: 0.5rem 0.55rem;
        }
        .dc-reactor__status { text-align: center; }
    }

    /* ══════════════════════════════════════════════════════
       CONTENEDOR DEL SVG — marco de celda
    ══════════════════════════════════════════════════════ */
    .dc-reactor__viz {
        position: relative;
        width: 92px;
        height: 92px;
        flex-shrink: 0;
        isolation: isolate;
    }

    /* Marco metálico exterior alrededor del SVG */
    .dc-reactor__viz::before {
        content: "";
        position: absolute;
        inset: -3px;
        border-radius: 4px;
        background: transparent;
        border: 1px solid rgba(255,255,255,0.06);
        pointer-events: none;
        z-index: 8;
    }
    /* Corner brackets decorativos (pseudo-elemento sobre el viz) */
    .dc-reactor__viz::after {
        content: "";
        position: absolute;
        inset: -4px;
        border-radius: 3px;
        background:
            linear-gradient(to right, rgba(255,255,255,0.14) 6px, transparent 6px) top left,
            linear-gradient(to bottom, rgba(255,255,255,0.14) 6px, transparent 6px) top left,
            linear-gradient(to left, rgba(255,255,255,0.14) 6px, transparent 6px) top right,
            linear-gradient(to bottom, rgba(255,255,255,0.14) 6px, transparent 6px) top right,
            linear-gradient(to right, rgba(255,255,255,0.14) 6px, transparent 6px) bottom left,
            linear-gradient(to top, rgba(255,255,255,0.14) 6px, transparent 6px) bottom left,
            linear-gradient(to left, rgba(255,255,255,0.14) 6px, transparent 6px) bottom right,
            linear-gradient(to top, rgba(255,255,255,0.14) 6px, transparent 6px) bottom right;
        background-size: 10px 10px;
        background-repeat: no-repeat;
        pointer-events: none;
        z-index: 9;
    }

    .dc-reactor-svg {
        position: absolute;
        inset: 0;
        display: block;
        width: 92px;
        height: 92px;
        overflow: visible;
        pointer-events: none;
    }

    /* ══════════════════════════════════════════════════════
       ROTACIONES DE CAPAS SVG
    ══════════════════════════════════════════════════════ */
    .dc-r-svg-rot {
        transform-box: fill-box;
        transform-origin: 50% 50%;
    }
    .dc-r-svg-rot--rings  { animation: dc-svg-spin 42s linear infinite; }
    .dc-r-svg-rot--plasma { animation: dc-svg-spin 24s linear infinite reverse; }
    .dc-r-svg-rot--slots  { animation: dc-svg-spin 96s linear infinite; }
    @keyframes dc-svg-spin { to { transform: rotate(360deg); } }

    /* Filamentos: rotación muy lenta */
    .dc-r-svg-filaments {
        transform-box: fill-box;
        transform-origin: 50px 50px;
        animation: dc-svg-spin 18s linear infinite;
    }

    /* Bloom ambiental */
    .dc-r-svg-outer {
        transform-origin: 50px 50px;
        animation: dc-svg-outer-pulse 8s ease-in-out infinite;
    }
    @keyframes dc-svg-outer-pulse {
        0%, 100% { opacity: 0.6;  transform: scale(1); }
        50%       { opacity: 0.82; transform: scale(1.03); }
    }

    /* ══════════════════════════════════════════════════════
       ANIMACIONES DEL CORE POR ESTADO
    ══════════════════════════════════════════════════════ */
    .dc-r-svg-core {
        transform-box: fill-box;
        transform-origin: 50px 50px;
    }
    .dc-r-svg-core--drift {
        animation: dc-svg-core-drift 10s ease-in-out infinite;
    }
    @keyframes dc-svg-core-drift {
        0%, 100% { transform: translate(0,0) scale(1); }
        25%       { transform: translate(0.28px,-0.22px) scale(1.008); }
        75%       { transform: translate(-0.18px, 0.25px) scale(0.995); }
    }
    .dc-r-svg-core--pulse {
        animation: dc-r-unstable-core 1.2s ease-in-out infinite;
    }
    @keyframes dc-r-unstable-core {
        0%, 100% { transform: scale(1) rotate(0deg); }
        50%       { transform: scale(1.055) rotate(0.4deg); }
    }
    .dc-r-svg-core--shake {
        animation: dc-r-crit-shake 0.18s linear infinite;
    }
    @keyframes dc-r-crit-shake {
        0%   { transform: translate(0,0); }
        20%  { transform: translate(1.8px,-1.8px); }
        40%  { transform: translate(-1.8px, 1.2px); }
        60%  { transform: translate(1.5px, 1.8px); }
        80%  { transform: translate(-1.2px,-1.5px); }
        100% { transform: translate(0,0); }
    }
    .dc-r-svg-core--melt {
        animation: dc-r-melt-core 0.48s ease-in-out infinite;
    }
    @keyframes dc-r-melt-core {
        0%, 100% { transform: scale(1) skewX(0deg) skewY(0deg); }
        30%       { transform: scale(1.09) skewX(-1.8deg) skewY(0.4deg); }
        65%       { transform: scale(1.05) skewX(1.5deg) skewY(-0.3deg); }
    }

    /* ══════════════════════════════════════════════════════
       OVERLAY NUMÉRICO EN EL CORE
    ══════════════════════════════════════════════════════ */
    .dc-reactor__core-overlay {
        position: absolute;
        inset: 20%;
        display: flex;
        align-items: center;
        justify-content: center;
        z-index: 4;
        pointer-events: none;
        font-size: 0.7rem;
        font-weight: 900;
        font-variant-numeric: tabular-nums;
        letter-spacing: -0.04em;
    }
    .dc-reactor__core-label {
        position: relative;
        text-shadow: 0 1px 3px rgba(0,0,0,0.8);
    }

    /* ══════════════════════════════════════════════════════
       BARRA DE ESTADO TEXTUAL
    ══════════════════════════════════════════════════════ */
    .dc-reactor__status {
        flex: 1 1 0;
        min-width: 0;
        max-width: 100%;
        text-align: left;
    }
    .dc-reactor__title {
        font-size: 0.76rem;
        font-weight: 800;
        letter-spacing: -0.02em;
        line-height: 1.18;
        margin: 0 0 0.16rem 0;
    }
    .dc-reactor__meter {
        height: 4px;
        border-radius: 4px;
        background: rgba(0,0,0,0.55);
        overflow: hidden;
        margin-bottom: 0.13rem;
        border: 1px solid rgba(255,255,255,0.08);
        box-shadow: inset 0 1px 2px rgba(0,0,0,0.5);
    }
    .dc-reactor__meter-fill {
        height: 100%;
        border-radius: 4px;
        transition: width 0.6s cubic-bezier(0.22,1,0.36,1);
    }
    .dc-reactor__ratio-line {
        font-size: 0.6rem;
        font-weight: 700;
        color: #c9d1d9;
        margin-bottom: 0.1rem;
        font-variant-numeric: tabular-nums;
        letter-spacing: 0.03em;
        line-height: 1.25;
    }
    .dc-reactor__flavor {
        font-size: 0.58rem;
        line-height: 1.38;
        color: #8b949e;
        margin: 0;
        display: -webkit-box;
        -webkit-line-clamp: 3;
        -webkit-box-orient: vertical;
        overflow: hidden;
        word-break: break-word;
    }

    /* ══════════════════════════════════════════════════════
       ESTADO: OFFLINE / IDLE
    ══════════════════════════════════════════════════════ */
    .dc-reactor--offline, .dc-reactor--idle {
        background:
            radial-gradient(ellipse 90% 75% at 50% 105%, rgba(48,54,61,0.28), transparent 52%),
            linear-gradient(158deg, #111820 0%, #090d13 100%);
    }
    .dc-reactor--offline .dc-r-svg-rot,
    .dc-reactor--idle    .dc-r-svg-rot,
    .dc-reactor--offline .dc-r-svg-filaments,
    .dc-reactor--idle    .dc-r-svg-filaments  { animation: none !important; }
    .dc-reactor--offline .dc-r-svg-outer,
    .dc-reactor--idle    .dc-r-svg-outer      { animation: none; opacity: 0.35; }
    .dc-reactor--offline .dc-reactor__title,
    .dc-reactor--idle    .dc-reactor__title   { color: #8b949e; }
    .dc-reactor--offline .dc-reactor__glow-field,
    .dc-reactor--idle    .dc-reactor__glow-field {
        opacity: 0.15;
        background: radial-gradient(circle at 50% 50%, rgba(110,118,129,0.12), transparent 60%);
    }
    .dc-reactor--offline .dc-reactor__core-overlay,
    .dc-reactor--idle    .dc-reactor__core-overlay { color: #6b7280; }
    .dc-reactor--offline .dc-reactor__meter-fill,
    .dc-reactor--idle    .dc-reactor__meter-fill   { width: 0 !important; background: #374151; }
    .dc-reactor--offline .dc-reactor__sweep,
    .dc-reactor--idle    .dc-reactor__sweep        { display: none; }

    /* ══════════════════════════════════════════════════════
       ESTADO: ESTABLE
    ══════════════════════════════════════════════════════ */
    .dc-reactor--estable {
        background:
            radial-gradient(ellipse 95% 105% at 18% 28%, rgba(45,212,191,0.2), transparent 50%),
            radial-gradient(ellipse 65% 85% at 88% 62%, rgba(74,222,128,0.16), transparent 46%),
            linear-gradient(148deg, #091610 0%, #0c1210 38%, #060f0d 100%);
        animation: dc-r-stable-breathe 6s ease-in-out infinite;
    }
    @keyframes dc-r-stable-breathe {
        0%, 100% { filter: brightness(1) saturate(1); }
        50%       { filter: brightness(1.04) saturate(1.05); }
    }
    .dc-reactor--estable .dc-reactor__glow-field {
        background:
            radial-gradient(ellipse 52% 48% at 40% 34%, rgba(255,255,255,0.065) 0%, transparent 48%),
            radial-gradient(circle at 44% 42%, rgba(74,222,128,0.35), rgba(34,211,238,0.1) 44%, transparent 70%);
        opacity: 0.82;
        filter: saturate(1.15);
    }
    .dc-reactor--estable .dc-reactor__title {
        color: #86efac;
        text-shadow: 0 0 18px rgba(74,222,128,0.38), 0 0 6px rgba(34,211,238,0.22);
    }
    .dc-reactor--estable .dc-reactor__core-overlay { color: #022c0d; }
    .dc-reactor--estable .dc-reactor__core-label {
        text-shadow: 0 0 10px rgba(187,247,208,0.6), 0 1px 2px rgba(0,0,0,0.4);
    }
    .dc-reactor--estable .dc-reactor__meter-fill {
        background: linear-gradient(90deg, #16a34a, #4ade80, #22d3ee, #4ade80);
        box-shadow: 0 0 18px rgba(74,222,128,0.6), 0 0 6px rgba(34,211,238,0.4);
    }
    .dc-reactor--estable .dc-reactor__sweep {
        background: linear-gradient(90deg,
            transparent 0%, rgba(74,222,128,0.0) 10%,
            rgba(74,222,128,0.3) 40%, rgba(34,211,238,0.38) 50%,
            rgba(74,222,128,0.3) 60%, rgba(74,222,128,0.0) 90%, transparent 100%);
    }
    .dc-reactor--estable .dc-reactor__viz::after { opacity: 0.6; }

    /* ══════════════════════════════════════════════════════
       ESTADO: INESTABLE
    ══════════════════════════════════════════════════════ */
    .dc-reactor--inestable {
        background:
            radial-gradient(ellipse 82% 98% at 22% 22%, rgba(251,191,36,0.26), transparent 48%),
            radial-gradient(ellipse 58% 75% at 82% 68%, rgba(248,113,113,0.1), transparent 43%),
            linear-gradient(130deg, #1a1106 0%, #0d1117 46%, #150907 100%);
        animation: dc-r-unstable-flicker 2.4s steps(2, end) infinite;
    }
    @keyframes dc-r-unstable-flicker {
        0%, 100% { opacity: 1; filter: brightness(1) saturate(1); }
        50%       { opacity: 0.93; filter: brightness(1.1) saturate(1.1); }
    }
    .dc-reactor--inestable .dc-r-svg-rot--rings  { animation-duration: 14s; }
    .dc-reactor--inestable .dc-r-svg-rot--plasma { animation-duration: 8s; }
    .dc-reactor--inestable .dc-r-svg-rot--slots  { animation-duration: 55s; }
    .dc-reactor--inestable .dc-r-svg-filaments   { animation-duration: 12s; }
    .dc-reactor--inestable .dc-reactor__glow-field {
        background:
            radial-gradient(ellipse 48% 42% at 46% 38%, rgba(255,255,255,0.055) 0%, transparent 46%),
            radial-gradient(circle at 50% 44%, rgba(251,191,36,0.35), transparent 62%);
        animation: dc-r-glow-drift 3.2s ease-in-out infinite;
        filter: saturate(1.12);
    }
    .dc-reactor--inestable .dc-reactor__title {
        color: #fcd34d;
        text-shadow: 0 0 16px rgba(251,191,36,0.4), 0 0 5px rgba(253,224,71,0.25);
    }
    .dc-reactor--inestable .dc-reactor__core-overlay { color: #3d1f02; }
    .dc-reactor--inestable .dc-reactor__core-label {
        text-shadow: 0 0 8px rgba(254,243,199,0.45), 0 1px 2px rgba(0,0,0,0.4);
    }
    .dc-reactor--inestable .dc-reactor__meter-fill {
        background: linear-gradient(90deg, #ea580c, #fbbf24, #fde68a, #f59e0b);
        box-shadow: 0 0 16px rgba(251,191,36,0.5), 0 0 5px rgba(234,88,12,0.35);
    }
    .dc-reactor--inestable .dc-reactor__sweep {
        background: linear-gradient(90deg,
            transparent 0%, rgba(251,191,36,0.0) 10%,
            rgba(251,191,36,0.32) 40%, rgba(253,224,71,0.4) 50%,
            rgba(251,191,36,0.32) 60%, rgba(251,191,36,0.0) 90%, transparent 100%);
    }

    /* ══════════════════════════════════════════════════════
       ESTADO: CRÍTICO
    ══════════════════════════════════════════════════════ */
    .dc-reactor--critico {
        background:
            radial-gradient(ellipse 98% 88% at 50% -8%, rgba(249,115,22,0.38), transparent 40%),
            radial-gradient(ellipse 75% 65% at 8% 78%, rgba(239,68,68,0.14), transparent 48%),
            linear-gradient(152deg, #1e0805 0%, #0d1117 36%, #1a0604 100%);
        animation: dc-r-crit-pulse 0.7s ease-in-out infinite;
    }
    @keyframes dc-r-crit-pulse {
        0%, 100% { filter: brightness(1) saturate(1); }
        50%       { filter: brightness(1.12) saturate(1.18); }
    }
    .dc-reactor--critico .dc-r-svg-rot--rings  { animation-duration: 3.0s; }
    .dc-reactor--critico .dc-r-svg-rot--plasma { animation-duration: 2.2s; }
    .dc-reactor--critico .dc-r-svg-rot--slots  { animation-duration: 9s; }
    .dc-reactor--critico .dc-r-svg-filaments   { animation-duration: 4s; }
    .dc-reactor--critico .dc-r-svg-outer {
        animation: dc-svg-outer-urgent 0.75s ease-in-out infinite;
    }
    @keyframes dc-svg-outer-urgent {
        0%, 100% { opacity: 0.65; transform: scale(1); }
        50%       { opacity: 0.92; transform: scale(1.05); }
    }
    .dc-reactor--critico .dc-reactor__glow-field {
        background:
            radial-gradient(ellipse 42% 38% at 50% 36%, rgba(255,255,255,0.08) 0%, transparent 44%),
            radial-gradient(circle at 50% 38%, rgba(249,115,22,0.42), rgba(239,68,68,0.16) 50%, transparent 66%);
        opacity: 0.92;
        filter: saturate(1.18);
    }
    .dc-reactor--critico .dc-reactor__title {
        color: #fb923c;
        text-shadow: 0 0 20px rgba(249,115,22,0.5), 0 0 6px rgba(239,68,68,0.3);
    }
    .dc-reactor--critico .dc-reactor__core-overlay { color: #1a0501; }
    .dc-reactor--critico .dc-reactor__core-label {
        text-shadow: 0 0 10px rgba(254,215,170,0.4), 0 1px 2px rgba(0,0,0,0.55);
    }
    .dc-reactor--critico .dc-reactor__meter-fill {
        background: linear-gradient(90deg, #b91c1c, #ea580c, #fb923c, #f97316);
        box-shadow: 0 0 20px rgba(249,115,22,0.65), 0 0 8px rgba(220,38,38,0.5);
    }
    .dc-reactor--critico .dc-reactor__sweep {
        background: linear-gradient(90deg,
            transparent 0%, rgba(249,115,22,0.0) 10%,
            rgba(249,115,22,0.35) 40%, rgba(254,166,100,0.45) 50%,
            rgba(249,115,22,0.35) 60%, rgba(249,115,22,0.0) 90%, transparent 100%);
        animation-duration: 2.5s;
    }

    /* ══════════════════════════════════════════════════════
       ESTADO: MELTDOWN
    ══════════════════════════════════════════════════════ */
    .dc-reactor--meltdown {
        background:
            radial-gradient(ellipse 108% 88% at 50% 118%, rgba(220,38,38,0.6), transparent 50%),
            radial-gradient(circle at 25% 25%, rgba(244,114,182,0.24), transparent 36%),
            radial-gradient(circle at 75% 20%, rgba(248,113,113,0.2), transparent 33%),
            linear-gradient(170deg, #2c0408 0%, #0d1117 30%, #1c0206 100%);
        animation: dc-r-melt-bg 0.88s ease-in-out infinite;
    }
    @keyframes dc-r-melt-bg {
        0%, 100% { filter: brightness(1) saturate(1); }
        50%       { filter: brightness(1.18) saturate(1.42); }
    }
    .dc-reactor--meltdown .dc-r-svg-rot--rings  { animation-duration: 4.2s; }
    .dc-reactor--meltdown .dc-r-svg-rot--plasma { animation-duration: 3.0s; }
    .dc-reactor--meltdown .dc-r-svg-rot--slots  { animation-duration: 13s; }
    .dc-reactor--meltdown .dc-r-svg-filaments   { animation-duration: 2.8s; }
    .dc-reactor--meltdown .dc-r-svg-outer {
        animation: dc-r-melt-outer 1.0s ease-in-out infinite;
    }
    @keyframes dc-r-melt-outer {
        0%, 100% { opacity: 0.58; transform: scale(1); }
        50%       { opacity: 0.96; transform: scale(1.08); }
    }
    .dc-reactor--meltdown .dc-reactor__glow-field {
        background:
            radial-gradient(circle at 50% 32%, rgba(255,255,255,0.1) 0%, transparent 32%),
            radial-gradient(circle at 50% 50%, rgba(220,38,38,0.48), rgba(244,114,182,0.2) 42%, transparent 60%);
        opacity: 1;
        animation: dc-r-melt-glow 1.1s ease-in-out infinite;
        filter: saturate(1.28);
    }
    @keyframes dc-r-melt-glow {
        0%, 100% { transform: scale(1); opacity: 0.88; }
        50%       { transform: scale(1.14); opacity: 1; }
    }
    .dc-reactor--meltdown .dc-reactor__title {
        color: #fecaca;
        animation: dc-r-melt-glitch 2.0s steps(2, end) infinite;
        text-shadow: 0 0 22px rgba(220,38,38,0.6), 0 0 8px rgba(244,114,182,0.35);
    }
    @keyframes dc-r-melt-glitch {
        0%, 86%, 100% { transform: translateX(0) skewX(0deg); }
        88%            { transform: translateX(-3.5px) skewX(-1deg); }
        92%            { transform: translateX(3.5px) skewX(1deg); }
    }
    .dc-reactor--meltdown .dc-reactor__core-overlay { color: #fef2f2; }
    .dc-reactor--meltdown .dc-reactor__core-label {
        text-shadow: 0 0 12px rgba(254,202,202,0.6), 0 1px 3px rgba(0,0,0,0.65);
    }
    .dc-reactor--meltdown .dc-reactor__meter-fill {
        background: linear-gradient(90deg, #450a0a, #dc2626, #f472b6, #fb7185, #dc2626);
        box-shadow: 0 0 24px rgba(220,38,38,0.85), 0 0 10px rgba(244,114,182,0.5);
        animation: dc-r-melt-bar 0.6s ease-in-out infinite;
    }
    @keyframes dc-r-melt-bar {
        0%, 100% { opacity: 1; }
        50%       { opacity: 0.74; }
    }
    .dc-reactor--meltdown .dc-reactor__sweep {
        background: linear-gradient(90deg,
            transparent 0%, rgba(220,38,38,0.0) 8%,
            rgba(220,38,38,0.38) 38%, rgba(248,113,113,0.5) 50%,
            rgba(220,38,38,0.38) 62%, rgba(220,38,38,0.0) 92%, transparent 100%);
        animation-duration: 1.8s;
    }
    .dc-reactor--meltdown .dc-reactor__scan {
        opacity: 0.55;
        animation: dc-r-melt-scan 2.2s linear infinite;
    }
    @keyframes dc-r-melt-scan { to { transform: translateY(6px); } }

    /* Leak de energía (meltdown) */
    .dc-reactor__leak {
        position: absolute;
        width: 115%;
        height: 45%;
        left: -7.5%;
        bottom: -14%;
        background:
            radial-gradient(ellipse 82% 62% at 50% 82%, rgba(220,38,38,0.35), transparent 74%),
            radial-gradient(ellipse 52% 42% at 32% 62%, rgba(244,114,182,0.14), transparent 72%);
        pointer-events: none;
        z-index: 1;
        animation: dc-r-melt-leak 1.6s ease-in-out infinite;
    }
    @keyframes dc-r-melt-leak {
        0%, 100% { opacity: 0.5;  transform: scaleY(1) translateY(0); }
        50%       { opacity: 0.95; transform: scaleY(1.25) translateY(-5px); }
    }
    .dc-reactor--meltdown .dc-reactor__leak { display: block; }
    .dc-reactor:not(.dc-reactor--meltdown) .dc-reactor__leak { display: none; }

    /* ══════════════════════════════════════════════════════
       CORNER BRACKETS: color por estado
    ══════════════════════════════════════════════════════ */
    .dc-reactor--estable  .dc-reactor__viz::after { --bracket-color: rgba(74,222,128,0.35); }
    .dc-reactor--inestable .dc-reactor__viz::after { --bracket-color: rgba(251,191,36,0.35); }
    .dc-reactor--critico   .dc-reactor__viz::after { --bracket-color: rgba(249,115,22,0.4); }
    .dc-reactor--meltdown  .dc-reactor__viz::after { --bracket-color: rgba(220,38,38,0.45); }

    </style>
    """


def _injectar_estilos():
    st.markdown(_css_command_center(), unsafe_allow_html=True)
    st.markdown(_css_reactor_panel(), unsafe_allow_html=True)


def _render_live_background_js() -> None:
    """
    Fondo animado command center (canvas + JS): rejilla con acentos, auroras, scanlines y partículas.
    Más llamativo que la versión inicial; respeta prefers-reduced-motion.
    Se monta en el DOM padre del iframe cuando el sandbox lo permite; si no, no rompe la app.
    """
    snippet = r"""
<div id="dc-bg-boot" style="height:0;width:0;overflow:hidden;position:absolute;" aria-hidden="true"></div>
<script>
(function () {
  function docWin() {
    try {
      if (window.parent && window.parent !== window && window.parent.document) {
        return { d: window.parent.document, w: window.parent };
      }
    } catch (e) {}
    return { d: document, w: window };
  }
  var _ = docWin();
  var doc = _.d;
  var win = _.w;
  if (doc.getElementById("dc-live-bg-host")) return;

  var cont = doc.querySelector('[data-testid="stAppViewContainer"]');
  if (!cont) return;

  var reduced = false;
  try {
    reduced = win.matchMedia && win.matchMedia("(prefers-reduced-motion: reduce)").matches;
  } catch (e) {}

  var host = doc.createElement("div");
  host.id = "dc-live-bg-host";
  host.setAttribute("aria-hidden", "true");
  var cv = doc.createElement("canvas");
  cv.id = "dc-live-bg-canvas";
  host.appendChild(cv);
  cont.insertBefore(host, cont.firstChild);

  var ctx = cv.getContext("2d");
  if (!ctx) return;

  var t = 0;
  var w = 0, h = 0;
  var particles = [];
  var i, p, n;

  function resize() {
    w = win.innerWidth || doc.documentElement.clientWidth || 1200;
    h = win.innerHeight || doc.documentElement.clientHeight || 800;
    cv.width = Math.floor(w * (win.devicePixelRatio || 1));
    cv.height = Math.floor(h * (win.devicePixelRatio || 1));
    cv.style.width = w + "px";
    cv.style.height = h + "px";
    ctx.setTransform(win.devicePixelRatio || 1, 0, 0, win.devicePixelRatio || 1, 0, 0);
    particles.length = 0;
    n = Math.min(110, Math.floor((w * h) / 14000));
    for (i = 0; i < n; i++) {
      particles.push({
        x: Math.random() * w,
        y: Math.random() * h,
        vx: (Math.random() - 0.5) * 0.38,
        vy: (Math.random() - 0.5) * 0.38,
        r: 0.4 + Math.random() * 1.8,
        a: 0.12 + Math.random() * 0.35,
        ph: Math.random() * Math.PI * 2
      });
    }
  }
  resize();
  try {
    win.addEventListener("resize", resize);
  } catch (e) {}

  function drawStatic() {
    ctx.clearRect(0, 0, w, h);
    var g0 = ctx.createRadialGradient(w * 0.2, h * 0.15, 0, w * 0.2, h * 0.15, w * 0.65);
    g0.addColorStop(0, "rgba(56, 189, 248, 0.12)");
    g0.addColorStop(1, "rgba(0,0,0,0)");
    ctx.fillStyle = g0;
    ctx.fillRect(0, 0, w, h);
    var g1 = ctx.createRadialGradient(w * 0.85, h * 0.55, 0, w * 0.85, h * 0.55, h * 0.55);
    g1.addColorStop(0, "rgba(129, 140, 248, 0.1)");
    g1.addColorStop(1, "rgba(0,0,0,0)");
    ctx.fillStyle = g1;
    ctx.fillRect(0, 0, w, h);
    var step = 48;
    ctx.lineWidth = 0.5;
    var j0, x0, y0;
    for (j0 = -1; j0 * step < w + step; j0++) {
      x0 = j0 * step;
      ctx.strokeStyle = (j0 % 5 === 0) ? "rgba(88, 166, 255, 0.2)" : "rgba(48, 54, 61, 0.22)";
      ctx.beginPath();
      ctx.moveTo(x0, 0);
      ctx.lineTo(x0, h);
      ctx.stroke();
    }
    for (j0 = -1; j0 * step < h + step; j0++) {
      y0 = j0 * step;
      ctx.strokeStyle = (j0 % 5 === 0) ? "rgba(34, 211, 238, 0.14)" : "rgba(48, 54, 61, 0.18)";
      ctx.beginPath();
      ctx.moveTo(0, y0);
      ctx.lineTo(w, y0);
      ctx.stroke();
    }
  }

  function loop() {
    if (reduced) {
      drawStatic();
      return;
    }
    t += 0.022;
    ctx.clearRect(0, 0, w, h);

    var step = 44;
    var drift = (t * 16) % step;
    ctx.lineWidth = 0.5;
    var j, ix;
    for (j = -1; j * step < w + step; j++) {
      ix = j * step + drift;
      ctx.strokeStyle = (j % 5 === 0) ? "rgba(88, 166, 255, 0.32)" : "rgba(56, 66, 82, 0.28)";
      ctx.beginPath();
      ctx.moveTo(ix, 0);
      ctx.lineTo(ix, h);
      ctx.stroke();
    }
    for (j = -1; j * step < h + step; j++) {
      ix = j * step - drift * 0.55;
      ctx.strokeStyle = (j % 5 === 0) ? "rgba(34, 211, 238, 0.22)" : "rgba(56, 66, 82, 0.22)";
      ctx.beginPath();
      ctx.moveTo(0, ix);
      ctx.lineTo(w, ix);
      ctx.stroke();
    }

    var gx1 = w * 0.28 + Math.sin(t * 0.42) * (w * 0.12);
    var gy1 = h * 0.22 + Math.cos(t * 0.38) * (h * 0.1);
    var r1 = Math.max(w, h) * 0.48;
    var grd1 = ctx.createRadialGradient(gx1, gy1, 0, gx1, gy1, r1);
    grd1.addColorStop(0, "rgba(56, 189, 248, 0.14)");
    grd1.addColorStop(0.35, "rgba(34, 211, 238, 0.06)");
    grd1.addColorStop(1, "rgba(0,0,0,0)");
    ctx.fillStyle = grd1;
    ctx.fillRect(0, 0, w, h);

    var gx2 = w * 0.72 + Math.cos(t * 0.33) * (w * 0.14);
    var gy2 = h * 0.58 + Math.sin(t * 0.29) * (h * 0.12);
    var r2 = Math.max(w, h) * 0.42;
    var grd2 = ctx.createRadialGradient(gx2, gy2, 0, gx2, gy2, r2);
    grd2.addColorStop(0, "rgba(129, 140, 248, 0.12)");
    grd2.addColorStop(0.4, "rgba(167, 139, 250, 0.05)");
    grd2.addColorStop(1, "rgba(0,0,0,0)");
    ctx.fillStyle = grd2;
    ctx.fillRect(0, 0, w, h);

    var gx3 = w * 0.5 + Math.sin(t * 0.21) * 80;
    var gy3 = h * 0.85 + Math.cos(t * 0.25) * 50;
    var grd3 = ctx.createRadialGradient(gx3, gy3, 0, gx3, gy3, Math.max(w, h) * 0.35);
    grd3.addColorStop(0, "rgba(59, 130, 246, 0.08)");
    grd3.addColorStop(1, "rgba(0,0,0,0)");
    ctx.fillStyle = grd3;
    ctx.fillRect(0, 0, w, h);

    var scanY = (t * 42) % (h + 120) - 60;
    var scanGrad = ctx.createLinearGradient(0, scanY - 40, 0, scanY + 40);
    scanGrad.addColorStop(0, "rgba(88, 166, 255, 0)");
    scanGrad.addColorStop(0.45, "rgba(147, 197, 253, 0.07)");
    scanGrad.addColorStop(0.55, "rgba(34, 211, 238, 0.09)");
    scanGrad.addColorStop(1, "rgba(88, 166, 255, 0)");
    ctx.fillStyle = scanGrad;
    ctx.fillRect(0, scanY - 40, w, 80);

    var scanY2 = h - ((t * 28) % (h + 100)) + 20;
    var scanGrad2 = ctx.createLinearGradient(0, scanY2 - 25, 0, scanY2 + 25);
    scanGrad2.addColorStop(0, "rgba(129, 140, 248, 0)");
    scanGrad2.addColorStop(0.5, "rgba(167, 139, 250, 0.06)");
    scanGrad2.addColorStop(1, "rgba(129, 140, 248, 0)");
    ctx.fillStyle = scanGrad2;
    ctx.fillRect(0, scanY2 - 25, w, 50);

    ctx.strokeStyle = "rgba(88, 166, 255, 0.14)";
    ctx.lineWidth = 1.2;
    ctx.beginPath();
    ctx.moveTo(0, (h * 0.42 + Math.sin(t * 0.9) * 22) % h);
    ctx.lineTo(w, (h * 0.42 + Math.sin(t * 0.9) * 22 + 1) % h);
    ctx.stroke();
    ctx.strokeStyle = "rgba(34, 211, 238, 0.1)";
    ctx.lineWidth = 0.8;
    ctx.beginPath();
    ctx.moveTo(0, (h * 0.68 + Math.cos(t * 0.75) * 18) % h);
    ctx.lineTo(w, (h * 0.68 + Math.cos(t * 0.75) * 18 + 1) % h);
    ctx.stroke();

    ctx.save();
    ctx.translate(w * 0.5, h * 0.48);
    ctx.rotate(t * 0.035);
    ctx.strokeStyle = "rgba(88, 166, 255, 0.06)";
    ctx.lineWidth = 0.5;
    for (i = 1; i <= 6; i++) {
      ctx.beginPath();
      ctx.arc(0, 0, 80 + i * 55 + Math.sin(t + i) * 6, 0, Math.PI * 2);
      ctx.stroke();
    }
    ctx.restore();

    for (i = 0; i < particles.length; i++) {
      p = particles[i];
      p.x += p.vx;
      p.y += p.vy;
      if (p.x < 0) p.x = w;
      if (p.x > w) p.x = 0;
      if (p.y < 0) p.y = h;
      if (p.y > h) p.y = 0;
      var tw = 0.45 + 0.55 * Math.sin(t * 1.8 + p.ph);
      var al = p.a * (0.55 + 0.45 * tw);
      ctx.fillStyle = "rgba(186, 198, 220, " + al + ")";
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
      ctx.fill();
      if (tw > 0.92) {
        ctx.fillStyle = "rgba(147, 197, 253, " + (al * 0.35) + ")";
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.r * 2.2, 0, Math.PI * 2);
        ctx.fill();
      }
    }

    win.requestAnimationFrame(loop);
  }

  if (reduced) drawStatic();
  else loop();
})();
</script>
"""
    components.html(snippet, height=0, scrolling=False)


def _render_hero():
    st.markdown(
        """
        <div class="dc-hero">
            <div class="dc-hero-scan" aria-hidden="true"></div>
            <div class="dc-hero-kicker">Monitor de control</div>
            <div class="dc-hero-title" role="heading" aria-level="1">Dashboard Control</div>
            <p class="dc-hero-sub">Estado de actualización de tableros Power BI · vista ejecutiva · datos del worker</p>
            <div class="dc-hero-accent"></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_metric_cards(
    total: int,
    n_ok: int,
    n_adv: int,
    n_dem: int,
    n_err: int,
):
    st.markdown(
        f"""
        <div class="dc-metrics-row">
            <div class="dc-metric-card dc-metric-card--total" style="animation-delay:0.05s">
                <span class="dc-metric-label">Total de tableros</span>
                <span class="dc-metric-value">{total}</span>
            </div>
            <div class="dc-metric-card dc-metric-card--ok" style="animation-delay:0.12s">
                <span class="dc-metric-label">En estado OK</span>
                <span class="dc-metric-value">{n_ok}</span>
            </div>
            <div class="dc-metric-card dc-metric-card--warn" style="animation-delay:0.19s">
                <span class="dc-metric-label">Con advertencia</span>
                <span class="dc-metric-value">{n_adv}</span>
            </div>
            <div class="dc-metric-card dc-metric-card--late" style="animation-delay:0.26s">
                <span class="dc-metric-label">Demorados</span>
                <span class="dc-metric-value">{n_dem}</span>
            </div>
            <div class="dc-metric-card dc-metric-card--err" style="animation-delay:0.33s">
                <span class="dc-metric-label">Con error</span>
                <span class="dc-metric-value">{n_err}</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _html_reactor_embebido(
    mod: str,
    title_e: str,
    flavor_e: str,
    ratio_e: str,
    core_txt: str,
    pct: int,
) -> str:
    # Sin sangría tipo bloque de código: Streamlit/markdown puede mostrar cierres como texto plano.
    core_safe = html.escape(str(core_txt))
    svg_nucleo = _svg_nucleo_reactor(mod)
    return (
        f'<div class="dc-reactor dc-reactor--embedded dc-reactor--{mod}" role="status" aria-live="polite">'
        f'<div class="dc-reactor__leak" aria-hidden="true"></div>'
        f'<div class="dc-reactor__glow-field" aria-hidden="true"></div>'
        f'<div class="dc-reactor__scan" aria-hidden="true"></div>'
        f'<div class="dc-reactor__sweep" aria-hidden="true"></div>'
        f'<div class="dc-reactor__vignette" aria-hidden="true"></div>'
        f'<div class="dc-reactor__embedded-stack"><div class="dc-reactor__viz">'
        f'{svg_nucleo}'
        f'<div class="dc-reactor__core-overlay"><span class="dc-reactor__core-label">{core_safe}</span></div>'
        f'</div>'
        f'<div class="dc-reactor__status"><div class="dc-reactor__title" role="heading" aria-level="3">{title_e}</div>'
        f'<div class="dc-reactor__meter"><div class="dc-reactor__meter-fill" style="width: {pct}%;"></div></div>'
        f'<div class="dc-reactor__ratio-line">{ratio_e}</div>'
        f'<p class="dc-reactor__flavor">{flavor_e}</p></div></div></div>'
    )


def _render_bloque_criticos_unificado(df: pd.DataFrame | None, n_total: int, n_con_problema: int) -> None:
    mod, r_title, flavor, n_ok, n_tot_r = _evaluar_reactor_criticos(df)
    pct = int(round(100 * n_ok / n_tot_r)) if n_tot_r > 0 else 0
    if n_tot_r > 0:
        ratio_line = f"{n_ok} / {n_tot_r} críticos en OK (núcleo)"
    elif mod == "idle":
        ratio_line = "Sin tableros en el núcleo crítico"
    else:
        ratio_line = "Sin datos de núcleo para el ratio"
    core_txt = f"{n_ok}/{n_tot_r}" if n_tot_r > 0 else "—"
    title_e = html.escape(r_title)
    flavor_e = html.escape(flavor)
    ratio_e = html.escape(ratio_line)

    if n_total == 0:
        wrap = "dc-criticos-unificado dc-criticos-unificado--empty"
        kicker = "Configuración"
        b_title = "Críticos"
        meta = (
            "No hay tableros marcados como críticos. Cuando los configures, la tabla aparecerá debajo y el reactor "
            "reflejará la salud del núcleo."
        )
        badge = "0 en configuración"
    elif n_con_problema > 0:
        wrap = "dc-criticos-unificado dc-criticos-unificado--alert"
        kicker = "Atención prioritaria"
        b_title = "Críticos"
        meta = "Todos los tableros críticos. Arriba en la tabla los que tienen advertencia, demora o error."
        badge = f"{n_con_problema} con alerta · {n_total} críticos"
    else:
        wrap = "dc-criticos-unificado dc-criticos-unificado--clear"
        kicker = "Estado operativo"
        b_title = "Críticos"
        meta = "Todos los tableros críticos en orden. Ninguno requiere atención en esta consulta."
        badge = f"{n_total} críticos · todos OK"

    reactor_html = _html_reactor_embebido(mod, title_e, flavor_e, ratio_e, core_txt, pct)
    kicker_e = html.escape(kicker)
    b_title_e = html.escape(b_title)
    meta_e = html.escape(meta)
    badge_e = html.escape(badge)
    bloque = (
        f'<div class="{html.escape(wrap)}"><div class="dc-criticos-unificado__rail"></div>'
        f'<div class="dc-criticos-unificado__body"><div class="dc-criticos-unificado__left">'
        f'<div class="dc-banner__kicker">{kicker_e}</div>'
        f'<div class="dc-banner__title" role="heading" aria-level="2">{b_title_e}</div>'
        f'<p class="dc-banner__meta">{meta_e}</p><span class="dc-banner__badge">{badge_e}</span></div>'
        f'<div class="dc-criticos-unificado__reactor-host">{reactor_html}</div></div></div>'
    )
    st.markdown(bloque, unsafe_allow_html=True)


st.set_page_config(
    page_title="Dashboard Control",
    layout="wide",
    page_icon=FAVICON_ICO if os.path.isfile(FAVICON_ICO) else "📊",
)
_injectar_estilos()
_render_live_background_js()
_render_hero()
st_autorefresh(interval=3 * 60 * 1000, key="dashboard_refresh")


def _critico_a_etiqueta(val) -> str:
    try:
        return "Sí" if int(float(val)) == 1 else "No"
    except (TypeError, ValueError):
        return "No"


def _fmt_fecha_hora(ts) -> str:
    if pd.isna(ts):
        return ""
    return pd.Timestamp(ts).strftime("%d/%m/%Y %H:%M:%S")


def _fmt_retraso_min(val) -> str:
    if pd.isna(val):
        return ""
    return f"{round(float(val), 2):.2f}"


def _aplicar_filtros(df: pd.DataFrame, modo: str) -> pd.DataFrame:
    if df.empty:
        return df
    if modo == "Solo críticos":
        c = pd.to_numeric(df["critico"], errors="coerce").fillna(0).astype(int)
        return df.loc[c == 1].copy()
    if modo == "Solo con problema":
        return df.loc[df["estado"].isin(ESTADOS_PROBLEMA)].copy()
    return df.copy()


def _preparar_tabla_vista(df: pd.DataFrame, omitir_critico: bool = False) -> pd.DataFrame:
    if df.empty:
        return df
    out = pd.DataFrame()
    out["tablero"] = df["tablero"]
    if not omitir_critico:
        out["crítico"] = df["critico"].map(_critico_a_etiqueta)
    out["estado"] = df["estado"]
    out["última actualización"] = df["ultima_actualizacion"].map(_fmt_fecha_hora)
    out["hora consulta"] = df["hora_consulta"].map(_fmt_fecha_hora)
    out["retraso (min)"] = df["retraso_min"].map(_fmt_retraso_min)
    ed = df["error_detalle"].fillna("").astype(str).str.strip()
    if not ed.eq("").all():
        out["error"] = ed
    return out


def _estilos_columna_estado(_series_estado: pd.Series, df_clave_estado: pd.DataFrame):
    return [
        (
            f"background-color: {PALETA_ESTADO.get(df_clave_estado.loc[i, 'estado'], ('rgba(148,163,184,0.12)', '#e2e8f0'))[0]}; "
            f"color: {PALETA_ESTADO.get(df_clave_estado.loc[i, 'estado'], ('rgba(148,163,184,0.12)', '#e2e8f0'))[1]}; "
            "font-weight: 600; padding: 2px 6px; border-radius: 3px;"
        )
        for i in _series_estado.index
    ]


def _mostrar_tabla_estilizada(
    df_para_clave: pd.DataFrame,
    df_vista: pd.DataFrame,
    col_estado: str = "estado",
    altura_px: int | None = ALTURA_TABLA_PX,
):
    if df_vista.empty:
        return
    kwargs = {"use_container_width": True, "hide_index": True}
    if altura_px is not None:
        kwargs["height"] = altura_px
    try:
        if col_estado in df_vista.columns:
            styled = df_vista.style.apply(
                lambda s: _estilos_columna_estado(s, df_para_clave),
                subset=[col_estado],
                axis=0,
            )
            st.dataframe(styled, **kwargs)
        else:
            st.dataframe(df_vista, **kwargs)
    except Exception:
        st.dataframe(df_vista, **kwargs)


def _df_criticos_con_problema(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    c = pd.to_numeric(df["critico"], errors="coerce").fillna(0).astype(int)
    mask = (c == 1) & df["estado"].isin(ESTADOS_PROBLEMA)
    return df.loc[mask].copy()


def _df_todos_criticos(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    c = pd.to_numeric(df["critico"], errors="coerce").fillna(0).astype(int)
    return df.loc[c == 1].copy()


def _ordenar_criticos_problema_arriba(df: pd.DataFrame) -> pd.DataFrame:
    """Críticos con problema primero (Error, Demorado, Advertencia), luego OK."""
    if df.empty:
        return df
    out = df.copy()
    out["_prio_grupo"] = (~out["estado"].isin(ESTADOS_PROBLEMA)).astype(int)
    out["_prio_estado"] = out["estado"].map(ORDEN_ESTADO)
    out = out.sort_values(
        by=["_prio_grupo", "_prio_estado", "retraso_min"],
        ascending=[True, True, False],
        na_position="last",
    )
    return out.drop(columns=["_prio_grupo", "_prio_estado"]).reset_index(drop=True)


def _render_seccion_cambios_recientes(lineas_cambios: list[str], lineas_fallos_ntfy: list[str]):
    """Bloque único HTML para la sección de cambios recientes."""
    parts: list[str] = [
        '<div class="dc-cambios-card">',
        '<div class="dc-cambios-card-title">Cambios desde la última corrida del monitor</div>',
    ]
    if not lineas_cambios and not lineas_fallos_ntfy:
        parts.append(
            '<span class="dc-cambios-card-empty">Sin cambios de estado en la última corrida del worker '
            "(o aún no hubo una segunda corrida).</span>"
        )
        parts.append("</div>")
        st.markdown("".join(parts), unsafe_allow_html=True)
        return
    if lineas_cambios:
        parts.append(
            '<p class="dc-cambios-section-label"><strong>Transiciones detectadas en la última corrida</strong></p>'
        )
        parts.append('<ul class="dc-cambios-list">')
        for linea in lineas_cambios:
            parts.append(f"<li>{html.escape(str(linea))}</li>")
        parts.append("</ul>")
        if not NTFY_ENABLED:
            parts.append(
                "<p class=\"dc-cambios-caption\">Notificaciones push desactivadas "
                "(`NTFY_ENABLED=1` en el entorno del <strong>worker</strong>).</p>"
            )
        elif not mc.leer_push_ntfy_usuario():
            parts.append(
                "<p class=\"dc-cambios-caption\">Notificaciones <strong>ntfy pausadas</strong> desde el panel lateral.</p>"
            )
        if EXPO_PUSH_ENABLED and not mc.leer_expo_push_global():
            parts.append(
                "<p class=\"dc-cambios-caption\">Expo Push (móvil) <strong>desactivado</strong> desde el panel lateral.</p>"
            )
    if lineas_fallos_ntfy:
        parts.append('<div class="dc-cambios-warn-box" role="alert">')
        parts.append("<strong>Incidencias (ntfy o snapshot)</strong>")
        parts.append('<ul class="dc-cambios-list">')
        for x in lineas_fallos_ntfy:
            parts.append(f"<li>{html.escape(str(x))}</li>")
        parts.append("</ul></div>")
    parts.append("</div>")
    st.markdown("".join(parts), unsafe_allow_html=True)


def _evaluar_reactor_criticos(df: pd.DataFrame | None) -> tuple[str, str, str, int, int]:
    """
    Salud global solo sobre tableros críticos.
    Umbrales equivalentes a 8/8 usando enteros: n_ok*8 frente a 4*n y 6*n.
    Retorna (mod_css, título, flavor, n_ok_críticos, n_total_críticos).
    """
    if df is None or "estado" not in df.columns or "critico" not in df.columns:
        return (
            "offline",
            "Núcleo: Sin enlace",
            "Sin datos del monitor. Ejecutá el worker o «Actualizar ahora».",
            0,
            0,
        )
    if df.empty:
        return (
            "offline",
            "Núcleo: Stand-by",
            "Snapshot sin filas. Revisá configuración o la última corrida del worker.",
            0,
            0,
        )
    c = pd.to_numeric(df["critico"], errors="coerce").fillna(0).astype(int)
    crit = df.loc[c == 1]
    n_total = int(len(crit))
    if n_total == 0:
        return (
            "idle",
            "Núcleo: Inactivo",
            "Sin tableros críticos en configuración. El indicador no aplica.",
            0,
            0,
        )
    n_ok = int((crit["estado"] == "OK").sum())
    x = n_ok * 8
    if n_ok >= n_total:
        mod = "estable"
        title = "Núcleo: Estable"
    elif x >= 6 * n_total and n_ok < n_total:
        mod = "inestable"
        title = "Núcleo: Inestable"
    elif x >= 4 * n_total and x < 6 * n_total:
        mod = "critico"
        title = "Núcleo: Estado crítico"
    else:
        mod = "meltdown"
        title = "Núcleo: Meltdown"

    flavors = {
        "estable": "Contención total.",
        "inestable": "Oscilación detectada.",
        "critico": "Anillo fuera de control.",
        "meltdown": "Contención perdida.",
    }
    return mod, title, flavors[mod], n_ok, n_total


corrida_meta: dict = {}
try:
    df, lineas_cambios, lineas_ntfy_err, _meta_leido, err_lectura = mc.cargar_datos_para_frontend()
    corrida_meta = _meta_leido if isinstance(_meta_leido, dict) else {}

    with st.sidebar:
        st.markdown("#### Notificaciones push")
        push_usuario_on = mc.leer_push_ntfy_usuario()
        if not NTFY_ENABLED:
            st.caption("El worker tiene `NTFY_ENABLED=0`; no se envían pushes ntfy.")
        else:
            st.caption(f"**ntfy:** {'activas' if push_usuario_on else 'pausadas'}")
            if push_usuario_on:
                if st.button("Pausar ntfy", key="dc_ntfy_apagar"):
                    mc.escribir_push_ntfy_usuario(False)
                    st.rerun()
            else:
                if st.button("Activar ntfy", key="dc_ntfy_encender"):
                    mc.escribir_push_ntfy_usuario(True)
                    st.rerun()

        st.markdown("##### Expo Push (móvil)")
        expo_glob_on = mc.leer_expo_push_global()
        if not EXPO_PUSH_ENABLED:
            st.caption("`EXPO_PUSH_ENABLED=0` en el worker: no se envían pushes Expo.")
        else:
            st.caption(f"**Expo Push:** {'activo' if expo_glob_on else 'desactivado'} (global)")
            if expo_glob_on:
                if st.button("Desactivar Expo Push", key="dc_expo_push_apagar"):
                    mc.escribir_expo_push_global(False)
                    st.rerun()
            else:
                if st.button("Activar Expo Push", key="dc_expo_push_encender"):
                    mc.escribir_expo_push_global(True)
                    st.rerun()

    st.markdown('<div class="dc-section-gap"></div>', unsafe_allow_html=True)
    col_lbl, col_centro, col_btn = st.columns([1.35, 4.25, 1.2])
    with col_lbl:
        st.markdown(
            '<span class="dc-control-bar__label">Resumen de la consulta</span>',
            unsafe_allow_html=True,
        )
    with col_centro:
        if df is None:
            st.markdown(
                '<span class="dc-control-bar__empty">Sin snapshot local. «Actualizar ahora» ejecuta el monitor (Power BI).</span>',
                unsafe_allow_html=True,
            )
        elif not df.empty:
            ts_fmt = _fmt_fecha_hora(df["hora_consulta"].iloc[0])
            st.markdown(
                f'<span class="dc-control-bar__time">Última consulta (worker): <strong>{ts_fmt}</strong></span>',
                unsafe_allow_html=True,
            )
            if corrida_meta.get("duracion_s") is not None and corrida_meta.get("exito"):
                st.caption(
                    f"Worker · duración última corrida: {corrida_meta.get('duracion_s')} s · "
                    f"{corrida_meta.get('n_tableros', '—')} tableros"
                )
        else:
            st.markdown(
                '<span class="dc-control-bar__empty">Sin tableros activos en configuración (último snapshot).</span>',
                unsafe_allow_html=True,
            )
    with col_btn:
        if st.button("Actualizar ahora", key="refresh_manual"):
            with st.spinner("Ejecutando monitor (consulta Power BI)…"):
                ok_run, msg_run = _ejecutar_corrida_monitor_manual()
            if ok_run:
                st.rerun()
            else:
                st.error("La corrida manual del monitor falló.")
                st.code(msg_run)

    if err_lectura:
        st.warning(err_lectura)
        st.stop()

    if corrida_meta.get("exito") is False and corrida_meta.get("error"):
        st.warning(
            f"La última corrida del monitor falló: {corrida_meta.get('error')} "
            "(mostrando el último estado guardado en disco)."
        )

    if df.empty or "estado" not in df.columns:
        n_ok = n_adv = n_dem = n_err = 0
    else:
        n_ok = int((df["estado"] == "OK").sum())
        n_adv = int((df["estado"] == "Advertencia").sum())
        n_dem = int((df["estado"] == "Demorado").sum())
        n_err = int((df["estado"] == "Error").sum())
    df_todos_crit = _df_todos_criticos(df)
    n_crit = len(df_todos_crit)
    n_crit_problema = len(_df_criticos_con_problema(df))
    layout_mobile = _layout_mobile_streamlit()

    def _render_cola_tablas_monitor() -> None:
        if n_crit > 0:
            df_crit_ordenado = _ordenar_criticos_problema_arriba(df_todos_crit)
            _mostrar_tabla_estilizada(
                df_crit_ordenado.copy(),
                _preparar_tabla_vista(df_crit_ordenado, omitir_critico=True),
                col_estado="estado",
                altura_px=None,
            )
        st.markdown(
            '<hr class="dc-divider" />',
            unsafe_allow_html=True,
        )
        st.markdown(
            '<p class="dc-section-title">Tabla completa</p>',
            unsafe_allow_html=True,
        )
        modo_vista = st.radio(
            "Filtro",
            options=["Ver todos", "Solo críticos", "Solo con problema"],
            horizontal=True,
            key="filtro_vista_monitor",
            label_visibility="collapsed",
        )
        df_filtrado = _aplicar_filtros(df, modo_vista)
        if df_filtrado.empty:
            st.markdown(
                '<div class="dc-info-callout" role="status">'
                "No hay filas que coincidan con el filtro."
                "</div>",
                unsafe_allow_html=True,
            )
        else:
            _mostrar_tabla_estilizada(
                df_filtrado.copy(), _preparar_tabla_vista(df_filtrado)
            )

    if layout_mobile:
        _render_bloque_criticos_unificado(df, n_crit, n_crit_problema)
        _render_metric_cards(len(df), n_ok, n_adv, n_dem, n_err)
        _render_seccion_cambios_recientes(lineas_cambios, lineas_ntfy_err)
        st.markdown(
            '<hr class="dc-divider" />',
            unsafe_allow_html=True,
        )
        _render_cola_tablas_monitor()
    else:
        _render_metric_cards(len(df), n_ok, n_adv, n_dem, n_err)
        _render_seccion_cambios_recientes(lineas_cambios, lineas_ntfy_err)
        st.markdown(
            '<hr class="dc-divider" />',
            unsafe_allow_html=True,
        )
        _render_bloque_criticos_unificado(df, n_crit, n_crit_problema)
        _render_cola_tablas_monitor()

except Exception as e:
    st.error(f"Error en la vista: {e}")
