# Bitacora de incidentes — DashboardControl

Registro chronologico de errores, causas raiz y soluciones aplicadas.
Cada entrada debe tener: fecha, sintoma, causa, fix, archivos tocados.

---

## 2026-07-16 — Deploy al servidor Linux (192.168.0.95)

### Sintoma
El sistema corria en una PC con Windows. Se decidio migrar a un servidor Linux
en la red local para que corra 24/7 sin depender de una PC encendida.

### Configuracion del servidor
- IP: 192.168.0.95
- Usuario: vm-hermes
- OS: Linux
- Python: 3.14.4
- Puerto del dashboard: 8070

### Archivos de deploy creados
- `requirements.txt` — dependencias minimas (pandas, requests, msal, fastapi,
  uvicorn, python-dotenv)
- `deploy/deploy.sh` — script de deploy via rsync + SSH desde la PC local
- `deploy/first_auth.sh` — script de primera autenticacion (device flow) en
  el servidor
- `deploy/dashboardcontrol-scheduler.service` — servicio de systemd para el
  scheduler (corre cada 30 min)
- `deploy/dashboardcontrol-frontend.service` — servicio de systemd para el
  frontend (uvicorn en puerto 8070)

### Procedimiento de deploy
1. Desde la PC local: `bash deploy/deploy.sh` (copia archivos, crea venv,
   instala deps, instala servicios systemd)
2. En el servidor: `cd /opt/dashboardcontrol && bash deploy/first_auth.sh`
   (device flow de Azure AD, genera token_cache.bin, inicia servicios)
3. Dashboard disponible en `http://192.168.0.95:8070`

### Cambios adicionales
- ngrok eliminado (no se necesita, el servidor esta en la red local)
- `DashboardControl.bat` simplificado (solo scheduler + frontend, sin ngrok)
- `.gitignore` actualizado: logs/, device_flow_info.txt, mobile_push_tokens.json

---

## 2026-07-16 — Corrida del monitor con 23/23 tableros en Error

### Sintoma
La corrida del 15/07 16:16 marco los 23 tableros en estado "Error" con
`400 Client Error: Bad Request` en todas las consultas a `executeQueries`.
La corrida anterior del 14/07 17:08 habia funcionado correctamente.

### Causas raiz (4 bugs encadenados)

#### Bug 1: DAX mal formado — comilla simple de cierre incorrecta
- **Archivo:** `src/powerbi.py:45`
- **DAX generado (incorrecto):** `MAX('tabla'[col]))`  ← faltaba `']` despues de la columna
- **DAX correcto:** `MAX('tabla'[col]))`
- **Sintoma en log:** `Invalid token, Line 1, Offset 64, [Actualizado_al)).`
- **Causa:** El f-string no incluia el corchete de cierre de la columna antes del parentesis.

#### Bug 2: CSV leido sin separador
- **Archivo:** `src/worker.py:54`
- **Problema:** `pd.read_csv(path_csv)` usa `,` por defecto, pero el CSV usa `;`
- **Sintoma:** `KeyError: 'activo'` — pandas no encontraba ninguna columna
- **Fix:** `pd.read_csv(path_csv, sep=";")`

#### Bug 3: Typo en funcion helper
- **Archivo:** `src/estados.py:61`
- **Problema:** `_lear_umbral` (sin la segunda `e`) en vez de `_leer_umbral`
- **Sintoma:** `NameError: name '_lear_umbral' is not defined` — todos los tableros
  caian en estado Error aunque la consulta a Power BI hubiera funcionado
- **Fix:** Corregir el nombre de la funcion a `_leer_umbral`

#### Bug 4: App de Azure configurada como cliente confidencial
- **Archivo:** Azure Portal — App registration `13264966...`
- **Problema:** `allowPublicClient` estaba en `null` (no `true`)
- **Sintoma:** `AADSTS7000218: The request body must contain the following
  parameter: 'client_assertion' or 'client_secret'.` al intentar el device flow
- **Causa:** La app fue creada como cliente confidencial por defecto. El device
  flow requiere cliente publico.
- **Fix:** Editar el manifest en Azure Portal: `"allowPublicClient": true`

#### Bug 5: token_cache.bin inexistente
- **Problema:** No habia token cache. El refresh token del CLIENT_ID viejo
  (`04f0c124...`) era invalido para el CLIENT_ID nuevo (`13264966...`).
- **Sintoma:** `RuntimeError: No se pudo obtener token silencioso.`
- **Fix:** Ejecutar `python -m scripts.auth_step1` (device flow interactivo)
  con el nuevo CLIENT_ID para generar `token_cache.bin`

