# Plan de Rediseño — MonitorTableros (resiliencia + confianza)

> **For Hermes:** Implementar con `subagent-driven-development` (un subagente por tarea,
> revisión de spec y luego de calidad antes de pasar a la siguiente). Cada tarea ≤ 5 min.

**Goal:** Reestructurar el monitor de frescura de Power BI para que **no se rompa en silencio
nunca más** y para poder **confiar en cada actualización** que muestra, sin perder la vista
actual (que ya está aprobada).

**Architecture:** Se conserva la arquitectura viva v2 (2 contenedores Docker sobre una imagen,
FastAPI `:8070` + scheduler, frontend HTML/CSS/JS vanilla, persistencia en JSON en disco).
Se le **superponen tres capas nuevas**: (1) autenticación no-humana autoestable, (2) auto-reparación
y reintentos, (3) auto-vigilancia con alertas + salud honesta expuesta en la UI.

**Tech Stack:** Python 3.12, MSAL, requests/urllib3, FastAPI, uvicorn, Docker Compose,
Telegram Bot API. Sin base de datos, sin frameworks de frontend.

---

## Decisiones tomadas (Emmanuel, 06/10/2026)

1. **Autenticación:** Service Principal con `client_secret`, **sobre la app Azure EXISTENTE**
   `DashboardControl-Monitor` (client_id `13264966-13d3-46a7-925d-6b15f2d80f1a`).
   **NO se crea una app nueva.** Solo se le agregan permiso de APLICACIÓN + consentimiento
   + un client secret.
2. **Alertas:** Telegram (bot `@up_verdugo_bot`).
3. **Alcance:** los 4 pilares, por fases (F0 → F1 → F2 → F3 → F4).
4. **Rama:** todo en `feature/resiliencia-monitor` (nunca directo en `main`/`master`).
5. **Intocable:** la vista/diseño actual del dashboard. Se le agrega una franja de salud,
   no se rediseña.

## Contexto / estado al 06/10/2026

- **F0 (reanimar) YA HECHO:** device flow re-ejecutado; `token_cache.bin` regenerado;
  corrida real 21 tableros / 0 errores. Producción reportando datos de HOY.
- Repo local: `C:\Desarrollos BI\Reportes_Epem_data\1 - Reportes\MonitorTablero`
- Servidor: `192.168.0.95` (`vm-hermes`), `/home/vm-hermes/MonitorTableros`
- Remoto: `grupoepem-bi-team/MonitorTablero` (en el 95 la rama se llama `master`)
- Commit base: `1d19060`
- Vault SSH: `~/.hermes/vault/ssh_192.168.0.95.json` (Windows sin sshpass → usar `paramiko`)

### Causas raíz a eliminar

| # | Causa | Efecto | Pilar que la mata |
|---|-------|--------|-------------------|
| 1 | `src/auth.py::obtener_token()` **nunca** persiste el cache renovado | refresh caduca a 90 d y muere en silencio | P1+P2 |
| 2 | Dependencia de login **humano** (device flow) | nadie re-loguea → 2 semanas ciego | P1 |
| 3 | **Cero alertas** (NTFY en `.env` pero `config.py` no lo lee; no hay módulo) | nadie se entera | P3 |
| 4 | **Healthcheck falso** (valida el proceso/JSON viejo, no la última corrida) | "healthy" con pipeline muerto | P4 |
| 5 | UI dice "En vivo" aunque los datos estén congelados | falsa confianza | P4 |

---

