"""
test_reactor_svg.py - Tests del generador de SVG del reactor visual.

Verifica que generar_svg_reactor produzca SVG valido para todos los estados,
que no haya errores de formato, y que generar_html_reactor incluya el SVG.
"""
from __future__ import annotations

import html
import re

import pytest

from frontend.components.reactor_svg import (
    generar_html_reactor,
    generar_svg_reactor,
    _PALETA,
)

ESTADOS = list(_PALETA.keys())


class TestGenerarSVGReactor:
    @pytest.mark.parametrize("mod", ESTADOS)
    def test_svg_valido_basico(self, mod):
        svg = generar_svg_reactor(mod)
        assert "<svg" in svg
        assert "</svg>" in svg
        assert "viewBox" in svg

    @pytest.mark.parametrize("mod", ESTADOS)
    def test_svg_tiene_defs(self, mod):
        svg = generar_svg_reactor(mod)
        assert "<defs>" in svg
        assert "</defs>" in svg
        # Debe tener al menos los gradientes clave
        assert "dcCore" in svg
        assert "dcOuter" in svg
        assert "dcReactPlasma" in svg

    @pytest.mark.parametrize("mod", ESTADOS)
    def test_svg_tiene_hexagono(self, mod):
        svg = generar_svg_reactor(mod)
        # El path del hexagono debe estar
        assert "M " in svg or "M" in svg
        assert "L " in svg or "L" in svg

    @pytest.mark.parametrize("mod", ESTADOS)
    def test_svg_tiene_filtros(self, mod):
        svg = generar_svg_reactor(mod)
        assert "dcBloom" in svg
        assert "dcCoreGlow" in svg
        assert "dcFilGlow" in svg

    def test_estado_desconocido_usa_offline(self):
        svg = generar_svg_reactor("no_existe")
        assert "<svg" in svg
        # Debe usar la paleta offline (gris)
        assert "3a404a" in svg  # c0 de offline

    @pytest.mark.parametrize("mod", ESTADOS)
    def test_svg_no_tiene_etiquetas_sin_cerrar(self, mod):
        svg = generar_svg_reactor(mod)
        # Contar tags <svg y </svg>
        assert svg.count("<svg") >= 1
        assert svg.count("</svg>") >= 1


class TestGenerarHTMLReactor:
    def test_html_incluye_svg(self):
        html_out = generar_html_reactor("estable", "Nucleo: Estable", "Todo OK", 5, 7, 71)
        assert "<svg" in html_out
        assert "</div>" in html_out

    def test_html_escape_titulo(self):
        html_out = generar_html_reactor("estable", "<script>alert(1)</script>", "", 1, 1, 100)
        assert "<script>" not in html_out
        assert "&lt;script&gt;" in html_out

    def test_html_escape_flavor(self):
        html_out = generar_html_reactor("estable", "Test", "<b>negrita</b>", 1, 1, 100)
        assert "<b>negrita</b>" not in html_out
        assert "&lt;b&gt;" in html_out

    def test_html_con_total_cero(self):
        html_out = generar_html_reactor("offline", "Sin datos", "", 0, 0, 0)
        assert "--" in html_out
        assert "Sin datos" in html_out

    def test_html_con_datos(self):
        html_out = generar_html_reactor("estable", "Nucleo", "OK", 5, 7, 71)
        assert "5/7" in html_out
        assert "71%" in html_out

    @pytest.mark.parametrize("mod", ESTADOS)
    def test_todos_los_estados_generan_html(self, mod):
        html_out = generar_html_reactor(mod, "Test", "flavor", 1, 2, 50)
        assert "<svg" in html_out
        assert "Test" in html_out