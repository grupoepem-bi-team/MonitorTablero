/*
 * js_smoke.js - Smoke test del JavaScript del panel (sin navegador).
 *
 * POR QUE EXISTE: el 06/10/2026 un cambio en app.js dejo una variable usada pero
 * ya no declarada (`nAtencion`). El render explotaba con ReferenceError y la tabla
 * quedaba VACIA en produccion, mientras la suite de Python seguia toda verde: no
 * habia NINGUNA prueba que ejecutara el JavaScript del panel.
 *
 * QUE CUBRE (ejecuta el app.js REAL contra un DOM minimo):
 *   1. RENDER        -> pinta las tablas, los KPIs y los contadores
 *   2. TEMA arranque -> sigue el tema del sistema si el usuario no eligio
 *   3. TEMA eleccion -> LA ELECCION DEL USUARIO GANA (el bug: "claro" no se aplicaba)
 *   4. TEMA clic     -> cambia y se guarda en localStorage
 *   5. BOTON         -> "Actualizar" manda POST /api/corrida con X-CSRF-Token
 *   6. SIN AVISOS    -> no dispara ninguna notificacion (orden 06/10/2026)
 *
 * Uso:  node tests/js_smoke.js      (exit 0 = OK, exit 1 = fallo)
 */
"use strict";

const fs = require("fs");
const path = require("path");
const vm = require("vm");

const APP_JS = path.join(__dirname, "..", "frontend", "static", "app.js");
const CODIGO = fs.readFileSync(APP_JS, "utf8");

const CSRF_ESPERADO = "TOKEN-TEST";

// --- Payload de ejemplo: 3 tableros (1 critico atrasado, 1 aviso, 1 al dia) ---
const PAYLOAD = {
  estado: [
    {
      tablero: "Tablero Lento", critico: 1, estado: "Demorado",
      ultima_actualizacion: "2026-10-06T08:00:00", hora_consulta: "2026-10-06T10:00:00",
      retraso_min: 120.0, ratio: 2.0, hace: "2h", error_detalle: "",
    },
    {
      tablero: "Tablero Aviso", critico: 0, estado: "Advertencia",
      ultima_actualizacion: "2026-10-06T09:30:00", hora_consulta: "2026-10-06T10:00:00",
      retraso_min: 30.0, ratio: 0.5, hace: "30min", error_detalle: "",
    },
    {
      tablero: "Tablero Al Dia", critico: 0, estado: "OK",
      ultima_actualizacion: "2026-10-06T09:55:00", hora_consulta: "2026-10-06T10:00:00",
      retraso_min: 5.0, ratio: 0.1, hace: "5min", error_detalle: "",
    },
  ],
  cambios: { lineas_cambios_ui: [], lineas_fallos: [] },
  meta: {
    version: 1, ultima_corrida_fin: "2026-10-06T10:00:00", duracion_s: 2.5,
    exito: true, error: null, n_tableros: 3, n_cambios_estado: 0,
  },
  metricas: null,
  salud: { codigo: "ok", exito: true, edad_min: 1.0, ultima_corrida_fin: "2026-10-06T10:00:00", error: null },
  error: null,
};

// ---------------------------------------------------------------------------
// DOM minimo y arnes
// ---------------------------------------------------------------------------