# ═══════════════════════════════════════════════════════════════════════════
# ESTADO DE EJECUCIÓN (actualizado 06/10/2026)
# ═══════════════════════════════════════════════════════════════════════════
#
# ✔ F0 — REANIMAR (HECHO): device flow re-ejecutado en el 95; token_cache.bin
#   regenerado; corrida real 21 tableros / 0 errores. Producción reportando hoy.
#
# ✔ F1 — AUTH (HECHO, commit 0f2c1cd): config SP + auth con modo Service Principal
#   / fallback device flow + FIX DEL BUG DE RAÍZ (persistir el token cache).
#   5 tests. PENDIENTE ACTIVAR: cargar AZURE_CLIENT_SECRET en el .env del 95
#   (requiere habilitar app-only en la app existente, Tarea 1.0). Sin el secret,
#   sigue en device flow — seguro, no rompe.
#
# ✔ F2 — REINTENTOS (HECHO, commit 2ff554a): backoff ante timeout/red y 429/5xx;
#   renovación de token ante 401. 5 tests.
#
# ✔ F4 — SALUD HONESTA (HECHO, commit 7c2a07b): src/salud.py, GET /healthz que
#   valida la ÚLTIMA CORRIDA, healthchecks reales en docker-compose/Dockerfile,
#   franja de salud + badge honesto en la UI (diseño intacto). 12 tests.
#   Verificado con prueba de humo real (200/503/503 en los 3 casos).
#
# ⏸ F3 — ALERTAS TELEGRAM: EN PAUSA por decisión de Emmanuel (06/10).
#   Especificada abajo (Tareas 3.1–3.4). No bloquea F1/F2/F4.
#
# ☐ F5 — DOCS: actualizar README.md / MAPA_PROYECTO.md (describen la gen vieja).
# ✔ DEPLOY al 95 (HECHO 06/10): rama feature/resiliencia-monitor checkouteada y corriendo
#   (commit 113bf8b). Imágenes reconstruidas, 2 contenedores healthy, corrida real
#   21 tableros / 0 errores, /healthz 200. Prueba de caos OK (/healthz -> 503 al simular
#   fallo). Fix del build: docker-compose platforms solo linux/amd64 (el 95 no tiene qemu).
#
# Suite: 214 passed, 4 skipped (base 190 + 24 nuevos).
#
# ═══════════════════════════════════════════════════════════════════════════

# FASE 1 — Autenticación que no caduca ni se rompe

## Tarea 1.0 (MANUAL, la hace Emmanuel o el admin de Azure) — habilitar app-only en la app existente

**Objetivo:** que la app `DashboardControl-Monitor` pueda pedir token **sin usuario**.

En Azure Portal → App registrations → *DashboardControl-Monitor* → API permissions:
1. Add a permission → **Power BI Service** → **Application permissions** (¡no Delegated!) →
   marcar `Dataset.Read.All` → Add permissions.
2. Click **Grant admin consent for GRUPOIDEM** (queda con el tilde verde).

En Power BI Admin portal → **Tenant settings**:
3. Buscar **"Service principals can use Power BI APIs"** → Enabled
   (idealmente *Enabled for a specific security group* que contenga al SP).

En Power BI (app web) → cada uno de los **3 workspaces** monitoreados
(`8ac545a2…`, `a6474caa…`, `a1839600…`) → **Access** → agregar el SP como **Member**.

En Azure → Certificates & secrets:
4. **New client secret** → copiar el **Value** (se muestra una sola vez) → expiración 24 meses.
5. Anotar: `AZURE_TENANT_ID=655b856c-39c2-4438-9d98-b375b84019a9`,
   `AZURE_CLIENT_ID=13264966-13d3-46a7-925d-6b15f2d80f1a`, `AZURE_CLIENT_SECRET=<value>`.

**Verificación (Tarea 1.0b, la hace Beru):** probar el client-credentials flow contra Power BI
y confirmar que devuelve un `access_token` y que `executeQueries` responde. Si falla, casi
siempre es el tenant setting (paso 3) o el SP sin acceso al workspace (paso 4).

## Tarea 1.1 — Agregar configuración de Service Principal a `src/config.py`

**Objective:** exponer las credenciales SP opcionales sin romper el modo actual.

**Files:**
- Modify: `src/config.py` (sección Autenticación)

**Code:**
```python
AZURE_TENANT_ID = os.environ.get("AZURE_TENANT_ID", "").strip()
AZURE_CLIENT_SECRET = os.environ.get("AZURE_CLIENT_SECRET", "").strip()

# Modo de autenticación: "service_principal" si hay secret, si no "device_flow".
AUTH_MODE = "service_principal" if AZURE_CLIENT_SECRET else "device_flow"

# Scopes para client-credentials (app-only): .default va SOBRE el recurso.
POWERBI_SCOPE = "https://analysis.windows.net/powerbi/api/.default"
```

**Step: Run** `python -c "from src import config; print(config.AUTH_MODE)"`
**Expected:** `device_flow` (aún sin secret; no rompe nada).

