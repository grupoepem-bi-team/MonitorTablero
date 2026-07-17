# Autenticacion con Power BI

Este documento explica como el sistema se conecta a la API de Power BI, como
se obtienen las credenciales, y como migrar a una app con permisos minimos.

---

## Como funciona (resumen)

```
                        token_cache.bin
                              |  (refresh token)
                              v
  src/auth.py  --->  MSAL  --->  Azure AD  --->  access token (1h)
                              |
                              v
  src/powerbi.py  --->  POST /executeQueries  (Bearer token)
                              |
                              v
                       DAX: MAX('tabla'[columna])
                              |
                              v
                       fecha de ultima actualizacion
```

1. **Una vez** el usuario se loguea con el flujo de dispositivo de Azure AD
   (device flow). Esto guarda un refresh token en `token_cache.bin`.
2. **En cada corrida**, el worker usa ese refresh token para pedir un access
   token nuevo (silencioso, sin interaccion del usuario).
3. El access token dura 1 hora. El refresh token dura 90 dias de inactividad.
4. Con el access token, el worker consulta la API REST de Power BI ejecutando
   un DAX `MAX('tabla'[columna])` contra cada dataset.

El dato de "ultima actualizacion" **no viene del servicio de Power BI**. Viene
de una columna dentro de los datos del dataset (ej: `conceptos_facturados[Actualizado_al]`),
que los procesos ETL dejan registrada.

---

## Primera vez: como loguearse

```bash
# Activar el entorno virtual
.venv\Scripts\activate

# Ejecutar el flujo de dispositivo
python -m scripts.auth_test
```

Esto muestra en consola una URL y un codigo. Abrir la URL en el navegador,
pegar el codigo, y autenticarse con la cuenta de Azure AD. El token se guarda
en `token_cache.bin` y a partir de ahi el worker lo renueva solo.

---

## Estado actual (a julio 2026)

| Aspecto | Estado | Riesgo |
|---------|--------|--------|
| Usuario autenticado | AlanChaparro@GRUPOIDEM.onmicrosoft.com | Si Alan cambia password o deja la empresa, se rompe |
| App registration | CLIENT_ID 04f0c124... (no aparece en Azure Portal) | Si fue borrada, el refresh token deja de funcionar |
| Permisos del token | ReadWrite.All en todo | Excesivo: el codigo solo necesita lectura |
| Refresh token | Ultima modificacion 18/06/2026 | Expira a los 90 dias de inactividad |
| Tipo de auth | Usuario humano (device flow) | Un Service Principal seria mas robusto |

---

## Migracion: crear nueva app con permisos minimos

### Paso 1: Crear la app en Azure Portal

1. Entrar a https://portal.azure.com
2. Buscar "App registrations" (Registros de aplicaciones)
3. Click en "New registration" (Nuevo registro)
4. Nombre: `DashboardControl-Monitor` (o el que prefieras)
5. Supported account types: **Single tenant** (solo el tenant GRUPOIDEM)
6. Redirect URI: dejar vacio (no se necesita para device flow)
7. Click en "Register"
8. Copiar el **Application (client) ID** que se genera

### Paso 2: Configurar permisos

1. En la app recien creada, ir a "API permissions" (Permisos de API)
2. Click en "Add a permission" (Agregar permiso)
3. Seleccionar "Power BI Service"
4. Seleccionar "Delegated permissions" (Permisos delegados)
5. Marcar SOLO:
   - `Dataset.Read.All`
   - `Workspace.Read.All`
6. NO marcar: Capacity, Report, Write, ni ningun otro
7. Click en "Add permissions"
8. Click en "Grant admin consent for [tenant]" (Conceder consentimiento
   de administrador) para que los permisos queden aprobados

### Paso 3: Configurar el proyecto

1. Abrir el archivo `.env` del proyecto
2. Pegar el CLIENT_ID en la variable `AZURE_CLIENT_ID`:
   ```
   AZURE_CLIENT_ID=tu-nuevo-client-id-aqui
   ```
3. Guardar

### Paso 4: Regenerar el token

```bash
.venv\Scripts\activate
python -m scripts.auth_test
```

Autenticarse con la cuenta de Azure AD. Esto genera un nuevo `token_cache.bin`
con el refresh token vinculado a la nueva app.

### Paso 5: Verificar

```bash
python -m src.worker
```

Deberia ejecutar una corrida completa y devolver:
```
Corrida OK - 23 tableros - N cambios de estado - X.X s
```

---

## Archivos involucrados

| Archivo | Funcion |
|---------|---------|
| `src/config.py` | Define `CLIENT_ID`, `AUTHORITY`, `SCOPES` |
| `src/auth.py` | `obtener_token()` (silencioso) y `login_device_flow()` (interactivo) |
| `token_cache.bin` | Cache serializado de MSAL con el refresh token |
| `scripts/auth_test.py` | Script para ejecutar el device flow la primera vez |
| `.env` | Variable `AZURE_CLIENT_ID` (sobreescribe el fallback del codigo) |

---

## Preguntas frecuentes

**¿Que pasa si el refresh token expira?**
El worker lanza `RuntimeError: No se pudo obtener token silencioso. Ejecuta
scripts/auth_test.py para volver a loguearte.` Hay que correr el device flow
nuevamente.

**¿Que pasa si cambio el CLIENT_ID en .env?**
El refresh token del `token_cache.bin` viejo queda invalido (esta vinculado a
la app anterior). Hay que borrar `token_cache.bin` y ejecutar
`python -m scripts.auth_test` para regenerarlo con la nueva app.

**¿Por que no usar Service Principal (app sin usuario humano)?**
Un Service Principal seria mas robusto para un servicio que corre
automaticamente, pero requiere client_secret o certificado y permisos de
aplicacion (no delegados). La migracion a Service Principal queda pendiente
por ahora. El `.env` tiene campos vacios `TENANT_ID`, `CLIENT_ID`,
`CLIENT_SECRET` de un intento anterior que no se completo.

**¿El token_cache.bin es seguro?**
Contiene el refresh token. Si alguien lo roba, puede pedir access tokens en
nombre del usuario. Por eso es importante:
- No commitearlo a git (esta en `.gitignore`)
- Usar una app con permisos minimos (solo lectura)
- Si se sospecha compromiso, borrar el cache y re-autenticarse