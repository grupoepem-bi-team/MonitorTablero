# Reporte de estado — Dashboard Control

**Fecha:** 15/07/2026  
**Proyecto:** `C:\Desarrollos BI\dashboardcontrol\dashboardcontrol`  
**Propósito:** Monitorear la actualización de 23 tableros de Power BI y alertar si se atrasan

---

## 1. Resumen ejecutivo

El sistema **funciona**. La última corrida exitosa fue el 14/07/2026 a las 17:08 (23 tableros consultados en 6 segundos, 4 cambios de estado detectados). Sin embargo, hay **5 problemas críticos** de seguridad y configuración que necesitan atención, y varios menores.

| Severidad | Cantidad | Descripción |
|-----------|----------|-------------|
| 🔴 Crítico | 3 | Token sobrepermissivo, app no encontrada en Azure, .env con campos vacíos |
| 🟡 Medio | 4 | ngrok sin configurar, Expo Push sin tokens reales, columnas CSV ignoradas, CSS muerto |
| 🟢 Bajo | 2 | Código duplicado en scripts, wrapper trivial mobile_push_api.py |

---

## 2. Cómo funciona el sistema (resumen técnico)

```
config_tableros.csv (23 tableros)
        │
        ▼
monitor_worker.py → monitor_common.py
        │
        ├── 1. Lee token_cache.bin → MSAL renueva token con Microsoft
        ├── 2. Por cada tablero (12 hilos en paralelo):
        │      POST a Power BI API → DAX: MAX(tabla[columna]) → datetime
        ├── 3. Calcula retraso: (ahora - última_actualización) en minutos
        ├── 4. Estado: OK ≤60min / Advertencia ≤80min / Demorado >80min / Error
        ├── 5. Compara con snapshot anterior → detecta cambios
        ├── 6. Si hay cambios → ntfy.sh + Expo Push (si están habilitados)
        └── 7. Guarda en 4 JSON locales (estado, snapshot, cambios, meta)
        
app.py (Streamlit) lee los JSON y muestra la UI
```

**Dato clave:** La "hora de actualización" no viene del servicio de Power BI. Viene de una **columna dentro de los datos** del dataset (ej: `conceptos_facturados[Actualizado_al]`), que los procesos ETL dejan registrada.

---

## 3. Estado actual de cada componente

### 3.1 Consulta a Power BI
| Aspecto | Estado | Detalle |
|---------|--------|---------|
| Funciona | ✅ | Última corrida: 14/07/2026 17:08, 23 tableros, 6s |
| Token | ⚠️ | Expirado el 18/06/2026, pero el refresh token sigue renovando |
| Usuario autenticado | Alan Chaparro | `AlanChaparro@GRUPOIDEM.onmicrosoft.com` |
| Tenant | GRUPOIDEM | `655b856c-39c2-4438-9d98-b375b84019a9` |
| Permisos del token | 🔴 | `Capacity.ReadWrite.All`, `Dataset.ReadWrite.All`, `Report.ReadWrite.All`, `Workspace.ReadWrite.All` — todos de escritura |

### 3.2 Configuración (config_tableros.csv)
| Aspecto | Estado | Detalle |
|---------|--------|---------|
| Tableros activos | 23 | Todos con `activo=1` |
| Críticos | 8 | `critico=1` |
| Workspaces | 3 | `8ac545a2...` (5 tableros), `a6474caa...` (16), `a1839600...` (2) |
| Columnas ignoradas | 🔴 | `frecuencia_objetivo_min` y `demorado_min` nunca se leen (umbrales hardcodeados en 60/80 min) |

### 3.3 Notificaciones
| Canal | Estado | Detalle |
|-------|--------|---------|
| ntfy.sh | ⏸️ Pausado | `push_enabled: false` (decisión del usuario desde la UI) |
| Expo Push | ⚠️ | `expo_push_enabled: true` pero solo hay 1 token de prueba deshabilitado |
| Dispositivos móviles reales | ❌ | Ninguno registrado |

### 3.4 Conectividad
| Componente | Estado | Detalle |
|------------|--------|---------|
| Streamlit | ✅ | Corre en puerto 8501 |
| ngrok | 🔴 | `ngrok.yml` tiene `TU_AUTHTOKEN` como placeholder |
| API registro móvil | ✅ | Puerto 8091, embebida en Streamlit |
| IP hardcodeada | ⚠️ | `192.168.0.43:8091` en `.env` |