**Step: Commit** `feat(auth): config para Service Principal opcional`

## Tarea 1.2 — `obtener_token()` con modo SP + fallback

**Objective:** obtener token app-only cuando haya secret; conservar el device flow como fallback.

**Files:**
- Modify: `src/auth.py`
- Test: `tests/test_auth.py` (crear)

**Step 1: test que falla**
```python
# tests/test_auth.py
import src.auth as auth
from src import config

def test_modo_sp_usa_confidential_client(monkeypatch):
    monkeypatch.setattr(config, "AUTH_MODE", "service_principal")
    monkeypatch.setattr(config, "AZURE_CLIENT_SECRET", "x")
    llamado = {}
    class FakeApp:
        def __init__(self, *a, **k): pasado = (a, k)
        def acquire_token_silent(self, scopes, account=None): return {"access_token": "T"}
    monkeypatch.setattr(auth.msal, "ConfidentialClientApplication", FakeApp)
    assert auth.obtener_token() == "T"
```

**Step 2: Run** `python -m pytest tests/test_auth.py -v` → FAIL (`ConfidentialClientApplication` no existe en auth).

**Step 3: implementación mínima en `src/auth.py`**
```python
from msal import ConfidentialClientApplication, PublicClientApplication, SerializableTokenCache

def _obtener_token_service_principal() -> str:
    """Token app-only con las credenciales del Service Principal (sin usuario)."""
    app = ConfidentialClientApplication(
        client_id=config.CLIENT_ID,
        client_credential=config.AZURE_CLIENT_SECRET,
        authority=config.AUTHORITY,
    )
    result = app.acquire_token_silent([config.POWERBI_SCOPE], account=None) \
             or app.acquire_token_for_client(scopes=[config.POWERBI_SCOPE])
    if result and "access_token" in result:
        return result["access_token"]
    raise RuntimeError(f"Service Principal sin token: {result.get('error_description', result)}")


def obtener_token() -> str:
    if config.AUTH_MODE == "service_principal":
        return _obtener_token_service_principal()
    return _obtener_token_device_flow()   # ← la lógica actual, renombrada
```

**Step 4: Run** `python -m pytest tests/test_auth.py -v` → PASS.

**Step 5: Commit** `feat(auth): modo Service Principal con fallback a device flow`

## Tarea 1.3 — **EL FIX DEL BUG DE RAÍZ:** persistir el cache en el fallback

**Objective:** que el device-flow guarde el refresh renovado en cada corrida (hoy no lo hace).

**Files:** Modify `src/auth.py` (`_obtener_token_device_flow`)

**Code:**
```python
        result = app.acquire_token_silent(config.SCOPES, account=accounts[0])
        if result and "access_token" in result:
            if cache.has_state_changed:          # ← ESTO FALTABA
                with open(config.CACHE_FILE, "w", encoding="utf-8") as f:
                    f.write(cache.serialize())
            return result["access_token"]
```

**Test:** `test_device_flow_persiste_cache` — simular `has_state_changed=True` y assert que el
archivo se escribió (`tmp_path` con `monkeypatch` de `config.CACHE_FILE`).
**Run** `python -m pytest tests/test_auth.py -v` → PASS. **Commit** `fix(auth): persistir el token cache renovado (bug raiz)`

---

# FASE 2 — Auto-reparación y reintentos

## Tarea 2.1 — Sesión HTTP con reintentos y backoff

**Objective:** que un timeout/5xx transitorio de Power BI no marque el tablero en Error.

**Files:** Modify `src/powerbi.py`; Test `tests/test_powerbi.py`

**Code (arriba de `consultar_tablero`):**
```python
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

def _sesion_con_reintentos() -> requests.Session:
    s = requests.Session()
    r = Retry(total=3, backoff_factor=1.0, status_forcelist=(429, 500, 502, 503, 504),
              allowed_methods=frozenset(["POST"]))
    s.mount("https://", HTTPAdapter(max_retries=r))
    return s
```
Usar `_sesion_con_reintentos().post(...)` en `consultar_tablero`.

**Test:** mock de `requests.Session.post` que falla 2 veces con 503 y luego 200 → assert OK.
**Run** `python -m pytest tests/test_powerbi.py -v`. **Commit** `feat(powerbi): reintentos con backoff`

