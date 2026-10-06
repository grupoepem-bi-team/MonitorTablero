/*
 * js_smoke.js - Smoke test del JavaScript del panel (sin navegador).
 *
 * POR QUE EXISTE: el 06/10/2026 un cambio en app.js dejo una variable usada
 * pero ya no declarada (`nAtencion`). El render explotaba con ReferenceError y
 * la tabla quedaba VACIA en produccion, mientras la suite de Python seguia toda
 * verde (no habia ninguna prueba que ejecutara el JS). Este harness corre el
 * app.js REAL contra un DOM minimo y falla si el render no pinta las filas.
 *
 * Uso:  node tests/js_smoke.js      (exit 0 = OK, exit 1 = fallo)
 */
"use strict";

const fs = require("fs");
const path = require("path");
const vm = require("vm");

const APP_JS = path.join(__dirname, "..", "frontend", "static", "app.js");

// --- Payload de ejemplo: 2 tableros (uno atrasado, uno OK) ---
const PAYLOAD = {
  estado: [
    {
      tablero: "Tablero Lento",
      critico: 1,
      estado: "Demorado",
      ultima_actualizacion: "2026-10-06T08:00:00",
      hora_consulta: "2026-10-06T10:00:00",
      retraso_min: 120.0,
      ratio: 2.0,
      hace: "2h",
      error_detalle: "",
    },
    {
      tablero: "Tablero Al Dia",
      critico: 0,
      estado: "OK",
      ultima_actualizacion: "2026-10-06T09:55:00",
      hora_consulta: "2026-10-06T10:00:00",
      retraso_min: 5.0,
      ratio: 0.1,
      hace: "5min",
      error_detalle: "",
    },
    {
      tablero: "Tablero Aviso",
      critico: 0,
      estado: "Advertencia",
      ultima_actualizacion: "2026-10-06T09:30:00",
      hora_consulta: "2026-10-06T10:00:00",
      retraso_min: 30.0,
      ratio: 0.5,
      hace: "30min",
      error_detalle: "",
    },
  ],
  cambios: { lineas_cambios_ui: [], lineas_fallos: [] },
  meta: {
    version: 1,
    ultima_corrida_fin: "2026-10-06T10:00:00",
    duracion_s: 2.5,
    exito: true,
    error: null,
    n_tableros: 3,
    n_cambios_estado: 0,
  },
  metricas: null,
  salud: { codigo: "ok", exito: true, edad_min: 1.0, ultima_corrida_fin: "2026-10-06T10:00:00", error: null },
  error: null,
};

// --- DOM minimo ---
function makeElement(id) {
  return {
    id: id,
    textContent: "",
    innerHTML: "",
    className: "",
    classList: {
      _set: new Set(),
      add() { for (const a of arguments) this._set.add(a); },
      remove() { for (const a of arguments) this._set.delete(a); },
      toggle(c, on) { if (on === undefined) { this._set.has(c) ? this._set.delete(c) : this._set.add(c); } else if (on) { this._set.add(c); } else { this._set.delete(c); } return this._set.has(c); },
      contains(c) { return this._set.has(c); },
    },
    addEventListener() {},
    getAttribute() { return null; },
    querySelectorAll() { return []; },
  };
}

const elementos = {};
function el(id) {
  if (!elementos[id]) elementos[id] = makeElement(id);
  return elementos[id];
}

const erroresConsola = [];
const htmlDe = (id) => (elementos[id] ? elementos[id].innerHTML : "");

const documentStub = {
  documentElement: makeElement("html"),
  getElementById: el,
  querySelector: () => null,
  querySelectorAll: () => [],
  createElement: () => ({ set textContent(v) { this._t = String(v); }, get innerHTML() { return String(this._t == null ? "" : this._t); } }),
  addEventListener() {},
};

const sandbox = {
  document: documentStub,
  window: {
    matchMedia: () => ({ matches: false }),
    addEventListener() {},
  },
  localStorage: { getItem: () => null, setItem() {}, removeItem() {} },
  console: {
    log: () => {},
    warn: () => {},
    error: (...a) => erroresConsola.push(a.map(String).join(" ")),
  },
  fetch: () => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(PAYLOAD) }),
  setInterval: () => 0,
  clearTimeout: () => {},
  setTimeout: (fn) => { if (typeof fn === "function") fn(); return 0; },
  performance: { now: () => 1 },
  Notification: undefined,
  Date: Date,
  Math: Math,
  JSON: JSON,
  String: String,
  Number: Number,
  Array: Array,
  Object: Object,
  isNaN: isNaN,
  parseInt: parseInt,
  parseFloat: parseFloat,
};
sandbox.window.document = documentStub;
sandbox.globalThis = sandbox;

const codigo = fs.readFileSync(APP_JS, "utf8");
vm.createContext(sandbox);

let fallos = [];
try {
  vm.runInContext(codigo, sandbox, { filename: "app.js" });
} catch (e) {
  fallos.push("app.js lanzo una excepcion al cargar: " + e.message);
}

// Esperar a que se resuelvan las promesas del fetch/cargar
setTimeout(() => {
  const filasLate = htmlDe("late-body");
  const filasOk = htmlDe("ok-body");

  if (erroresConsola.length) {
    fallos.push("console.error durante el render: " + erroresConsola.join(" | "));
  }
  if (!filasLate || !filasLate.includes("Tablero Lento")) {
    fallos.push("la tabla 'late-body' no pinto el tablero Demorado (render roto o vacio)");
  }
  if (!filasOk || !filasOk.includes("Tablero Al Dia")) {
    fallos.push("la tabla 'ok-body' no pinto el tablero OK (render roto o vacio)");
  }
  // Ojo: "Advertencia" cuenta como tablero que REQUIERE ATENCION (ESTADOS_LATE
  // incluye Demorado, Error y Advertencia), asi que va a late-body, no a ok-body.
  if (!filasLate || !filasLate.includes("Tablero Aviso")) {
    fallos.push("la tabla 'late-body' no pinto el tablero en Advertencia");
  }
  // KPIs: Demorado=1, Advertencia=1, Al dia=1, Total=3
  const kpis = [el("kpi-demorado").textContent, el("kpi-advertencia").textContent, el("kpi-aldia").textContent, el("kpi-total").textContent].join("/");
  if (kpis !== "1/1/1/3") {
    fallos.push("KPIs incorrectos: se esperaba 1/1/1/3 y salio " + kpis);
  }
  // Contadores de seccion: sin la clase 'empty-row' ni ceros falsos
  if (el("late-count").textContent !== "2") {
    fallos.push("el contador de 'Requieren atencion' deberia ser 2 y fue " + el("late-count").textContent);
  }

  if (fallos.length) {
    console.error("FALLO js_smoke:");
    for (const f of fallos) console.error("  - " + f);
    process.exit(1);
  }
  console.log("OK js_smoke: render completo, KPIs 1/1/1/3, tablas pintadas.");
  process.exit(0);
}, 0);
