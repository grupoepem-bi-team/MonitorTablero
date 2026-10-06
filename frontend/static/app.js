/* ==========================================================================
   app.js - Monitor de Tableros EPEM
   Frontend puro vanilla JS. Consume /api/todos del backend FastAPI.
   Render: KPIs + tabla "Requieren atencion" + tabla "Al dia" con timeline.
   ========================================================================== */

(function () {
    "use strict";

    // --- Configuracion ---
    const API = "/api/todos";
    const API_CORRIDA = "/api/corrida";
    const REFRESH_FAST_MS = 30 * 1000;   // 30s cuando hay atrasados
    const REFRESH_SLOW_MS = 5 * 60 * 1000; // 5min cuando todo OK
    const MAX_MINUTOS_TIMELINE = 1440;     // 24h = escala maxima de la barra

    // --- Estado ---
    let estadoData = null;
    let metaData = null;
    let saludData = null;
    let corriendo = false;
    let refreshTimer = null;

    const ESTADOS_LATE = ["Demorado", "Error", "Advertencia"];

    // --- Helpers ---

    /** Escapa HTML para evitar XSS */
    function esc(s) {
        const d = document.createElement("div");
        d.textContent = String(s ?? "");
        return d.innerHTML;
    }

    /** Formatea timestamp ISO a "DD/MM HH:MM" o solo "HH:MM" si es hoy */
    function fmtUltimaActualizacion(ts) {
        if (!ts || ts === "NaT" || ts === "null") return "";
        try {
            const d = new Date(ts);
            if (isNaN(d.getTime())) return "";
            const ahora = new Date();
            const esHoy = d.toDateString() === ahora.toDateString();
            const hh = String(d.getHours()).padStart(2, "0");
            const mm = String(d.getMinutes()).padStart(2, "0");
            if (esHoy) return `${hh}:${mm}`;
            const dd = String(d.getDate()).padStart(2, "0");
            const mo = String(d.getMonth() + 1).padStart(2, "0");
            return `${dd}/${mo} ${hh}:${mm}`;
        } catch (e) {
            return "";
        }
    }

    /** Devuelve clase CSS segun estado */
    function claseEstado(estado) {
        const map = {
            "OK": "ok",
            "Advertencia": "advertencia",
            "Demorado": "demorado",
            "Error": "error",
        };
        return map[estado] || "error";
    }

    /** Devuelve clase CSS para texto de atraso */
    function claseAtraso(estado) {
        const map = {
            "OK": "atraso-text--ok",
            "Advertencia": "atraso-text--advertencia",
            "Demorado": "atraso-text--demorado",
            "Error": "atraso-text--error",
        };
        return map[estado] || "atraso-text--error";
    }

    /** Calcula el ancho % de la barra de timeline (0-100) */
    function calcWidth(retraso_min) {
        if (retraso_min === null || retraso_min === undefined || isNaN(retraso_min)) return 0;
        const pct = (Math.abs(retraso_min) / MAX_MINUTOS_TIMELINE) * 100;
        return Math.min(pct, 100);
    }

    /** Determina si un tablero esta "late" (requiere atencion) */
    function esLate(estado) { return ESTADOS_LATE.includes(estado); }

    /** Formatea una edad en minutos a texto corto: "12 min", "1 h 5 min", "2 d 3 h". */
    function fmtEdadMin(min) {
        if (min === null || min === undefined || isNaN(min)) return "";
        const m = Math.floor(min);
        if (m < 1) return "menos de 1 min";
        if (m < 60) return `${m} min`;
        if (m < 1440) {
            const h = Math.floor(m / 60);
            const mm = m % 60;
            return mm > 0 ? `${h} h ${mm} min` : `${h} h`;
        }
        const d = Math.floor(m / 1440);
        const h = Math.floor((m % 1440) / 60);
        return h > 0 ? `${d} d ${h} h` : `${d} d`;
    }

    /**
     * Pinta la franja de salud del monitor (honestidad sobre la frescura del dato).
     *   ok            -> verde discreto
     *   desactualizado-> ambar (los datos pueden estar viejos)
     *   caido         -> rojo (la ultima corrida fallo o es muy vieja)
     *   sin_datos     -> ambar
     */
    function renderSalud() {
        const strip = document.getElementById("salud-strip");
        const ico = document.getElementById("salud-ico");
        const txt = document.getElementById("salud-text");
        const badge = document.getElementById("live-badge");
        const badgeTxt = document.getElementById("live-badge-text");
        if (!strip || !txt) return;

        const s = saludData || {};
        const codigo = s.codigo || "sin_datos";
        const edad = fmtEdadMin(s.edad_min);
        const cuando = edad ? `hace ${edad}` : "hora desconocida";
        const fecha = fmtUltimaActualizacion(s.ultima_corrida_fin);

        strip.classList.remove("salud-strip--ok", "salud-strip--warn", "salud-strip--danger");

        if (codigo === "ok") {
            strip.classList.add("salud-strip--ok");
            if (ico) ico.textContent = "\u2713";
            txt.textContent = `Monitor OK \u00b7 ultima corrida ${cuando}`;
            if (badge) badge.classList.remove("header-live-badge--warn", "header-live-badge--danger");
            if (badgeTxt) badgeTxt.textContent = "En vivo";
        } else if (codigo === "desactualizado") {
            strip.classList.add("salud-strip--warn");
            if (ico) ico.textContent = "\u26a0";
            txt.textContent = `Ultima corrida ${cuando} (${fecha}) \u00b7 los datos pueden estar desactualizados`;
            if (badge) badge.classList.add("header-live-badge--warn");
            if (badgeTxt) badgeTxt.textContent = "Demorado";
        } else {
            strip.classList.add("salud-strip--danger");
            if (ico) ico.textContent = "\u26a0";
            const detalle = s.error ? ` \u00b7 ${esc(s.error)}` : "";
            txt.textContent = `Monitor caido: mostrando datos del ${fecha}${detalle}`;
            if (badge) badge.classList.add("header-live-badge--danger");
            if (badgeTxt) badgeTxt.textContent = "Datos viejos";
        }
    }

    // --- Reloj del header ---

    function actualizarReloj() {
        const el = document.getElementById("header-time");
        if (!el) return;
        const ahora = new Date();
        const hh = String(ahora.getHours()).padStart(2, "0");
        const mm = String(ahora.getMinutes()).padStart(2, "0");
        el.textContent = `${hh}:${mm}`;
    }
    setInterval(actualizarReloj, 1000);
    actualizarReloj();

    // --- Carga de datos ---

    async function cargar(silencioso) {
        const btn = document.getElementById("btn-refresh");
        if (corriendo) return;
        corriendo = true;
        if (btn) btn.classList.add("spinning");

        const t0 = performance.now();
        try {
            const r = await fetch(API);
            if (!r.ok) throw new Error(`HTTP ${r.status}`);
            const d = await r.json();
            estadoData = d.estado;
            metaData = d.meta;
            saludData = d.salud || null;
            const t1 = performance.now();
            const segundos = ((t1 - t0) / 1000).toFixed(1);
            const checkEl = document.getElementById("header-check");
            if (checkEl) checkEl.textContent = `Ultima comprobacion: ${segundos}s`;
            render();
            programarSiguienteRefresh();
        } catch (e) {
            console.error("Error cargando datos:", e);
            const checkEl = document.getElementById("header-check");
            if (checkEl) checkEl.textContent = "Ultima comprobacion: error";
        } finally {
            corriendo = false;
            if (btn) btn.classList.remove("spinning");
        }
    }

    // --- Renderizado ---

    function render() {
        // La franja de salud se pinta SIEMPRE, aun sin datos de tableros.
        renderSalud();

        if (!estadoData || !Array.isArray(estadoData)) {
            // Mostrar vacio
            setKPIs(0, 0, 0, 0);
            renderTabla("late-body", []);
            renderTabla("ok-body", []);
            return;
        }

        // Separar tableros
        const late = [];
        const ok = [];
        for (const t of estadoData) {
            if (esLate(t.estado)) late.push(t);
            else ok.push(t);
        }

        // Ordenar late por retraso desc (mayor atraso primero)
        late.sort((a, b) => {
            const ra = a.retraso_min ?? 0;
            const rb = b.retraso_min ?? 0;
            return rb - ra;
        });

        // Ordenar ok por retraso asc (menos atraso primero, o alfabetico)
        ok.sort((a, b) => {
            const ra = a.retraso_min ?? 0;
            const rb = b.retraso_min ?? 0;
            return ra - rb;
        });

        // KPIs — cada numero cuenta una COSA distinta, sin solaparse:
        //   Demorado + Advertencia = tableros que requieren atencion (por separado)
        //   Al dia  = OK
        //   Total   = todos
        const nDemorado = estadoData.filter(t => t.estado === "Demorado").length;
        const nAdvertencia = estadoData.filter(t => t.estado === "Advertencia").length;
        const nError = estadoData.filter(t => t.estado === "Error").length;
        const nOk = estadoData.filter(t => t.estado === "OK").length;
        const nTotal = estadoData.length;
        setKPIs(nDemorado + nError, nAdvertencia, nOk, nTotal);

        // Contadores de secciones
        const lateCount = document.getElementById("late-count");
        const okCount = document.getElementById("ok-count");
        if (lateCount) lateCount.textContent = String(late.length);
        if (okCount) okCount.textContent = String(nOk);

        // Render tablas
        renderTabla("late-body", late);
        renderTabla("ok-body", ok);
    }

    function setKPIs(demorado, advertencia, ok, total) {
        const elD = document.getElementById("kpi-demorado");
        const elW = document.getElementById("kpi-advertencia");
        const elO = document.getElementById("kpi-aldia");
        const elT = document.getElementById("kpi-total");
        if (elD) elD.textContent = String(demorado);
        if (elW) elW.textContent = String(advertencia);
        if (elO) elO.textContent = String(ok);
        if (elT) elT.textContent = String(total);
    }

    function renderTabla(tbodyId, tableros) {
        const tbody = document.getElementById(tbodyId);
        if (!tbody) return;
        if (!tableros.length) {
            tbody.innerHTML = `<tr class="empty-row"><td colspan="7">Sin tableros en esta seccion</td></tr>`;
            return;
        }

        const html = tableros.map(t => {
            const clase = claseEstado(t.estado);
            const ultima = fmtUltimaActualizacion(t.ultima_actualizacion);
            const width = calcWidth(t.retraso_min);
            const hace = esc(t.hace || "");
            const nombre = esc(t.tablero);
            const critico = t.critico ? `<span class="badge-cr">CR</span>` : "";
            const claseAtr = claseAtraso(t.estado);

            return `
                <tr>
                    <td class="col-estado">
                        <span class="state-dot state-dot--${clase}"></span>
                    </td>
                    <td class="col-tablero">
                        ${critico}<span class="tablero-name">${nombre}</span>
                    </td>
                    <td class="col-ultima">${esc(ultima)}</td>
                    <td class="col-timeline">
                        <div class="timeline-track">
                            <div class="timeline-fill timeline-fill--${clase}" style="width: ${width.toFixed(1)}%"></div>
                            <div class="timeline-marks">
                                <div class="timeline-mark timeline-mark--30"></div>
                                <div class="timeline-mark timeline-mark--60"></div>
                                <div class="timeline-mark timeline-mark--1440"></div>
                            </div>
                        </div>
                    </td>
                    <td class="col-atraso ${claseAtr}">${hace}</td>
                    <td class="col-arrow">&rsaquo;</td>
                </tr>
            `;
        }).join("");

        tbody.innerHTML = html;
    }

    // --- Notificaciones del navegador ---
    // ELIMINADAS (orden de Emmanuel, 06/10/2026): el monitor NO avisa por ningun
    // medio. Solo muestra el estado en pantalla. Si en el futuro se quiere avisar
    // por Telegram, se hace en el backend (src/), no en el navegador.

    // --- Refresh automatico ---

    function programarSiguienteRefresh() {
        if (refreshTimer) clearTimeout(refreshTimer);
        const hayLate = estadoData && estadoData.some(t => esLate(t.estado));
        const delay = hayLate ? REFRESH_FAST_MS : REFRESH_SLOW_MS;
        refreshTimer = setTimeout(() => cargar(true), delay);
    }

    // --- Event listeners ---

    document.getElementById("btn-refresh").addEventListener("click", async () => {
        if (corriendo) return;
        // Lanzar corrida manual (con el token de sesion que dejo el servidor en el <meta>)
        const btn = document.getElementById("btn-refresh");
        btn.classList.add("spinning");
        try {
            const meta = document.querySelector('meta[name="csrf-token"]');
            const headers = meta ? { "X-CSRF-Token": meta.getAttribute("content") } : {};
            const r = await fetch(API_CORRIDA, { method: "POST", headers });
            if (!r.ok) {
                const txt = await r.text();
                console.error("Corrida manual fallo:", r.status, txt);
            }
        } catch (e) {
            console.error("Error corrida manual:", e);
        }
        // Recargar datos
        await cargar();
        btn.classList.remove("spinning");
    });

    // --- Inicio ---
    cargar();

    // --- Dark Mode Toggle ---
    // El tema se fija en el <head> (index.html) ANTES del CSS, para evitar el
    // destello al cargar. Aca solo se refleja el estado en el boton y se maneja
    // el clic. Regla: la eleccion del usuario SIEMPRE gana sobre la del sistema.
    function aplicaTema(oscuro) {
        const html = document.documentElement;
        html.classList.toggle("dark", oscuro);
        html.classList.toggle("light", !oscuro);
        const btn = document.getElementById("btn-theme");
        if (btn) btn.textContent = oscuro ? "☀️" : "🌙";
    }

    const btnTheme = document.getElementById("btn-theme");
    if (btnTheme) {
        // Estado inicial: lo que ya dejo el script del <head>, o el sistema.
        let oscuro = document.documentElement.classList.contains("dark");
        if (!document.documentElement.classList.contains("dark")
            && !document.documentElement.classList.contains("light")) {
            oscuro = window.matchMedia
                && window.matchMedia("(prefers-color-scheme: dark)").matches;
        }
        aplicaTema(!!oscuro);

        btnTheme.addEventListener("click", () => {
            const oscuroAhora = !document.documentElement.classList.contains("dark");
            aplicaTema(oscuroAhora);
            try {
                localStorage.setItem("monitor-theme", oscuroAhora ? "dark" : "light");
            } catch (e) { /* sin localStorage: el tema no persiste, pero la UI funciona */ }
        });
    }
})();