## Tarea 2.2 — Reintento por token vencido a mitad de corrida (401)

**Objective:** si un tablero recibe 401, renovar token y reintentar una vez.

**Files:** Modify `src/powerbi.py` (`_procesar_un_tablero`) — pasar una *factory* de token en
vez del string, y ante `HTTPError 401` pedir token nuevo (`obtener_token()`) y repetir.

**Test:** mock 401 → 200 con token nuevo → assert OK y 2 llamadas.
**Run** `pytest tests/test_powerbi.py -v`. **Commit** `feat(powerbi): renovar token ante 401`

---

# FASE 3 — Auto-vigilancia + alerta por Telegram

## Tarea 3.1 — Módulo de notificación Telegram

**Objective:** poder mandar un mensaje al Telegram de Emmanuel.

**Files:** Create `src/notificaciones.py`; Test `tests/test_notificaciones.py`
Config nueva en `src/config.py`:
```python
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
```
**Code:**
```python
def enviar_telegram(texto: str) -> bool:
    """Manda un mensaje al chat configurado. True si se envio."""
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        return False
    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
    r = requests.post(url, json={"chat_id": config.TELEGRAM_CHAT_ID,
                                 "text": texto, "parse_mode": "HTML"}, timeout=10)
    return r.status_code == 200
```
**Verificación real:** en el 95, `python -c "from src.notificaciones import enviar_telegram; print(enviar_telegram('prueba monitor'))"`
y confirmar que llega al Telegram. (Secrets van al `.env` del 95 y al Vault, NUNCA al código.)

## Tarea 3.2 — Evaluador de salud con histéresis y anti-spam

**Objective:** decidir *cuándo* avisar, sin inundar.

**Files:** Create `src/salud.py`; Create `salud_estado.json` (state); Test `tests/test_salud.py`

**Reglas (definir con Emmanuel — ver Preguntas abiertas):**
- `caido`: 2 corridas consecutivas con `exito=false`, o sin corrida exitosa hace > 90 min.
- `datos_congelados`: monitor sano pero > 50 % de tableros `Demorado` (indicador de que el
  problema es de los ETL/PBI, no del monitor).
- **Transiciones**: se notifica al ENTRAR y al SALIR de un estado malo (recuperado), no en cada corrida.
- **Cooldown:** máximo 1 aviso por hora por estado (`salud_estado.json`).

**Test:** secuencia de metas (ok→ok→fallo→fallo) → assert que avisa una sola vez al segundo fallo.

## Tarea 3.3 — Enganchar la vigilancia al scheduler

**Objective:** que cada corrida evalúe salud y dispare alerta si corresponde.

**Files:** Modify `src/scheduler.py` (tras `ejecutar_corrida_con_manejo_error`):
```python
from src.salud import evaluar_y_notificar
...
ok, err = ejecutar_corrida_con_manejo_error()
evaluar_y_notificar(ok, err)     # ← evalúa, decide y (si toca) avisa por Telegram
```
**Commit** `feat(vigilancia): alertas de salud por Telegram`

## Tarea 3.4 — Alerta de frescura por tablero (> 1:20) — pedido de Emmanuel 06/10

**Objective:** avisar por Telegram cuando un tablero **concreto** supera **1 h 20 min (80 min)**
de retraso. Es distinto de la alerta de salud: acá el monitor está sano, pero un dataset/ETL
de Power BI dejó de refrescar.

**Reglas (definidas con Emmanuel 06/10):**
- **Alcance:** SOLO los tableros **críticos** (`critico=1`, hoy 8). Un cambio de `critico` en el
  CSV altera automáticamente a quién vigila.
- **Umbral:** 1 h 20 min (**80 min**), default `ALERTA_RETRASO_MIN=80` (configurable por `.env`
  y, opcional, por tablero en el CSV con `umbral_alerta_min`).
- **Cadencia de detección:** el scheduler baja de **30 → 5 min** (`SCHEDULER_INTERVAL_MIN=5`).
- **Aviso al cruzar:** mensaje apenas un crítico supera 80 min (transición sano→atrasado).
- **Recordatorio:** mientras siga atrasado, recordar **cada 30 min** (no cada 5).
- **Recuperación:** avisar cuando el tablero baja de 80 min.
- **Agrupación:** si hay **varios** críticos atrasados → UN mensaje resumen agrupado.
  Si hay **uno solo** → mensaje individual.

