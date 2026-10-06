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
    """
    El favicon debe existir Y servirse por las dos vias.

    Regla del proyecto (06/10/2026): NINGUNA pagina sin favicon. El icono es la
    marca de EPEM (emblema oficial) en el tema del panel; el .ico va en
    frontend/static/ (Docker solo copia frontend/), el HTML debe pedirlo con
    version para romper la cache que guardo el 404 viejo, y la ruta raiz
    /favicon.ico (que algunos navegadores piden solos) tambien debe responder.
    """

    def test_el_ico_esta_en_static(self):
        ico = os.path.join(_STATIC, "epem-monitor-tableros.ico")
        assert os.path.isfile(ico), (
            "el favicon debe estar en frontend/static/ o Docker no lo incluye"
        )

    def test_el_ico_es_multitamano(self):
        """Un .ico con varios tamanos se ve nitido en todas las barras/atajos."""
        ico = os.path.join(_STATIC, "epem-monitor-tableros.ico")
        datos = open(ico, "rb").read()
        assert datos[:4] == b"\x00\x00\x01\x00", "no es un archivo ICO valido"
        cantidad = int.from_bytes(datos[4:6], "little")
        assert cantidad >= 3, f"el .ico tiene {cantidad} tamano(s); conviene que tenga varios"

    def test_la_ruta_del_html_apunta_a_static(self):
        html = _html()
        assert "/static/epem-monitor-tableros.ico" in html, (
            "el <link> del favicon debe apuntar a /static/, que es lo que se monta"
        )

    def test_el_link_lleva_version(self):
        """Sin ?v=, el navegador conserva el 404 que cacheo cuando no existia."""
        html = _html()
        assert re.search(r"epem-monitor-tableros\.ico\?v=\d+", html), (
            "el <link> del favicon debe llevar ?v=N para forzar la recarga"
        )

    def test_existe_la_ruta_raiz_favicon_ico(self):
        """Algunos navegadores piden /favicon.ico sin mirar el <link>."""
        server = open(os.path.join(_ROOT, "frontend", "server.py"), encoding="utf-8").read()
        assert '@app.get("/favicon.ico")' in server, (
            "falta la ruta /favicon.ico: los navegadores que la piden solos reciben 404"
        )

    def test_no_queda_el_icono_de_stock(self):
        """El icono generico de Power BI (stock) fue reemplazado por la marca EPEM."""
        assert not os.path.isfile(os.path.join(_STATIC, "icons8-power-bi-50.ico")), (
            "quedo el icono de stock: el icono debe ser la marca EPEM"
        )


class TestEscalaDeTiempos:
    """
    La grilla no debe aplastar las tablas (bug de la escala pegada, 06/10/2026).

    Con la grilla fija "1fr 1fr 1fr" y el panel en 1400px, en un monitor de 1920px
    la tercera columna se comprimia a ~440px, la tabla quedaba en ~338px y la
    escala de tiempos salia pegada ("030 min60 min24 h"). Ahora la grilla es
    auto-fit con piso: abre columnas solo cuando ENTRAN.
    """

    def test_grilla_no_es_fija(self):
        css = _css()
        assert "grid-template-columns: 1fr 1fr 1fr" not in css, (
            "la grilla no debe volver a ser de 3 columnas fijas: aplasta la tabla en pantallas anchas"
        )

    def test_grilla_usa_minmax(self):
        css = _css()
        assert "repeat(auto-fit, minmax(" in css, (
            "la grilla debe abrir columnas solo cuando entren (auto-fit + minmax)"
        )

    def test_rotulos_de_la_escala_no_se_parten(self):
        css = _css()
        assert ".timeline-header span { white-space: nowrap; }" in css, (
            "los rotulos de la escala (0 / 30 min / 60 min / 24 h) no deben partirse"
        )


class TestTablaAlineada:
    """
    La cabecera y el cuerpo deben declarar la MISMA cantidad de columnas.

    El 26/08 un `colspan="4"` en el <th> de la timeline (heredado de un diseño
    anterior) declaraba 9 columnas donde el cuerpo tiene 6: la columna "Atraso"
    de la cabecera quedaba ~107 px desalineada de su dato y la escala de la
    timeline se estiraba a 126 px en vez de los 160 px del CSS. Lo corrigio
    `master` (691e01e) pero nunca se fusiono; se rescato el 06/10.
    """

    def test_la_cabecera_no_tiene_colspan(self):
        html = _html()
        assert 'class="col-timeline" colspan' not in html, (
            "el <th> de la timeline no debe llevar colspan: desalinea la cabecera"
        )

    def test_th_y_td_declaran_lo_mismo(self):
        html = _html()
        import re

        # Cantidad de <th> por tabla (sin contar los colspan)
        for tabla in re.findall(r"<table.*?</table>", html, re.S):
            ths = len(re.findall(r"<th\b", tabla))
            # El cuerpo lo llena el JS: la fila tiene 6 <td> (ver renderTabla).
            assert ths == 6, f"la tabla declara {ths} columnas; el cuerpo pinta 6"

    def test_el_ancho_de_la_timeline_esta_definido(self):
        css = _css()
        assert ".data-table th.col-timeline" in css, "falta el ancho de la columna timeline"


class TestJavaScriptRender:
    """
    Ejecuta el app.js REAL contra un DOM minimo (tests/js_smoke.js).

    Sin esto, un error de JavaScript en el render no lo ve ninguna prueba de
    Python: el 06/10/2026 una variable borrada dejo la tabla VACIA en produccion
    y la suite siguio verde. Requiere Node; si no esta, se salta.
    """

    def test_el_render_no_explota(self):
        import shutil
        import subprocess

        node = shutil.which("node") or shutil.which("node.exe")
        if not node:
            pytest.skip("Node no esta instalado: no se puede correr el smoke de JS")

        js_smoke = os.path.join(_ROOT, "tests", "js_smoke.js")
        r = subprocess.run(
            [node, js_smoke],
            cwd=_ROOT,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert r.returncode == 0, (
            "el render de app.js fallo\n"
            f"STDOUT: {r.stdout.strip()}\n"
            f"STDERR: {r.stderr.strip()}"
        )