### Resolucion
1. Editar manifest en Azure Portal (`allowPublicClient: true`)
2. Re-autenticar con device flow (`scripts/auth_step1`)
3. Fix DAX en `src/powerbi.py:45`
4. Fix separador CSV en `src/worker.py:54`
5. Fix typo en `src/estados.py:61`
6. Corrida exitosa: 23 tableros, 4.7s, 0 errores

### Estado post-fix
- 8 Demorados, 6 Advertencia, 9 OK
- Token con permisos minimos: `Dataset.Read.All`, `Workspace.Read.All`
- Usuario: AlanChaparro@GRUPOIDEM.onmicrosoft.com
- App: 13264966-13d3-46a7-925d-6b15f2d80f1a (DashboardControl-Monitor)

### Lecciones
- El error `400 Bad Request` de executeQueries puede enmascarar tanto un DAX
  mal formado como un token invalido. Siempre capturar el body del response
  para ver el mensaje real de Power BI.
- El typo `_lear_umbral` paso desapercibido porque el worker captura todas las
  excepciones en `_procesar_un_tablero` y las convierte en estado Error. La
  corrida "termina OK" pero todos los tableros quedan en Error. Convendria
  loguear los errores no esperados (no de Power BI) por separado.
- Al cambiar CLIENT_ID, el token_cache.bin viejo queda invalido. Hay que
  borrarlo y re-autenticar.

---

## 2026-07-16 — Deploy al servidor Linux (192.168.0.95)

### Sintoma
El sistema corria en una PC con Windows. Se decidio migrar a un servidor Linux
en la red local para que corra 24/7 sin depender de una PC encendida.

### Configuracion del servidor
- IP: 192.168.0.95
- Usuario: vm-hermes
- OS: Linux
- Python: 3.14.4
- Puerto del dashboard: 8070

### Archivos de deploy creados
- `requirements.txt` — dependencias minimas (pandas, requests, msal, fastapi,
  uvicorn, python-dotenv)
- `deploy/deploy.sh` — script de deploy via rsync + SSH desde la PC local
- `deploy/first_auth.sh` — script de primera autenticacion (device flow) en
  el servidor
- `deploy/dashboardcontrol-scheduler.service` — servicio de systemd para el
  scheduler (corre cada 30 min)
- `deploy/dashboardcontrol-frontend.service` — servicio de systemd para el
  frontend (uvicorn en puerto 8070)

### Procedimiento de deploy
1. Desde la PC local: `bash deploy/deploy.sh` (copia archivos, crea venv,
   instala deps, instala servicios systemd)
2. En el servidor: `cd /opt/dashboardcontrol && bash deploy/first_auth.sh`
   (device flow de Azure AD, genera token_cache.bin, inicia servicios)
3. Dashboard disponible en `http://192.168.0.95:8070`

### Cambios adicionales
- ngrok eliminado (no se necesita, el servidor esta en la red local)
- `DashboardControl.bat` simplificado (solo scheduler + frontend, sin ngrok)
- `.gitignore` actualizado: logs/, device_flow_info.txt, mobile_push_tokens.json

---

## 2026-07-15 — Migracion de Streamlit a FastAPI (frontend nuevo)

### Sintoma
Refactor completo del frontend: se paso de `app.py` (Streamlit, 2505 lineas)
a un server FastAPI en `frontend/server.py` con HTML/JS/CSS estatico.

### Cambios
- `frontend/server.py` — FastAPI con endpoints `/api/todos`, `/api/corrida`,
  `/api/reactor-svg`
- `frontend/templates/index.html` — HTML estatico
- `frontend/static/app.js` — Logica del frontend en JS vanilla
- `frontend/static/style.css` — Estilos
- `frontend/components/reactor_svg.py` — Generador de SVG del reactor visual
- `src/` — Modulos nuevos: auth, config, powerbi, estados, cambios,
  persistencia, worker

### Estado
Funcional. El server corre con `uvicorn frontend.server:app --port 8501`.

---

## 2026-07-16 — Deploy al servidor Linux (192.168.0.95)

### Sintoma
El sistema corria en una PC con Windows. Se decidio migrar a un servidor Linux
en la red local para que corra 24/7 sin depender de una PC encendida.

### Configuracion del servidor
- IP: 192.168.0.95
- Usuario: vm-hermes
- OS: Linux
- Python: 3.14.4
- Puerto del dashboard: 8070

### Archivos de deploy creados
- `requirements.txt` — dependencias minimas (pandas, requests, msal, fastapi,
  uvicorn, python-dotenv)
- `deploy/deploy.sh` — script de deploy via rsync + SSH desde la PC local
- `deploy/first_auth.sh` — script de primera autenticacion (device flow) en
  el servidor