**Efecto colateral a ajustar:** `HISTORICO_MAX_CORRIDAS=1008` estaba pensado para 30 min
(7 días). Con 5 min son ~3,5 días. Subir a `2016` para conservar 7 días.

**Files:**
- Create: `src/alertas_frescura.py` — evalúa el df de la corrida contra el estado anterior y
  decide qué avisos mandar (usa `src/notificaciones.enviar_telegram`).
- State: `alertas_frescura_estado.json` — último estado conocido por tablero + timestamps de aviso
  (para el recordatorio de 30 min y el cruce/recovery).
- Modify: `src/scheduler.py` (engancha tras la corrida, pasando el df).
- Modify: `.env` del 95 (`SCHEDULER_INTERVAL_MIN=5`, `HISTORICO_MAX_CORRIDAS=2016`).
- Test: `tests/test_alertas_frescura.py`.

**Test:** secuencia de corridas simuladas con retrasos [70, 85, 90, 110, 40] para un crítico →
assert: avisa al cruzar 85; NO repite a los 5 min; repite a los 30 min; avisa recovery a los 40;
y que un tablero NO crítico nunca dispare.

**Verificación real:** en el 95, forzar la alerta con un tablero de prueba y confirmar que
llega el mensaje al Telegram de Emmanuel (cruce, recordatorio y recuperación).

**Commit** `feat(alertas): aviso Telegram cuando un tablero critico supera 1:20 de retraso`

---

# FASE 4 — Confianza en el dato (healthcheck real + UI honesta)

## Tarea 4.1 — Endpoint `/healthz` que valida la ÚLTIMA CORRIDA

**Objective:** que Docker sepa si el pipeline está sano de verdad.

**Files:** Modify `frontend/server.py`
```python
@app.get("/healthz")
async def healthz():
    meta = leer_meta_corrida()
    edad_min = _edad_min(meta.get("ultima_corrida_fin"))
    sano = bool(meta.get("exito")) and edad_min is not None and edad_min < 90
    if not sano:
        raise HTTPException(status_code=503, detail={
            "exito": meta.get("exito"), "edad_min": edad_min, "error": meta.get("error")})
    return {"sano": True, "edad_min": edad_min}
```
**Files:** Modify `docker-compose.yml` → healthcheck del frontend a `http://localhost:8070/healthz`.
**Verificación:** `docker compose ps` debe mostrar `healthy` **solo** cuando la corrida es fresca;
forzar un fallo y comprobar que pasa a `unhealthy`.

## Tarea 4.2 — Healthcheck real del scheduler

**Objective:** el scheduler escriba un **latido** y el healthcheck lo valide.

**Files:** Modify `src/scheduler.py` (escribir `corrida_latido.json` con `ts` tras cada iteración)
y `docker-compose.yml` (healthcheck que lee ese archivo y valida frescura `< 35 min`).

## Tarea 4.3 — Franja de salud honesta en la UI (sin tocar el diseño)

**Objective:** decir la verdad cuando el monitor esté caído o los datos viejos.

**Files:** Modify `frontend/templates/index.html` (un `<div id="salud-strip">` arriba de la tabla),
`frontend/static/app.js` (pintarla desde `meta`), `frontend/static/style.css` (estilos).
**Comportamiento:**
- Todo bien → franja verde discreta: `Monitor OK · última corrida hace 12 min`.
- Corrida falló → franja ROJA: `⚠ Monitor caído: la última corrida falló. Mostrando datos del <fecha>`.
- Datos viejos → franja ÁMBAR: `Última corrida hace 2 h — los datos pueden estar desactualizados`.
**Verificación:** forzar `corrida_monitor_meta.json` con `exito=false` falso y ver la franja roja.
**Regla:** NO cambiar grillas, colores ni estructura de la vista existente; solo agregar la franja.

---

# Archivos que se tocan (resumen)

