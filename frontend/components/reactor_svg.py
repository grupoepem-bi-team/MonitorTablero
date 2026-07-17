"""
reactor_svg.py - Generadores SVG del reactor visual de salud critica.

Produce un SVG de 92x92 con multiples capas animadas (anillos, conductos,
graduaciones, filamentos, nucleo) cuyo color y animacion dependen del
estado del reactor: offline, idle, estable, inestable, critico, meltdown.
"""
from __future__ import annotations

import html
import math

# ---------------------------------------------------------------------------
# Paletas de color por estado
# ---------------------------------------------------------------------------

_PALETA = {
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

# Radios de las capas del SVG
R_OUTER_BLOOM = 49.5
R_HEX_OUT = 46.5
R_HEX_IN = 41.2
R_RING1 = 47.8
R_RING2 = 44.6
R_RING3 = 39.8
R_CONDUIT = 36.8
R_SLOTS = 42.5
R_BRACKET = 41.8
R_SEAL = 30.8
R_CORE = 27.2

# Clase CSS del core segun estado
_CORE_CLASS = {
    "estable": "dc-r-svg-core dc-r-svg-core--drift",
    "inestable": "dc-r-svg-core dc-r-svg-core--pulse",
    "critico": "dc-r-svg-core dc-r-svg-core--shake",
    "meltdown": "dc-r-svg-core dc-r-svg-core--melt",
}


# ---------------------------------------------------------------------------
# Generadores de formas SVG
# ---------------------------------------------------------------------------


def _hex_path(cx: float, cy: float, r: float) -> str:
    """Genera el path de un hexagono flat-top."""
    pts = []
    for k in range(6):
        ang = math.radians(-90 + k * 60)
        pts.append(f"{cx + r * math.cos(ang):.3f},{cy + r * math.sin(ang):.3f}")
    return "M " + " L ".join(pts) + " Z"


def _hex_rivets(cx: float, cy: float, r: float, fill: str, r_dot: float = 1.1) -> str:
    """Genera los remaches en los vertices del hexagono."""
    parts = []
    for k in range(6):
        ang = math.radians(-90 + k * 60)
        vx = cx + r * math.cos(ang)
        vy = cy + r * math.sin(ang)
        parts.append(
            f'<circle cx="{vx:.3f}" cy="{vy:.3f}" r="{r_dot}" fill="{fill}"/>'
            f'<circle cx="{vx - 0.28:.3f}" cy="{vy - 0.28:.3f}" r="{r_dot * 0.38:.3f}" fill="rgba(255,255,255,0.22)"/>'
        )
    return "".join(parts)


def _slot_marks(cx: float, cy: float, r: float, n: int = 16, half_len: float = 1.6) -> str:
    """Genera muescas tangentes (graduaciones industriales)."""
    parts = []
    for k in range(n):
        ang = -math.pi / 2 + math.tau * k / n
        px = cx + r * math.cos(ang)
        py = cy + r * math.sin(ang)
        tx = -math.sin(ang)
        ty = math.cos(ang)
        hl = half_len if k % 4 == 0 else half_len * 0.55
        x1, y1 = px - hl * tx, py - hl * ty
        x2, y2 = px + hl * tx, py + hl * ty
        w = "0.75" if k % 4 == 0 else "0.4"
        parts.append(
            f'<line x1="{x1:.3f}" y1="{y1:.3f}" x2="{x2:.3f}" y2="{y2:.3f}" '
            f'stroke-linecap="round" stroke-width="{w}"/>'
        )
    return "".join(parts)


def _conduit_arcs(cx: float, cy: float, r: float, n: int = 10, span_deg: float = 22) -> str:
    """Genera arcos de conducto de plasma."""
    parts = []
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


def _containment_brackets(cx: float, cy: float, r: float) -> str:
    """Genera 4 soportes de contencion en los ejes cardinales."""
    parts = []
    for ang_deg in [0, 90, 180, 270]:
        ang = math.radians(ang_deg - 90)
        bx = cx + r * math.cos(ang)
        by = cy + r * math.sin(ang)
        inner_r = r - 4.5
        ix = cx + inner_r * math.cos(ang)
        iy = cy + inner_r * math.sin(ang)
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


def _energy_filaments(cx: float, cy: float, core_r: float, n: int = 6) -> str:
    """Genera filamentos de energia que emergen del nucleo."""
    parts = []
    for k in range(n):
        ang = math.tau * k / n + math.pi / 12
        sx = cx + core_r * math.cos(ang)
        sy = cy + core_r * math.sin(ang)
        seal_r = core_r + 4.5
        ex = cx + seal_r * math.cos(ang + 0.18)
        ey = cy + seal_r * math.sin(ang + 0.18)
        mid_r = core_r + 2.2
        mx = cx + mid_r * math.cos(ang + 0.09)
        my = cy + mid_r * math.sin(ang + 0.09)
        parts.append(
            f'<path d="M {sx:.3f},{sy:.3f} Q {mx:.3f},{my:.3f} {ex:.3f},{ey:.3f}" '
            f'fill="none" stroke="url(#dcFilamentGrad)" stroke-width="0.55" stroke-linecap="round" opacity="0.62"/>'
        )
    return "".join(parts)


# ---------------------------------------------------------------------------
# Generador del SVG completo
# ---------------------------------------------------------------------------


def generar_svg_reactor(mod: str) -> str:
    """
    Genera el SVG del reactor para un estado dado.

    Args:
        mod: Estado del reactor ("offline", "idle", "estable",
             "inestable", "critico", "meltdown").

    Returns:
        str: Markup SVG de 92x92 con todas las capas animadas.
    """
    p = _PALETA.get(mod, _PALETA["offline"])
    cx, cy = 50.0, 50.0

    hex_o = _hex_path(cx, cy, R_HEX_OUT)
    hex_i = _hex_path(cx, cy, R_HEX_IN)
    hex_bg = _hex_path(cx, cy, R_HEX_IN - 0.4)

    rivets = _hex_rivets(cx, cy, R_HEX_OUT, p["rivet"])
    slots = _slot_marks(cx, cy, R_SLOTS, n=24)
    conduits = _conduit_arcs(cx, cy, R_CONDUIT, n=10, span_deg=20)
    brackets = _containment_brackets(cx, cy, R_BRACKET)
    filaments = _energy_filaments(cx, cy, R_CORE, n=8)

    rings = (
        f'<circle cx="{cx}" cy="{cy}" r="{R_RING1}" fill="none" stroke="{p["s1"]}" stroke-width="0.5" stroke-dasharray="2.8 7.5" opacity="0.8"/>'
        f'<circle cx="{cx}" cy="{cy}" r="{R_RING2}" fill="none" stroke="{p["s2"]}" stroke-width="0.38" stroke-dasharray="1.2 5" opacity="0.65"/>'
        f'<circle cx="{cx}" cy="{cy}" r="{R_RING3}" fill="none" stroke="{p["s3"]}" stroke-width="0.6" stroke-dasharray="7 12" opacity="0.5"/>'
    )

    tick_ring = f'<circle cx="{cx}" cy="{cy}" r="34.5" fill="none" stroke="{p["seal"]}" stroke-width="0.28" stroke-dasharray="0.6 3.8" opacity="0.55"/>'

    core_cls = _CORE_CLASS.get(mod, "dc-r-svg-core")

    # Glints especulares
    g_r = R_CORE
    glint_main = (
        f'<path fill="none" stroke="rgba(255,255,255,0.18)" stroke-width="0.5" stroke-linecap="round" '
        f'd="M {cx - g_r * 0.62:.3f} {cy - g_r * 0.75:.3f} A {g_r * 0.88:.3f} {g_r * 0.88:.3f} 0 0 1 '
        f'{cx + g_r * 0.62:.3f} {cy - g_r * 0.75:.3f}"/>'
    )
    glint_soft = (
        f'<path fill="none" stroke="rgba(255,255,255,0.07)" stroke-width="0.9" stroke-linecap="round" '
        f'd="M {cx - g_r * 0.38:.3f} {cy - g_r * 0.62:.3f} A {g_r * 0.6:.3f} {g_r * 0.6:.3f} 0 0 1 '
        f'{cx + g_r * 0.38:.3f} {cy - g_r * 0.62:.3f}"/>'
    )
    glint_fresnel = (
        f'<path fill="none" stroke="rgba(255,255,255,0.04)" stroke-width="1.2" stroke-linecap="round" '
        f'd="M {cx - g_r * 0.45:.3f} {cy + g_r * 0.65:.3f} A {g_r * 0.72:.3f} {g_r * 0.72:.3f} 0 0 0 '
        f'{cx + g_r * 0.45:.3f} {cy + g_r * 0.65:.3f}"/>'
    )

    defs = (
        '<filter id="dcBloom" x="-80%" y="-80%" width="260%" height="260%">'
        '<feGaussianBlur in="SourceGraphic" stdDeviation="3.5" result="bl"/>'
        '<feMerge><feMergeNode in="bl"/></feMerge>'
        "</filter>"
        '<filter id="dcCoreGlow" x="-60%" y="-60%" width="220%" height="220%">'
        '<feGaussianBlur in="SourceGraphic" stdDeviation="1.2" result="b"/>'
        '<feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>'
        "</filter>"
        '<filter id="dcFilGlow" x="-40%" y="-40%" width="180%" height="180%">'
        '<feGaussianBlur in="SourceGraphic" stdDeviation="0.7" result="b"/>'
        '<feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>'
        "</filter>"
        f'<radialGradient id="dcCore" cx="44%" cy="40%" r="64%" fx="42%" fy="38%">'
        f'<stop offset="0%" stop-color="{p["c1"]}"/>'
        f'<stop offset="22%" stop-color="{p["c1"]}"/>'
        f'<stop offset="48%" stop-color="{p["c2"]}"/>'
        f'<stop offset="70%" stop-color="{p["c1"]}"/>'
        f'<stop offset="88%" stop-color="{p["c0"]}"/>'
        f'<stop offset="100%" stop-color="{p["c3"]}"/>'
        "</radialGradient>"
        f'<radialGradient id="dcOuter" cx="50%" cy="48%" r="56%">'
        f'<stop offset="0%" stop-color="{p["o_a"]}"/>'
        f'<stop offset="50%" stop-color="{p["o_b"]}"/>'
        f'<stop offset="100%" stop-color="rgba(0,0,0,0)"/>'
        "</radialGradient>"
        f'<linearGradient id="dcReactPlasma" x1="0%" y1="0%" x2="100%" y2="0%">'
        f'<stop offset="0%" stop-color="{p["pl_a"]}"/>'
        f'<stop offset="100%" stop-color="{p["pl_b"]}"/>'
        "</linearGradient>"
        f'<linearGradient id="dcBracketGrad" x1="0%" y1="0%" x2="0%" y2="100%">'
        f'<stop offset="0%" stop-color="{p["bracket"]}"/>'
        f'<stop offset="100%" stop-color="rgba(0,0,0,0)"/>'
        "</linearGradient>"
        f'<linearGradient id="dcFilamentGrad" x1="0%" y1="0%" x2="100%" y2="0%">'
        f'<stop offset="0%" stop-color="{p["fil_a"]}"/>'
        f'<stop offset="100%" stop-color="{p["fil_b"]}"/>'
        "</linearGradient>"
        f'<linearGradient id="dcSealGrad" x1="0%" y1="0%" x2="100%" y2="100%">'
        f'<stop offset="0%" stop-color="{p["seal"]}"/>'
        f'<stop offset="50%" stop-color="rgba(255,255,255,0.08)"/>'
        f'<stop offset="100%" stop-color="{p["seal"]}"/>'
        "</linearGradient>"
        '<linearGradient id="dcHexBg" x1="30%" y1="0%" x2="70%" y2="100%">'
        '<stop offset="0%" stop-color="rgba(10,14,20,0.98)"/>'
        '<stop offset="100%" stop-color="rgba(6,9,14,0.99)"/>'
        "</linearGradient>"
    )

    return (
        f'<svg class="dc-reactor-svg" viewBox="0 0 100 100" width="92" height="92" '
        f'xmlns="http://www.w3.org/2000/svg" focusable="false" aria-hidden="true">'
        f"<defs>{defs}</defs>"
        # 1. Bloom ambiental
        f'<circle class="dc-r-svg-outer" cx="{cx}" cy="{cy}" r="{R_OUTER_BLOOM}" '
        f'fill="url(#dcOuter)" opacity="0.65" filter="url(#dcBloom)"/>'
        # 2. Placa hex de fondo
        f'<path d="{hex_bg}" fill="url(#dcHexBg)" opacity="0.96"/>'
        # 3. Anillos
        f'<g class="dc-r-svg-rot dc-r-svg-rot--rings">{rings}</g>'
        # 4. Conductos de plasma
        f'<g class="dc-r-svg-rot dc-r-svg-rot--plasma">{conduits}</g>'
        # 5. Graduaciones
        f'<g class="dc-r-svg-rot dc-r-svg-rot--slots" stroke="{p["slot"]}">{slots}</g>'
        # 6. Soportes
        f'<g class="dc-r-svg-housing">{brackets}</g>'
        # 7. Carcasa hex
        f'<g class="dc-r-svg-housing">'
        f'<path fill="none" stroke="{p["hin"]}" stroke-width="1.1" d="{hex_i}"/>'
        f'<path fill="none" stroke="{p["hout"]}" stroke-width="1.3" d="{hex_o}"/>'
        f"{rivets}</g>"
        # 8. Anillo de graduacion fino
        f"{tick_ring}"
        # 9. Sello de contencion
        f'<circle cx="{cx}" cy="{cy}" r="{R_SEAL + 2.2}" fill="none" '
        f'stroke="{p["seal"]}" stroke-width="0.32" opacity="0.45"/>'
        f'<circle cx="{cx}" cy="{cy}" r="{R_SEAL}" fill="none" '
        f'stroke="url(#dcSealGrad)" stroke-width="1.2" opacity="0.72"/>'
        f'<circle cx="{cx}" cy="{cy}" r="{R_SEAL - 1.8}" fill="none" '
        f'stroke="rgba(0,0,0,0.5)" stroke-width="0.8" opacity="0.9"/>'
        # 10. Filamentos
        f'<g class="dc-r-svg-filaments" filter="url(#dcFilGlow)">{filaments}</g>'
        # 11. Nucleo
        f'<g class="{core_cls}">'
        f'<circle cx="{cx}" cy="{cy}" r="{R_CORE}" fill="url(#dcCore)" filter="url(#dcCoreGlow)"/>'
        f'<circle cx="{cx}" cy="{cy}" r="{R_CORE * 0.62:.3f}" fill="{p["c2"]}" opacity="0.22"/>'
        f'<circle cx="{cx}" cy="{cy}" r="{R_CORE}" fill="none" '
        f'stroke="rgba(255,255,255,0.12)" stroke-width="0.5"/>'
        f"{glint_main}{glint_soft}{glint_fresnel}</g>"
        f"</svg>"
    )


def generar_html_reactor(
    mod: str, title: str, flavor: str, n_ok: int, n_total: int, pct: int
) -> str:
    """
    Genera el HTML completo del reactor embebido (SVG + status + barra).

    Args:
        mod: Estado del reactor.
        title: Titulo a mostrar (ej: "Nucleo: Estable").
        flavor: Texto descriptivo corto.
        n_ok: Tableros criticos en OK.
        n_total: Total de tableros criticos.
        pct: Porcentaje de criticos en OK (0-100).

    Returns:
        str: HTML del reactor listo para inyectar en el DOM.
    """
    svg = generar_svg_reactor(mod)
    core_txt = f"{n_ok}/{n_total}" if n_total > 0 else "--"
    ratio = f"{n_ok} / {n_total} criticos en OK" if n_total > 0 else "Sin datos"

    return (
        f'<div class="dc-reactor dc-reactor--embedded dc-reactor--{mod}" role="status" aria-live="polite">'
        f'<div class="dc-reactor__leak" aria-hidden="true"></div>'
        f'<div class="dc-reactor__glow-field" aria-hidden="true"></div>'
        f'<div class="dc-reactor__scan" aria-hidden="true"></div>'
        f'<div class="dc-reactor__sweep" aria-hidden="true"></div>'
        f'<div class="dc-reactor__vignette" aria-hidden="true"></div>'
        f'<div class="dc-reactor__embedded-stack"><div class="dc-reactor__viz">'
        f"{svg}"
        f'<div class="dc-reactor__core-overlay"><span class="dc-reactor__core-label">{html.escape(core_txt)}</span></div>'
        f"</div>"
        f'<div class="dc-reactor__status"><div class="dc-reactor__title" role="heading" aria-level="3">{html.escape(title)}</div>'
        f'<div class="dc-reactor__meter"><div class="dc-reactor__meter-fill" style="width: {pct}%;"></div></div>'
        f'<div class="dc-reactor__ratio-line">{html.escape(ratio)}</div>'
        f'<p class="dc-reactor__flavor">{html.escape(flavor)}</p></div></div></div>'
    )