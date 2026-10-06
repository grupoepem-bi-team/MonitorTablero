"""
test_frontend_assets.py - Tests de los recursos visuales del panel.

No ejecutan JavaScript: validan el HTML y el CSS servidos, que es donde vivian
los fallos reales del 06/10/2026:

  * El tema (dark mode) no se podia forzar a claro si el sistema estaba oscuro.
  * El tema se aplicaba al final (destello al cargar).
  * El CSS nunca subia de version -> la cache del navegador quedaba pegada.
  * El favicon apuntaba a un archivo que no existia dentro de la imagen Docker.
"""
from __future__ import annotations

import os
import re

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_TEMPLATES = os.path.join(_ROOT, "frontend", "templates")
_STATIC = os.path.join(_ROOT, "frontend", "static")


def _html() -> str:
    with open(os.path.join(_TEMPLATES, "index.html"), encoding="utf-8") as f:
        return f.read()


def _css() -> str:
    with open(os.path.join(_STATIC, "style.css"), encoding="utf-8") as f:
        return f.read()


class TestTemaSinDestello:
    """El tema debe fijarse en el <head>, antes del CSS."""

    def test_script_de_tema_va_antes_del_stylesheet(self):
        html = _html()
        pos_script = html.find("monitor-theme")
        pos_css = html.find("style.css")
        assert pos_script != -1, "no existe el script que fija el tema en el <head>"
        assert pos_css != -1, "no se encontro el <link> del CSS"
        assert pos_script < pos_css, (
            "el script del tema debe ir ANTES del CSS para evitar el destello"
        )

    def test_script_aplica_clase_dark_o_light(self):
        html = _html()
        assert '"dark"' in html and '"light"' in html, (
            "el script debe aplicar la clase dark o light (nunca dejar el html sin clase)"
        )


class TestCacheBusting:
    """Los assets deben subir de version al cambiar, o la cache del navegador manda."""

    def test_css_lleva_version(self):
        m = re.search(r"style\.css\?v=(\d+)", _html())
        assert m, "el CSS debe pedirse con ?v=N para romper la cache"

    def test_js_lleva_version(self):
        m = re.search(r"app\.js\?v=(\d+)", _html())
        assert m, "el JS debe pedirse con ?v=N para romper la cache"

    def test_js_v5_y_css_v3_o_superior(self):
        """Cortes minimos: por debajo de esto el navegador sirve la copia vieja."""
        v_css = int(re.search(r"style\.css\?v=(\d+)", _html()).group(1))
        v_js = int(re.search(r"app\.js\?v=(\d+)", _html()).group(1))
        assert v_css >= 3, f"style.css?v={v_css}: subir a 3 (el dark mode nunca subio de v2)"
        assert v_js >= 5, f"app.js?v={v_js}: subir a 5"


class TestDarkModeCSS:
    """La eleccion del usuario debe ganarle al tema del sistema."""

    def test_media_query_excluye_la_clase_light(self):
        css = _css()
        assert "html:not(.light)" in css, (
            "sin :not(.light), un PC en oscuro queda oscuro aunque el usuario pida claro"
        )

    def test_existe_el_bloque_forzado_por_clase(self):
        css = _css()
        assert "html.dark {" in css, "falta el bloque que fuerza el tema oscuro por clase"

    def test_el_bloque_dark_va_despues_de_la_media_query(self):
        css = _css()
        pos_media = css.find("@media (prefers-color-scheme: dark)")
        pos_dark = css.find("html.dark {")
        assert pos_media != -1 and pos_dark != -1
        assert pos_dark > pos_media, (
            "html.dark debe ir DESPUES de la media query: misma especificidad, gana el ultimo"
        )


class TestSinAvisos:
    """El monitor no avisa por ningun medio (orden de Emmanuel, 06/10/2026)."""

    def test_no_usa_la_api_de_notificaciones_del_navegador(self):
        js = open(os.path.join(_STATIC, "app.js"), encoding="utf-8").read()
        assert "new Notification(" not in js, "quedaron avisos del navegador activos"
        assert "requestPermission" not in js, "quedaron avisos del navegador activos"


class TestFavicon:
    """El favicon debe existir dentro de la imagen (Docker solo copia frontend/)."""

    def test_el_ico_esta_en_static(self):
        ico = os.path.join(_STATIC, "icons8-power-bi-50.ico")
        assert os.path.isfile(ico), (
            "el favicon debe estar en frontend/static/ o Docker no lo incluye"
        )

    def test_la_ruta_del_html_apunta_a_static(self):
        html = _html()
        assert "/static/icons8-power-bi-50.ico" in html, (
            "el <link> del favicon debe apuntar a /static/, que es lo que se monta"
        )