- `deploy/dashboardcontrol-scheduler.service` — servicio de systemd para el
  scheduler (corre cada 30 min)
- `deploy/dashboardcontrol-frontend.service` — servicio de systemd para el
  frontend (uvicorn en puerto 8070)

### Procedimiento de deploy
1. Desde la PC local: `bash deploy/deploy.sh` (copia archivos, crea venv,
   instala deps, instala servicios systemd)
2. En el servidor: `cd /opt/dashboardcontrol && bash deploy/first_auth.sh`
   (device flow de Azure AD, genera token_cache.bin, inicia servicios)
3. Dashboard disponible en `http://192.168.0.95:8070`

### Cambios adicionales
- ngrok eliminado (no se necesita, el servidor esta en la red local)
- `DashboardControl.bat` simplificado (solo scheduler + frontend, sin ngrok)
- `.gitignore` actualizado: logs/, device_flow_info.txt, mobile_push_tokens.json

---

## 2026-07-15 — Creacion de nueva app registration en Azure

### Sintoma
El CLIENT_ID viejo (`04f0c124-f2bc-4f59-8241-bf6df9866bbd`) no aparecia en
Azure Portal. Riesgo de que el refresh token dejara de funcionar.

### Accion
Se creo nueva app registration `DashboardControl-Monitor` con ID
`13264966-13d3-46a7-925d-6b15f2d80f1a` en tenant GRUPOIDEM
(`655b856c-39c2-4438-9d98-b375b84019a9`).

### Permisos configurados
- `Dataset.Read.All` (delegated)
- `Workspace.Read.All` (delegado)

### Pendiente
- Migrar a Service Principal (app sin usuario humano) para autonomia total
- Completar campos vacios en `.env`: `TENANT_ID`, `CLIENT_ID`, `CLIENT_SECRET`

---

## 2026-07-16 — Deploy al servidor Linux (192.168.0.95)

### Sintoma
El sistema corria en una PC con Windows. Se decidio migrar a un servidor Linux
en la red local para que corra 24/7 sin depender de una PC encendida.

### Configuracion del servidor
- IP: 192.168.0.95
- Usuario: vm-hermes
- OS: Linux
- Python: 3.14.4
- Puerto del dashboard: 8070

### Archivos de deploy creados
- `requirements.txt` — dependencias minimas (pandas, requests, msal, fastapi,
  uvicorn, python-dotenv)
- `deploy/deploy.sh` — script de deploy via rsync + SSH desde la PC local
- `deploy/first_auth.sh` — script de primera autenticacion (device flow) en
  el servidor
- `deploy/dashboardcontrol-scheduler.service` — servicio de systemd para el
  scheduler (corre cada 30 min)
- `deploy/dashboardcontrol-frontend.service` — servicio de systemd para el
  frontend (uvicorn en puerto 8070)

### Procedimiento de deploy
1. Desde la PC local: `bash deploy/deploy.sh` (copia archivos, crea venv,
   instala deps, instala servicios systemd)
2. En el servidor: `cd /opt/dashboardcontrol && bash deploy/first_auth.sh`
   (device flow de Azure AD, genera token_cache.bin, inicia servicios)
3. Dashboard disponible en `http://192.168.0.95:8070`

### Cambios adicionales
- ngrok eliminado (no se necesita, el servidor esta en la red local)
- `DashboardControl.bat` simplificado (solo scheduler + frontend, sin ngrok)
- `.gitignore` actualizado: logs/, device_flow_info.txt, mobile_push_tokens.json

---
## 2026-07-16 — Migracion a Docker + auditoria de codigo

### Sintoma
El sistema corria con systemd en el servidor Linux. Se decidio migrar a Docker
para facilitar el deploy y la portabilidad. Antes de migrar se hizo una
auditoria completa de codigo muerto, bugs silenciosos y seguridad.

### Auditoria — Codigo muerto eliminado
- `app.js`: Removida `initWeather()` (34 lineas) que buscaba IDs inexistentes
  en el HTML. El widget de clima fue removido del HTML pero el JS+CSS quedaron.
- `style.css`: Removidas 6 reglas CSS de `.widget--weather`.
- `Dockerfile` y `docker-compose.yml`: Movidos a `_legacy/` (no se usaban con
  systemd) y luego restaurados a la raiz al migrar a Docker.
- `.dockerignore`: Movido a `_legacy/` y luego restaurado.