function makeEnv(opts) {
  opts = opts || {};
  const els = {};

  function makeEl(id) {
    const cl = new Set();
    return {
      id: id,
      textContent: "",
      innerHTML: "",
      className: "",
      _handlers: {},
      classList: {
        add() { for (const a of arguments) cl.add(a); },
        remove() { for (const a of arguments) cl.delete(a); },
        toggle(c, on) {
          if (on === undefined) { cl.has(c) ? cl.delete(c) : cl.add(c); }
          else if (on) { cl.add(c); } else { cl.delete(c); }
          return cl.has(c);
        },
        contains(c) { return cl.has(c); },
      },
      addEventListener(ev, fn) { (this._handlers[ev] = this._handlers[ev] || []).push(fn); },
      /** Dispara los handlers como si el usuario hubiera hecho clic. */
      click() { (this._handlers["click"] || []).forEach(function (fn) { fn({}); }); },
      getAttribute(name) { return name === "content" ? CSRF_ESPERADO : null; },
      querySelectorAll() { return []; },
    };
  }
  const getEl = (id) => (els[id] = els[id] || makeEl(id));

  const storage = Object.assign({}, opts.storage || {});
  const errores = [];
  const fetchCalls = [];
  const notifCalls = [];

  // El script del <head> (index.html) fija la clase ANTES de que corra app.js.
  const htmlEl = makeEl("html");
  if (opts.headClass) htmlEl.classList.add(opts.headClass);

  const documentStub = {
    documentElement: htmlEl,
    getElementById: getEl,
    querySelector: (sel) => (String(sel).indexOf("csrf-token") !== -1
      ? { getAttribute: () => CSRF_ESPERADO }
      : null),
    querySelectorAll: () => [],
    createElement: () => ({
      set textContent(v) { this._t = String(v); },
      get innerHTML() { return this._t == null ? "" : this._t; },
    }),
    addEventListener() {},
  };

  function NotificacionStub(title, o) { notifCalls.push({ title: title, opts: o }); }
  NotificacionStub.permission = "granted";
  NotificacionStub.requestPermission = () => Promise.resolve("granted");

  const sandbox = {
    document: documentStub,
    window: {
      matchMedia: () => ({ matches: !!opts.prefsDark }),
      addEventListener() {},
    },
    localStorage: {
      getItem: (k) => (Object.prototype.hasOwnProperty.call(storage, k) ? storage[k] : null),
      setItem: (k, v) => { storage[k] = String(v); },
      removeItem: (k) => { delete storage[k]; },
    },
    console: {
      log() {},
      warn() {},
      error() { errores.push(Array.prototype.map.call(arguments, String).join(" ")); },
    },
    fetch: (url, o) => {
      fetchCalls.push({
        url: String(url),
        method: (o && o.method) || "GET",
        headers: (o && o.headers) || {},
      });
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve(PAYLOAD),
        text: () => Promise.resolve("ok"),
      });
    },
    // NO se ejecutan: evitan que el auto-refresh entre en bucle dentro del test.
    setInterval: () => 0,
    clearTimeout: () => {},
    setTimeout: () => 0,
    performance: { now: () => 1 },
    Notification: NotificacionStub,
    Date: Date, Math: Math, JSON: JSON, String: String, Number: Number,
    Array: Array, Object: Object, Promise: Promise, Set: Set, Error: Error,
    isNaN: isNaN, parseInt: parseInt, parseFloat: parseFloat,
  };
  sandbox.window.document = documentStub;
  sandbox.window.localStorage = sandbox.localStorage;
  sandbox.globalThis = sandbox;

  return { els, getEl, storage, errores, fetchCalls, notifCalls, htmlEl, sandbox };
}

/** Deja que se resuelvan las promesas del fetch/cargar dentro del sandbox. */
function asentar() {
  return new Promise((res) => setImmediate(res))
    .then(() => new Promise((res) => setImmediate(res)))
    .then(() => new Promise((res) => setImmediate(res)));
}

/** Corre el app.js real con el escenario pedido y devuelve el entorno. */
function correr(opts) {
  const env = makeEnv(opts);
  vm.createContext(env.sandbox);
  vm.runInContext(CODIGO, env.sandbox, { filename: "app.js" });
  return asentar().then(() => env);
}

// ---------------------------------------------------------------------------
// Escenarios
// ---------------------------------------------------------------------------

const fallos = [];
function revisar(cond, mensaje) { if (!cond) fallos.push(mensaje); }