| Archivo | Fase | Acción |
|---------|------|--------|
| `src/config.py` | 1,3 | +vars SP y Telegram |
| `src/auth.py` | 1 | +modo SP, +fix persistir cache |
| `src/powerbi.py` | 2 | +reintentos, +401→refresh |
| `src/notificaciones.py` | 3 | **nuevo** |
| `src/salud.py` | 3 | **nuevo** |
| `src/scheduler.py` | 3,4 | +vigilancia, +latido |
| `frontend/server.py` | 4 | +`/healthz` |
| `frontend/templates/index.html` | 4 | +franja salud |
| `frontend/static/app.js` | 4 | +pintar franja |
| `frontend/static/style.css` | 4 | +estilos franja |
| `docker-compose.yml` | 4 | healthchecks reales |
| `tests/test_auth.py`, `test_powerbi.py`, `test_salud.py`, `test_notificaciones.py` | 1-3 | **nuevos** |
| `.env` (95, no versionado) | 1,3 | +secret SP + Telegram |
| Vault | 1,3 | guardar secret SP + token Telegram |
| `README.md`, `MAPA_PROYECTO.md` | 5 | actualizar (hoy describen la gen vieja) |

# Validación / pruebas (puertas de calidad)

1. **Unitarias:** `python -m pytest tests/ -v` → todo verde (base 140 + nuevos).
2. **Integración real (en el 95):**
   - Corrida manual OK: `docker exec -w /app dashboardcontrol-scheduler python -m src.worker`
   - `corrida_monitor_meta.json` con `exito:true`.
   - `curl http://192.168.0.95:8070/api/todos` → datos de hoy.
   - `curl http://192.168.0.95:8070/healthz` → 200.
3. **Prueba de caos (lo importante):**
   - Romper el token a propósito → confirmar que **llega la alerta a Telegram** y que
     `/healthz` da 503 y la UI muestra la franja roja.
   - Simular PBI caído → confirmar reintentos y que no se pierden los datos previos.
4. **Reversión:** `git revert` del commit; el sistema debe seguir operando con el estado previo.

# Riesgos, tradeoffs y preguntas abiertas

**Riesgos**
- **SP + Power BI:** el modo app-only depende del tenant setting (Tarea 1.0 p3) y de que el SP
  esté en cada workspace. Si el admin no lo habilita, hay que quedarse en device flow (con P2 y P3).
- **Secret que caduca:** el client secret se vence (máx 24 meses). Mitigación: cargar la fecha en
  `salud_estado.json` y **alertar 30 días antes** por Telegram (misma tubería de P3).
- **Ejecución con subagentes sobre producción:** todo cambio va a rama; el deploy al 95 es manual
  y explícito, tras la revisión.

**Preguntas abiertas (responder antes de Fase 3)**
1. Umbral de "datos congelados": ¿> 50 % Demorado? ¿o > 2 tableros críticos Demorado?
2. ¿Además del aviso de caída, querés un **parte diario** (resumen 8:00) aunque todo esté OK?
3. ¿La franja de salud debe ser solo informativa o también con un botón "Forzar corrida"?

**Orden de ejecución:** F1 (auth) → F2 (reintentos) → F4 (salud/UI) → F5 (docs).
**F3 (alertas Telegram) QUEDA EN PAUSA** por decisión de Emmanuel (06/10/2026): se deja el aviso
por Telegram para más adelante. La Tarea 3.4 (aviso 1:20) y 3.1-3.3 se conservan especificadas
acá para retomarlas cuando se pida. El resto del plan (F1, F2, F4) NO depende de Telegram.

**Prioridad de ejecución sin Telegram (lo que más protege):**
1. **F1.3 — fix del bug de raíz** (persistir el token cache). Es el que evita la próxima caída
   silenciosa. No necesita Azure ni Telegram.
2. **F2 — reintentos** (un timeout no debe marcar Error).
3. **F4 — healthcheck real + franja honesta en la UI** (que no vuelva a mentir "En vivo").
4. **F1.1/F1.2 — código del Service Principal** (queda listo para cuando Emmanuel cargue el
   secret; activa solo si `AZURE_CLIENT_SECRET` está presente).

Cada fase: código + tests + commit en `feature/resiliencia-monitor`, verificación en el 95, y
recién entonces la siguiente. F0 (reanimar) ya está completo.