### Auditoria — Bugs silenciosos corregidos
1. **Lock de concurrencia en `/api/corrida`** (`server.py`): Anadido
   `asyncio.Lock` para evitar corridas manuales simultaneas. Sin esto, dos
   workers en paralelo podian intercalar lineas en `historico_corridas.jsonl`
   y perder datos en el truncado. Si ya hay una corrida en curso, se
   rechaza con 409 Conflict.
2. **Referencia a `icon.png` inexistente** (`app.js`): Removido
   `icon: "/static/icon.png"` de `notificarTablero` (el archivo no existia).
3. **Fallback hardcodeado de CLIENT_ID** (`config.py`): Removido el valor
   `04f0c124-f2bc-4f59-8241-bf6df9866bbd` (app vieja con permisos excesivos
   ReadWrite.All). Ahora `config.py` raisea RuntimeError si no encuentra
   `AZURE_CLIENT_ID` en `.env`.

### Deploy Docker — Issues encontrados y corregidos

#### 1. NumPy X86_V2 no soportado
- **Sintoma**: `RuntimeError: NumPy was built with baseline optimizations
  (X86_V2) but your machine doesn't support: (X86_V2)`
- **Causa**: El CPU del servidor (192.168.0.95) es anterior a Haswell y no
  soporta las optimizaciones X86_V2 que NumPy >= 2.4 requiere.
- **Fix**: Fijado `numpy<2` (instala 1.26.4) y `pandas<3` (instala 2.3.3) en
  `requirements.txt`.

#### 2. os.replace falla sobre bind mounts de Docker
- **Sintoma**: `Errno 16: Device or resource busy` al guardar los JSONs
  de estado.
- **Causa**: `os.replace` (rename del sistema) no funciona sobre bind mounts
  de archivos individuales en Docker. Los JSONs estaban montados como
  volumenes de archivo (no de directorio).
- **Fix**: Cambiado `os.replace(tmp, path)` por `shutil.copy(tmp, path)` +
  `os.remove(tmp)` en `persistencia.py` (funciones `_atomic_write_json` y
  `_truncar_historico`).

#### 3. Timezone del container en UTC
- **Sintoma**: Los retrasos se calculaban 3h de mas. Todos los tableros
  aparecian como "Demorado" incluso los que estaban actualizados.
- **Causa**: El container Docker corria en UTC mientras que Power BI devuelve
  las fechas en hora local (-03). Al calcular
  `hora_consulta - ultima_actualizacion`, sumaba 3h.
- **Fix**: Anadido `TZ=America/Argentina/Buenos_Aires` en `environment` de
  ambos servicios en `docker-compose.yml`. Instalado `tzdata` en el
  `Dockerfile` con `apt-get install tzdata`.
- **Resultado**: 11 tableros pasaron de "Demorado" a "OK", 5 a "Advertencia",
  7 quedaron "Demorado" (reales).

### Configuracion final del deploy

| Componente | Valor |
|------------|-------|
| Servidor | 192.168.0.95 |
| Puerto | 8070 |
| Usuario SSH | vm-hermes |
| Directorio | /home/vm-hermes/MonitorTableros |
| Timezone | America/Argentina/Buenos_Aires |
| Scheduler interval | 30 min (SCHEDULER_INTERVAL_MIN=30) |
| NumPy | 1.26.4 (<2) |
| Pandas | 2.3.3 (<3) |

### Archivos modificados

| Archivo | Cambio |
|---------|--------|
| `frontend/static/app.js` | Removida `initWeather()`, removido `icon.png` |
| `frontend/static/style.css` | Removidas reglas de `.widget--weather` |
| `frontend/server.py` | Anadido `asyncio.Lock` en `/api/corrida` |
| `src/config.py` | Removido fallback hardcodeado de CLIENT_ID |
| `src/persistencia.py` | `os.replace` -> `shutil.copy` + `os.remove` |
| `requirements.txt` | Anadido `numpy<2`, cambiado `pandas>=2.0` a `pandas<3` |
| `Dockerfile` | Puerto 8070, instalado tzdata |
| `docker-compose.yml` | 2 servicios (frontend+scheduler), TZ=America/Argentina/Buenos_Aires |
| `.dockerignore` | Reescrito |
| `DEPLOY.md` | Reescrito con instrucciones Docker |
| `deploy/deploy.sh` | Parametrico (REMOTE_USER, REMOTE_HOST, etc.) |
| `deploy/first_auth.sh` | Parametrico, modo --remote |

### Estado final
- `dashboardcontrol-frontend`: Up (healthy), uvicorn en 0.0.0.0:8070
- `dashboardcontrol-scheduler`: Up, corre cada 30 min
- 23 tableros monitoreados: 11 OK, 5 Advertencia, 7 Demorado
- Dashboard accesible en http://192.168.0.95:8070

---