### 3.5 Autenticación
| Aspecto | Estado | Detalle |
|---------|--------|---------|
| App registration en Azure | ❓ | `CLIENT_ID 04f0c124...` no aparece en el portal (según usuario) |
| CLIENT_ID hardcodeado | 🔴 | En 7 archivos del proyecto |
| .env con campos vacíos | 🔴 | `TENANT_ID=`, `CLIENT_ID=`, `CLIENT_SECRET=` vacíos (migración a SP incompleta) |
| token_cache.bin | ⚠️ | Última modificación 18/06/2026, funciona vía refresh token |

---

## 4. Hallazgos críticos (ordenados por prioridad)

### 🔴 1. Token con permisos excesivos (ReadWrite.All)
**Problema:** El token decodificado tiene permisos de lectura Y escritura en datasets, reports, workspaces y capacidades Premium. El código solo necesita lectura (`Dataset.Read.All`).

**Riesgo:** Si alguien roba `token_cache.bin` o modifica el código, podría borrar/modificar recursos de Power BI.

**Solución:** Crear nueva app registration con permisos mínimos o reducir permisos de la app existente.

---

### 🔴 2. App registration no encontrada en Azure
**Problema:** El `CLIENT_ID 04f0c124-f2bc-4f59-8241-bf6df9866bbd` no aparece en Azure Portal (según el usuario). Posibles causas:
- Fue creada en otro tenant
- Fue borrada
- El usuario no tiene permisos para verla (¿verificaste "All applications"?)

**Riesgo:** Si fue borrada, el refresh token va a dejar de funcionar en algún momento y el monitor se va a romper sin previo aviso.

**Solución:** Investigar dónde está la app, o crear una nueva y reemplazar el `CLIENT_ID` en el código.

---

### 🔴 3. .env con campos vacíos (migración incompleta)
**Problema:** El `.env` tiene `TENANT_ID=`, `CLIENT_ID=`, `CLIENT_SECRET=` vacíos. Alguien intentó migrar a Service Principal (app sin usuario humano) pero no lo terminó.

**Riesgo:** Confusión sobre qué credenciales se están usando. El código ignora estos campos (usa el hardcodeado), pero genera falsas expectativas.

**Solución:** Completar la migración a Service Principal o eliminar esos campos del `.env`.

---

### 🟡 4. ngrok sin configurar
**Problema:** `ngrok.yml` tiene `TU_AUTHTOKEN` como placeholder. `DashboardControl.bat` invoca ngrok pero fallaría.

**Solución:** Obtener un authtoken real de ngrok.com y reemplazarlo, o eliminar ngrok si no se usa.

---

### 🟡 5. Expo Push sin dispositivos reales
**Problema:** `mobile_push_tokens.json` solo tiene un token de prueba deshabilitado. Las notificaciones móviles no llegan a nadie.

**Solución:** Registrar un dispositivo real desde la app móvil (POST a `/api/mobile/register-push-token`).

---

### 🟡 6. Columnas del CSV ignoradas
**Problema:** `frecuencia_objetivo_min` y `demorado_min` del CSV nunca se leen. Los umbrales están hardcodeados en `monitor_common.py` (60/80 min).

**Solución:** O bien usar las columnas del CSV en el código, o bien eliminarlas del CSV para evitar confusión.

---

### 🟡 7. CSS muerto en app.py
**Problema:** Las clases `.dc-banner`, `.dc-banner__rail`, `.dc-banner__inner`, `.dc-banner--clear` están definidas pero nunca se generan en el HTML.

**Solución:** Eliminar ~60 líneas de CSS muerto.

---

### 🟢 8. Código duplicado en scripts de test
**Problema:** 7 scripts (`auth_test.py`, `test_login.py`, `list_datasets.py`, etc.) duplican el bloque de autenticación MSAL.

**Solución:** Centralizar en una función de `monitor_common.py` y reutilizar.

---

### 🟢 9. mobile_push_api.py es un wrapper trivial
**Problema:** 7 líneas que solo importan `main` de `mobile_push_server.py` y la ejecutan.

**Solución:** Redundante pero inofensivo. Se puede eliminar o dejar.