async function main() {
  // ---- 1. RENDER ----
  {
    const env = await correr({ prefsDark: false, headClass: "light" });
    const late = env.getEl("late-body").innerHTML;
    const ok = env.getEl("ok-body").innerHTML;

    revisar(env.errores.length === 0,
      "render: hubo errores de consola -> " + env.errores.join(" | "));
    revisar(late.indexOf("Tablero Lento") !== -1,
      "render: la tabla 'Requieren atencion' no pinto el tablero Demorado");
    // "Advertencia" cuenta como tablero que REQUIERE ATENCION (ESTADOS_LATE).
    revisar(late.indexOf("Tablero Aviso") !== -1,
      "render: la tabla 'Requieren atencion' no pinto el tablero en Advertencia");
    revisar(ok.indexOf("Tablero Al Dia") !== -1,
      "render: la tabla 'Al dia' no pinto el tablero OK");

    const kpis = [env.getEl("kpi-demorado").textContent, env.getEl("kpi-advertencia").textContent,
      env.getEl("kpi-aldia").textContent, env.getEl("kpi-total").textContent].join("/");
    revisar(kpis === "1/1/1/3", "render: KPIs incorrectos, se esperaba 1/1/1/3 y salio " + kpis);
    revisar(env.getEl("late-count").textContent === "2",
      "render: el contador de 'Requieren atencion' deberia ser 2 y fue " + env.getEl("late-count").textContent);
    revisar(env.getEl("ok-count").textContent === "1",
      "render: el contador de 'Al dia' deberia ser 1 y fue " + env.getEl("ok-count").textContent);
    revisar(env.getEl("salud-text").textContent.indexOf("OK") !== -1,
      "render: la franja de salud no quedo en OK");
  }

  // ---- 2. TEMA: arranque segun el sistema ----
  {
    const envOsc = await correr({ prefsDark: true });
    revisar(envOsc.htmlEl.classList.contains("dark"),
      "tema: con PC en oscuro y sin eleccion previa debe quedar en 'dark'");
    revisar(envOsc.getEl("btn-theme").textContent === "☀️",
      "tema: el boton deberia mostrar ☀️ cuando esta en oscuro");

    const envClaro = await correr({ prefsDark: false });
    revisar(envClaro.htmlEl.classList.contains("light"),
      "tema: con PC en claro y sin eleccion previa debe quedar en 'light'");
  }

  // ---- 3. TEMA: LA ELECCION DEL USUARIO GANA (el bug del 06/10) ----
  {
    // PC en OSCURO pero el usuario eligio CLARO antes -> debe respetarse.
    const env = await correr({ prefsDark: true, headClass: "light", storage: { "monitor-theme": "light" } });
    revisar(env.htmlEl.classList.contains("light") && !env.htmlEl.classList.contains("dark"),
      "tema: PC en oscuro + usuario eligio CLARO -> debe quedar CLARO (regresion del bug del dark mode)");
    revisar(env.getEl("btn-theme").textContent === "🌙",
      "tema: con tema claro el boton debe mostrar 🌙");

    // Y al reves: PC en claro con eleccion previa de OSCURO.
    const env2 = await correr({ prefsDark: false, headClass: "dark", storage: { "monitor-theme": "dark" } });
    revisar(env2.htmlEl.classList.contains("dark"),
      "tema: PC en claro + usuario eligio OSCURO -> debe quedar OSCURO");
  }

  // ---- 4. TEMA: el clic cambia y persiste ----
  {
    const env = await correr({ prefsDark: false, headClass: "light" });
    revisar(env.htmlEl.classList.contains("light"), "tema: estado inicial deberia ser claro");

    env.getEl("btn-theme").click();
    revisar(env.htmlEl.classList.contains("dark") && !env.htmlEl.classList.contains("light"),
      "tema: el primer clic debe pasar a OSCURO");
    revisar(env.storage["monitor-theme"] === "dark",
      "tema: el clic debe guardar la eleccion en localStorage");

    env.getEl("btn-theme").click();
    revisar(env.htmlEl.classList.contains("light"),
      "tema: el segundo clic debe volver a CLARO");
    revisar(env.storage["monitor-theme"] === "light",
      "tema: el segundo clic debe guardar 'light'");
    // Nunca debe quedar el <html> SIN clase: era la causa del bug original.
    revisar(env.htmlEl.classList.contains("dark") || env.htmlEl.classList.contains("light"),
      "tema: el <html> nunca debe quedar sin clase dark/light");
  }

  // ---- 5. BOTON "Actualizar" -> POST /api/corrida con el token ----
  {
    const env = await correr({ prefsDark: false, headClass: "light" });
    const antes = env.fetchCalls.length;
    env.getEl("btn-refresh").click();
    await asentar();

    const nuevas = env.fetchCalls.slice(antes);
    const corr = nuevas.filter((c) => c.url.indexOf("/api/corrida") !== -1);
    revisar(corr.length === 1, "boton: deberia disparar 1 POST a /api/corrida (disparo " + corr.length + ")");
    if (corr.length) {
      revisar(corr[0].method === "POST", "boton: /api/corrida debe ir por POST");
      const tok = corr[0].headers["X-CSRF-Token"] || corr[0].headers["x-csrf-token"];
      revisar(tok === CSRF_ESPERADO,
        "boton: debe mandar la cabecera X-CSRF-Token con el token del <meta> (mando: " + tok + ")");
    }
    revisar(nuevas.some((c) => c.url.indexOf("/api/todos") !== -1),
      "boton: despues de la corrida debe recargar los datos (/api/todos)");
  }

  // ---- 6. SIN AVISOS ----
  {
    const env = await correr({ prefsDark: false, headClass: "light" });
    revisar(env.notifCalls.length === 0,
      "avisos: el monitor NO debe disparar notificaciones (disparo " + env.notifCalls.length + ")");
    revisar(CODIGO.indexOf("new Notification(") === -1 && CODIGO.indexOf("requestPermission") === -1,
      "avisos: quedo codigo de notificaciones del navegador en app.js");
  }

  // ---- Resultado ----
  if (fallos.length) {
    console.error("FALLO js_smoke:");
    for (const f of fallos) console.error("  - " + f);
    process.exit(1);
  }
  console.log("OK js_smoke: render + KPIs + tema (sistema/eleccion/clic) + boton con token + sin avisos.");
  process.exit(0);
}

main().catch((e) => {
  console.error("FALLO js_smoke: excepcion inesperada -> " + (e && e.message ? e.message : e));
  process.exit(1);
});
