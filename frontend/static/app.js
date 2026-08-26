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
    let corriendo = false;
    let refreshTimer = null;
    let notifiedSet = {};  // evita spam de notificaciones

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

        // KPIs
        const nAtencion = late.length;
        const nAdvertencia = estadoData.filter(t => t.estado === "Advertencia").length;
        const nOk = estadoData.filter(t => t.estado === "OK").length;
        const nTotal = estadoData.length;
        setKPIs(nAtencion, nAdvertencia, nOk, nTotal);

        // Contadores de secciones
        const lateCount = document.getElementById("late-count");
        const okCount = document.getElementById("ok-count");
        if (lateCount) lateCount.textContent = String(nAtencion);
        if (okCount) okCount.textContent = String(nOk);

        // Render tablas
        renderTabla("late-body", late);
        renderTabla("ok-body", ok);

        // Notificaciones de criticos nuevos
        detectarNuevosAtrasadosCriticos(late);
    }

    function setKPIs(atencion, advertencia, ok, total) {
        const elA = document.getElementById("kpi-atencion");
        const elW = document.getElementById("kpi-advertencia");
        const elO = document.getElementById("kpi-aldia");
        const elT = document.getElementById("kpi-total");
        if (elA) elA.textContent = String(atencion);
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

    function detectarNuevosAtrasadosCriticos(late) {
        if (!late.length) {
            notifiedSet = {};  // reset cuando todo vuelve a la normalidad
            return;
        }
        for (const t of late) {
            if (!t.critico) continue;
            const key = t.tablero;
            if (!notifiedSet[key]) {
                notificarTablero(t);
                notifiedSet[key] = true;
            }
        }
    }

    function notificarTablero(t) {
        if (!("Notification" in window)) return;
        if (Notification.permission === "granted") {
            new Notification(`Tablero critico atrasado: ${t.tablero}`, {
                body: `Estado: ${t.estado} - ${t.hace || ""}`,
                icon: "/static/icons8-power-bi-50.ico",
            });
        } else if (Notification.permission !== "denied") {
            Notification.requestPermission().then(p => {
                if (p === "granted") notificarTablero(t);
            });
        }
    }

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
        // Lanzar corrida manual
        const btn = document.getElementById("btn-refresh");
        btn.classList.add("spinning");
        try {
            const r = await fetch(API_CORRIDA, { method: "POST" });
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

})();