---

## 5. Estado de los tableros (última corrida 14/07/2026 17:08)

### Con problemas (8 tableros)
| Tablero | Estado | Retraso | Crítico |
|---------|--------|---------|---------|
| EERR_auto | Demorado | **540.435 min (~375 días)** | No |
| ODONTOLOGOS | Demorado | 6.168 min (~4 días) | No |
| Reporte ejecutivo | Demorado | 5.869 min (~4 días) | No |
| Nivel de Servicio Estética | Demorado | 289 min | **Sí** |
| Nivel de Servicio ODO | Demorado | 289 min | No |
| LTV | Demorado | 96 min | No |
| TAPO_DESEMBOLSOS | Advertencia | 76 min | No |
| LTV_Odontologia | Advertencia | 74 min | No |

### En OK (15 tableros)
Facturacion, Reporte Ventas, Seguimiento Cobranzas_, Seguimiento Cobranza - (COBRO BANCOS), TABLERO MEDICINA PREPAGA, TABLERO SERVICIOS, Tablero de Servicios Estética, Cobranzas Tratamientos, Corporativo, Denpro, Marcación Eme, Saldos pendientes, Servicios_Emergencia, Ventas por edad y genero, MLA

### Cambios detectados en la última corrida
1. Cobranzas Tratamientos: Advertencia → OK
2. Tablero de Servicios Estética: Demorado → OK
3. Seguimiento Cobranzas_: Error → OK
4. Seguimiento Cobranza - (COBRO BANCOS): Advertencia → OK

---

## 6. Plan de acción recomendado

### Prioridad 1 — Seguridad y autenticación
1. **Investigar la app de Azure** (¿está en otro tenant? ¿la creó otro admin?)
2. **Crear nueva app registration** con permisos mínimos: `Dataset.Read.All` + `Workspace.Read.All`
3. **Reemplazar CLIENT_ID** en los 7 archivos del proyecto
4. **Regenerar token_cache.bin** con `auth_test.py` usando la nueva app
5. **Eliminar campos vacíos** del `.env` o completar la migración a Service Principal

### Prioridad 2 — Conectividad
6. **Configurar ngrok** con un authtoken real (o eliminarlo si no se usa)
7. **Registrar un dispositivo móvil real** para Expo Push
8. **Revisar la IP hardcodeada** `192.168.0.43:8091` en `.env`

### Prioridad 3 — Limpieza
9. **Eliminar CSS muerto** del banner en `app.py`
10. **Decidir sobre columnas ignoradas** del CSV (usarlas o borrarlas)
11. **Centralizar el bloque de auth MSAL** en los scripts de test

### Prioridad 4 — Investigación de datos
12. **EERR_auto** tiene 375 días de retraso — investigar por qué no se actualiza
13. **Nivel de Servicio Estética** (crítico) está Demorado — 4 horas de retraso

---

## 7. Archivos del proyecto

| Archivo | Líneas | Función |
|---------|--------|---------|
| `app.py` | 2.505 | Frontend Streamlit (UI, CSS, SVG reactor) |
| `monitor_common.py` | 867 | Core: auth, consulta PBI, estados, notificaciones, persistencia |
| `monitor_worker.py` | 45 | CLI entrypoint para corridas |
| `mobile_push_server.py` | 145 | HTTP API para registro de tokens Expo |
| `mobile_push_api.py` | 7 | Wrapper trivial del anterior |
| `auth_test.py` | 53 | Login interactivo (device flow) |
| `test_login.py` | 27 | Login sin cache (diagnóstico) |
| `test_execute_query.py` | 56 | Prueba executeQueries |
| `test_cobranzas_query.py` | 56 | Prueba consulta Cobranzas |
| `test_refresh_history.py` | 42 | Historial de refrescos |
| `list_datasets.py` | 41 | Lista datasets de un workspace |
| `list_groups.py` | 40 | Lista workspaces |
| `config_tableros.csv` | 24 | Configuración de 23 tableros |
| `.env` | 16 | Variables de entorno |
| `DashboardControl.bat` | 8 | Lanzador (Streamlit + ngrok) |
| `ngrok.yml` | 8 | Configuración de túnel (placeholder) |

---

*Reporte generado el 15/07/2026 basado en el análisis del código y los archivos de estado del proyecto.*