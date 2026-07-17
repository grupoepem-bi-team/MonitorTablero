/* ==========================================================================
   app.js — Monitor de Tableros.
   2 secciones: Atrasados + Al dia.
   Animaciones: carga de pagina, transicion entre secciones (slide).
   ========================================================================== */

(function () {
    "use strict";

    const STALE_MIN = 60;
    const API = "/api/todos";
    const API_CORRIDA = "/api/corrida";
    const REFRESH_FAST_MS = 30 * 1000;   // 30s cuando hay atrasados
    const REFRESH_SLOW_MS = 5 * 60 * 1000; // 5min cuando todo OK

    let estadoData = null;
    let metaData = null;
    let corriendo = false;
    let prevMap = {};
    let isFirstRender = true;
    let refreshTimer = null;
    let notifiedSet = {};  // tableros ya notificados (evita spam)

    const ESTADOS_LATE = ["Demorado", "Error", "Advertencia"];

    const ICONOS = {
        OK: '<svg class="ic ic--OK" viewBox="0 0 14 14" fill="none" aria-hidden="true"><path d="M3 7.5L6 10.5L11 4.5" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>',
        Advertencia: '<svg class="ic ic--Advertencia" viewBox="0 0 14 14" fill="none" aria-hidden="true"><circle cx="7" cy="7" r="5.5" stroke="currentColor" stroke-width="1.5"/><path d="M7 4v3.5M7 9.5v.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>',
        Demorado: '<svg class="ic ic--Demorado" viewBox="0 0 14 14" fill="none" aria-hidden="true"><path d="M7 1.5L13 12.5H1L7 1.5z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/><path d="M7 5.5v3M7 10v.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>',
        Error: '<svg class="ic ic--Error" viewBox="0 0 14 14" fill="none" aria-hidden="true"><path d="M7 1.5L13 12.5H1L7 1.5z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/><path d="M7 5.5v3M7 10v.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>',
    };

    function esc(s) { const d = document.createElement("div"); d.textContent = String(s ?? ""); return d.innerHTML; }

    function fmtCorta(ts) {
        if (!ts || ts === "NaT") return "";
        try {
            const d = new Date(ts); if (isNaN(d.getTime())) return "";
            const ahora = new Date(); const hoy = d.toDateString() === ahora.toDateString();
            const hh = String(d.getHours()).padStart(2, "0"); const mm = String(d.getMinutes()).padStart(2, "0");
            if (hoy) return hh + ":" + mm;
            return String(d.getDate()).padStart(2, "0") + "/" + String(d.getMonth() + 1).padStart(2, "0") + " " + hh + ":" + mm;
        } catch { return ""; }
    }

    function fmtCompleta(ts) {
        if (!ts || ts === "NaT") return "";
        try { const d = new Date(ts); if (isNaN(d.getTime())) return ""; return d.toLocaleString("es-AR", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" }); }
        catch { return ""; }
    }

    function fmtHace(min) {
        if (min === null || min === undefined || isNaN(min)) return "";
        const m = Math.abs(min);
        if (m < 60) return "hace " + Math.round(m) + "min";
        if (m < 1440) return "hace " + Math.floor(m / 60) + "h";
        return "hace " + Math.floor(m / 1440) + "d";
    }

    function minDesde(ts) {
        if (!ts) return Infinity; const d = new Date(ts);
        if (isNaN(d.getTime())) return Infinity; return (Date.now() - d.getTime()) / 60000;
    }

    function esLate(estado) { return ESTADOS_LATE.includes(estado); }

    // --- Carga ---

    async function cargar() {
        try {
            const r = await fetch(API); if (!r.ok) return;
            const d = await r.json();
            // Detectar nuevos atrasados criticos antes de actualizar
            const nuevosAtrasados = detectarNuevosAtrasados(d.estado);
            estadoData = d.estado; metaData = d.meta;
            render();
            // Notificar al navegador
            for (const t of nuevosAtrasados) notificarTablero(t);
        } catch (e) {}
    }

    function detectarNuevosAtrasados(nuevoEstado) {
        if (!estadoData || !nuevoEstado) return [];
        const nuevos = [];
        for (const t of nuevoEstado) {
            const prev = prevMap[t.tablero];
            if (!prev) continue;
            const wasLate = esLate(prev);
            const nowLate = esLate(t.estado);
            // Notificar solo si: subio a atrasados Y es critico Y no fue notificado ya
            if (!wasLate && nowLate && t.critico === 1 && !notifiedSet[t.tablero]) {
                nuevos.push(t);
                notifiedSet[t.tablero] = true;
            }
            // Limpiar flag si volvio a OK
            if (!nowLate && notifiedSet[t.tablero]) {
                delete notifiedSet[t.tablero];
            }
        }
        return nuevos;
    }

    function notificarTablero(t) {
        if (!("Notification" in window)) return;
        if (Notification.permission === "granted") {
            const n = new Notification("Tablero critico atrasado", {
                body: t.tablero + " - " + fmtHace(t.retraso_min),
                tag: "tablero-" + t.tablero,
            });
            n.onclick = function () { window.focus(); n.close(); };
        }
    }

    function pedirPermisoNotificaciones() {
        if (!("Notification" in window)) return;
        if (Notification.permission === "default") {
            Notification.requestPermission();
        }
    }

    async function lanzarCorrida() {
        if (corriendo) return; corriendo = true;
        const btn = document.getElementById("dc-btn-actualizar");
        const txt = btn.querySelector(".btn__text");
        btn.classList.add("btn--loading"); btn.disabled = true; txt.textContent = "...";
        try {
            const r = await fetch(API_CORRIDA, { method: "POST" }); const d = await r.json();
            if (!r.ok) return;
            const nuevos = detectarNuevosAtrasados(d.estado);
            estadoData = d.estado; metaData = d.meta; render();
            for (const t of nuevos) notificarTablero(t);
        } catch (e) {}
        finally { corriendo = false; btn.classList.remove("btn--loading"); btn.disabled = false; txt.textContent = "Actualizar"; }
    }

    // --- Render ---

    function render() {
        if (!estadoData) return;

        // Animacion de carga: header pulsa al cargar/actualizar
        const app = document.querySelector(".app");
        if (isFirstRender) {
            app.classList.add("app--loading");
            setTimeout(function () { app.classList.remove("app--loading"); }, 600);
        } else {
            app.classList.add("app--refresh");
            setTimeout(function () { app.classList.remove("app--refresh"); }, 400);
        }

        renderBarra();
        renderSeccion("late", "dc-late-list", "dc-late-count", ESTADOS_LATE);
        renderSeccion("ok", "dc-ok-list", "dc-ok-count", ["OK"]);
        renderFooter();

        // Guardar estado actual para comparar en la proxima render
        prevMap = {};
        estadoData.forEach(function (t) { prevMap[t.tablero] = t.estado; });
        isFirstRender = false;

        // Re-programar refresh segun estado actual
        programarRefresh();
    }

    function renderBarra() {
        const el = document.getElementById("dc-ultima-consulta");
        if (!estadoData || estadoData.length === 0) { el.textContent = "sin tableros"; return; }
        const primera = estadoData[0];
        let txt = esc(fmtCorta(primera.hora_consulta));
        const ms = minDesde(primera.hora_consulta);
        if (ms > STALE_MIN) { const h = Math.floor(ms / 60); txt += ' <span class="stale">' + (h > 0 ? h + "h" : Math.round(ms) + "min") + "</span>"; }
        if (metaData && metaData.duracion_s != null && metaData.exito) txt += " <span style='opacity:0.5;font-size:0.78em'>" + metaData.duracion_s + "s</span>";
        el.innerHTML = txt;
    }

    function renderSeccion(tipo, listId, countId, estados) {
        const listEl = document.getElementById(listId);
        const countEl = document.getElementById(countId);
        const items = (estadoData || []).filter(function (t) { return estados.includes(t.estado); })
            .sort(function (a, b) { return (b.retraso_min ?? -Infinity) - (a.retraso_min ?? -Infinity); });

        if (countEl) countEl.textContent = items.length;

        if (items.length === 0) {
            if (tipo === "ok") {
                listEl.innerHTML = '<div class="empty">Sin tableros al dia</div>';
            } else {
                listEl.innerHTML = '<div class="empty"><span class="dot dot--OK"></span>Ningun tablero atrasado</div>';
            }
            return;
        }

        let html = "";
        for (const t of items) {
            const dotCls = "dot dot--" + t.estado;
            const ic = ICONOS[t.estado] || "";
            const haceCls = "item__hace item__hace--" + t.estado;
            const ult = fmtCorta(t.ultima_actualizacion);
            const hace = fmtHace(t.retraso_min);
            const crit = t.critico === 1 ? '<span class="crit-mark">CR</span>' : "";
            const warnCls = t.estado === "Advertencia" ? " item--warn" : "";

            // Detectar transicion de seccion para animar
            let transCls = "";
            if (!isFirstRender) {
                const prevEstado = prevMap[t.tablero];
                if (prevEstado && prevEstado !== t.estado) {
                    const wasLate = esLate(prevEstado);
                    const nowLate = esLate(t.estado);
                    if (!wasLate && nowLate) {
                        // Subio a atrasados: entra desde arriba
                        transCls = " item--enter-late";
                    } else if (wasLate && !nowLate) {
                        // Paso a OK: entra desde abajo
                        transCls = " item--enter-ok";
                    }
                }
            }

            html += '<div class="item' + warnCls + transCls + '">' +
                '<span class="' + dotCls + '"></span>' +
                '<span class="item__name">' + crit + esc(t.tablero) + "</span>" +
                '<span class="item__meta">' +
                (ult ? '<span class="item__ult">' + esc(ult) + "</span>" : "") +
                (ic ? ic : "") +
                '<span class="' + haceCls + '" data-ts="' + esc(t.ultima_actualizacion) + '">' + esc(hace) + "</span>" +
                "</span></div>";
        }
        listEl.innerHTML = html;
    }

    function renderFooter() {
        const el = document.getElementById("dc-footer-meta");
        if (metaData && metaData.ultima_corrida_fin) el.textContent = "ultima corrida " + fmtCorta(metaData.ultima_corrida_fin);
        else el.textContent = "—";
    }

    // --- Tooltip ---

    function setupTooltip() {
        const tt = document.createElement("div");
        tt.className = "tooltip"; tt.id = "dc-tooltip"; tt.hidden = true;
        document.body.appendChild(tt);
        document.addEventListener("mouseover", function (e) {
            const t = e.target.closest("[data-ts]"); if (!t) return;
            const ts = t.dataset.ts; if (!ts || ts === "NaT") return;
            tt.textContent = fmtCompleta(ts); tt.hidden = false;
            const r = t.getBoundingClientRect();
            tt.style.left = r.left + "px"; tt.style.top = (r.top - tt.offsetHeight - 5) + "px";
        });
        document.addEventListener("mouseout", function (e) { if (e.target.closest("[data-ts]")) tt.hidden = true; });
    }

    // --- Theme ---

    function initTheme() {
        const saved = localStorage.getItem("dc-theme") || "auto";
        applyTheme(saved);
        document.querySelectorAll(".theme-btn").forEach(function (b) {
            b.addEventListener("click", function () {
                const theme = b.dataset.theme;
                localStorage.setItem("dc-theme", theme);
                applyTheme(theme);
            });
        });
        // En modo auto, re-evaluar cada minuto segun horario
        setInterval(function () {
            if (localStorage.getItem("dc-theme") === "auto") applyTheme("auto");
        }, 60000);
    }

    function applyTheme(theme) {
        const root = document.documentElement;
        if (theme === "auto") {
            // Segun horario del sistema: 6:00-18:00 = light, 18:00-6:00 = dark
            const hora = new Date().getHours();
            const modo = (hora >= 6 && hora < 18) ? "light" : "dark";
            root.setAttribute("data-theme", modo);
        } else {
            root.setAttribute("data-theme", theme);
        }
        // Marcar boton activo
        document.querySelectorAll(".theme-btn").forEach(function (b) {
            b.classList.toggle("theme-btn--active", b.dataset.theme === theme);
        });
    }

    function programarRefresh() {
        if (refreshTimer) clearTimeout(refreshTimer);
        // Si hay atrasados, refrescar rapido. Si todo OK, refrescar lento.
        const hayAtrasados = estadoData && estadoData.some(function (t) { return esLate(t.estado); });
        const ms = hayAtrasados ? REFRESH_FAST_MS : REFRESH_SLOW_MS;
        refreshTimer = setTimeout(cargar, ms);
        // Mostrar countdown en footer
        renderProximoRefresh(ms);
    }

    function renderProximoRefresh(ms) {
        const el = document.getElementById("dc-next-refresh");
        if (!el) return;
        const segs = Math.round(ms / 1000);
        if (segs >= 60) el.textContent = "prox. " + Math.round(segs / 60) + "min";
        else el.textContent = "prox. " + segs + "s";
    }

    // --- Sidebar: reloj, calendario, temperatura ---

    function initClock() {
        let lastSec = -1, lastMin = -1;
        const widgetEl = document.querySelector(".widget--clock");
        const hmEl = document.getElementById("dc-clock-hm");
        const hhEl = document.getElementById("dc-clock-hh");
        const mmEl = document.getElementById("dc-clock-mm");
        const secsEl = document.getElementById("dc-clock-secs");
        const dateEl = document.getElementById("dc-clock-date");
        const dias = ["domingo", "lunes", "martes", "miércoles", "jueves", "viernes", "sábado"];
        const meses = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"];

        function tick() {
            const now = new Date();
            const ss = now.getSeconds();
            const mm = now.getMinutes();
            const hh = now.getHours();
            if (ss === lastSec) return;
            lastSec = ss;

            if (hhEl) hhEl.textContent = String(hh).padStart(2, "0");
            if (mmEl) mmEl.textContent = String(mm).padStart(2, "0");
            if (secsEl) {
                secsEl.textContent = String(ss).padStart(2, "0");
                secsEl.style.animation = "none";
                void secsEl.offsetWidth;
                secsEl.style.animation = "";
            }

            // Flip al cambiar de minuto
            if (mm !== lastMin && lastMin !== -1 && hmEl) {
                hmEl.classList.remove("clock__hm--flip");
                void hmEl.offsetWidth;
                hmEl.classList.add("clock__hm--flip");
            }
            lastMin = mm;

            // Respingue del borde del widget en cada segundo par (muy sutil)
            if (widgetEl && ss % 2 === 0) {
                widgetEl.classList.remove("is-tick");
                void widgetEl.offsetWidth;
                widgetEl.classList.add("is-tick");
            }

            if (dateEl) {
                const txt = dias[now.getDay()] + " " + now.getDate() + " " + meses[now.getMonth()];
                dateEl.textContent = txt.charAt(0).toUpperCase() + txt.slice(1);
            }
        }
        tick();
        setInterval(tick, 1000);
    }

    function initCalendar() {
        const now = new Date();
        const year = now.getFullYear();
        const month = now.getMonth();
        const meses = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"];
        const dowShort = ["L", "M", "X", "J", "V", "S", "D"];

        const headerEl = document.getElementById("dc-cal-month");
        if (headerEl) headerEl.textContent = meses[month] + " " + year;

        const gridEl = document.getElementById("dc-cal-grid");
        if (!gridEl) return;

        // Dias de la semana
        let html = "";
        dowShort.forEach(function (d) {
            html += '<div class="cal__dow">' + d + "</div>";
        });

        // Dia 1: que dia de la semana era? (L=0, D=6)
        const firstDay = new Date(year, month, 1);
        let startOffset = firstDay.getDay() - 1; // Domingo=0 → Lunes=0
        if (startOffset < 0) startOffset = 6;

        // Espacios vacios antes del dia 1
        for (let i = 0; i < startOffset; i++) {
            html += '<div class="cal__day cal__day--empty"></div>';
        }

        // Dias del mes (con stagger de entrada)
        const lastDay = new Date(year, month + 1, 0).getDate();
        const today = now.getDate();
        let dayIdx = 0;
        for (let d = 1; d <= lastDay; d++) {
            const dow = new Date(year, month, d).getDay();
            const isToday = d === today;
            const isWeekend = dow === 0 || dow === 6;
            const isPast = d < today;
            let cls = "cal__day";
            if (isToday) cls += " cal__day--today";
            else if (isPast) cls += " cal__day--past";
            if (isWeekend && !isToday) cls += " cal__day--weekend";
            const delay = Math.min(dayIdx * 14, 280);
            html += '<div class="' + cls + '" style="animation-delay:' + delay + 'ms">' + d + "</div>";
            dayIdx++;
        }

        gridEl.innerHTML = html;
    }

    // --- Init ---

    function init() {
        initTheme();
        initClock();
        initCalendar();
        document.getElementById("dc-btn-actualizar").addEventListener("click", lanzarCorrida);
        setupTooltip();
        pedirPermisoNotificaciones();
        // Carga inicial
        cargar().then(programarRefresh);
        // El refresh se reprograma solo despues de cada carga
    }

    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
    else init();
})();