# Monitor de Tableros Power BI

## Que hace este proyecto

Este proyecto es un **panel de control** que vigila la frescura de los datos de los tableros de Power BI.

El problema que resuelve: cuando un tablero de Power BI deja de actualizarse (por ejemplo, porque un proceso de ETL fallo, o alguien olvido programar el refresco), nadie se entera hasta que alguien abre el tablero y ve datos viejos. Esto puede ser horas o dias.

El monitor **consulta automaticamente cada tablero** y muestra en una pagina web si esta actualizado o atrasado, para que el equipo de BI lo vea de un vistazo.

### Como funciona en 3 pasos

1. **Consulta Power BI**: un programa (el "worker") se conecta a la API de Power BI y pregunta "cual es la fecha mas reciente de la tabla X del tablero Y?"
2. **Calcula el retraso**: compara esa fecha con la hora actual. Si pasaron mas de 30 minutos, lo marca como "Advertencia". Si pasaron mas de 60, "Demorado".
3. **Muestra en pantalla**: una pagina web simple muestra dos secciones: **Atrasados** (los que tienen problemas) y **Al dia** (los que estan OK).

### Que ve el usuario

```
Monitor de Tableros
Monitoreo de actualizacion       actualizado 14:46 · 8.3s    [Actualizar]

ATRASADOS  9
  ● EERR_auto              04/07   hace 378d
  ● ODONTOLOGOS            15/07   hace 20h
  ● Servicios Estetica     16/07   hace 7h
  ◐ Facturacion            16/07   hace 31m

AL DIA  14
  ● Seguimiento Cobranzas 16/07   hace 28m
  ● MLA                   14:46   hace 2m
```

- **Punto rojo + triangulo**: Demorado (mas de 60 min)
- **Punto ambar + reloj**: Advertencia (entre 30 y 60 min)
- **Punto verde + check**: OK (menos de 30 min)
- **CR**: tablero marcado como critico (requiere atencion prioritaria)

### Caracteristicas

- **Actualizacion automatica**: refresca cada 30 segundos si hay atrasados, cada 5 minutos si todo OK
- **Notificaciones del navegador**: si un tablero critico pasa a estar atrasado, manda una notificacion al escritorio
- **Modo claro/oscuro**: automatico segun horario (claro de dia, oscuro de tarde/noche), con override manual
- **Tooltip**: al pasar el mouse sobre "hace 20h" muestra la fecha y hora exacta
- **Historico**: guarda cada corrida para calcular tendencia y fiabilidad (mejorando o empeorando)

---

## Como levantarlo

### Requisitos previos

1. **Python 3.12+** instalado
2. **Token de Azure**: el monitor necesita autenticarse en Power BI. La primera vez hay que hacer un login interactivo (abrir el navegador, ingresar un codigo). Eso genera un archivo `token_cache.bin` que se reusa despues.
3. **Archivo `.env`**: con el ID de aplicacion de Azure (`AZURE_CLIENT_ID`)

### Paso a paso (primera vez)

```bash
# 1. Crear entorno virtual
python -m venv .venv
.venv\Scripts\activate

# 2. Instalar dependencias
pip install -r requirements.txt

# 3. Copiar y editar .env
copy .env.example .env
# Editar .env y poner el AZURE_CLIENT_ID

# 4. Hacer login en Azure (primera y unica vez)
python -m scripts.auth_test
# Abre el navegador, pegas el codigo, y listo.
# Se crea token_cache.bin

# 5. Ejecutar una corrida del worker (genera los primeros datos)
python -m src.worker

# 6. Levantar el servidor web
start.bat
# O manualmente:
python -m uvicorn frontend.server:app --host 127.0.0.1 --port 8501
```

Abrir el navegador en **http://localhost:8501**

### Siguientes veces

```bash
# Solo levantar
start.bat
```

El token se renueva solo. Solo hay que hacer login de nuevo si expira (lo cual pasa cada ~90 dias, o si se borra `token_cache.bin`).

### Con Docker

```bash
# Verificar puerto libre
python scripts/check_port.py 8501

# Levantar
docker compose up -d --build

# Ver logs
docker compose logs -f

# Detener
docker compose down
```

---

## Consideraciones importantes

### Seguridad

- **`.env` y `token_cache.bin` no se incluyen** en la imagen de Docker. Se montan como volumenes read-only.
- **El frontend no tiene acceso a credenciales**. Toda la autenticacion con Azure la hace el backend (Python).
- **No hay base de datos**. Todo se guarda en archivos JSON en disco. No hay datos sensibles almacenados.

### Token de Azure

- Si el token expira, el worker falla pero **no borra el estado anterior**. El dashboard sigue mostrando el ultimo estado valido.
- Para re-autenticar: `python -m scripts.auth_test` (fuera de Docker) o `docker compose exec monitor python -m scripts.auth_test` (dentro de Docker).

### Configuracion de tableros

- La lista de tableros a monitorear esta en `config_tableros.csv` (separado por `;`).
- Columnas: `tablero;workspace_id;dataset_id;tabla_dax;columna_dax;critico;frecuencia_objetivo_min;demorado_min;activo`
- `critico=1` marca tableros prioritarios (disparan notificaciones del navegador)
- `activo=0` desactiva un tablero sin borrarlo del archivo
- Para cambios, editar el CSV y reiniciar el worker. No requiere recompilar nada.

### Frecuencia de actualizacion

| Situacion | Intervalo |
|-----------|-----------|
| Hay tableros atrasados | cada 30 segundos |
| Todos OK | cada 5 minutos |
| Manual (boton Actualizar) | bajo demanda |

### Umbrales de estado

| Retraso | Estado | Color |
|---------|--------|-------|
| menos de 30 min | OK | verde |
| 30-60 min | Advertencia | ambar |
| mas de 60 min | Demorado | rojo |
| Error en consulta | Error | rojo |

Los umbrales (30 y 60) se configuran por tablero en el CSV (`frecuencia_objetivo_min`, `demorado_min`). Si no se especifican, usan los valores globales del `.env`.

### Historico

- Cada corrida del worker se guarda en `historico_corridas.jsonl` (una linea JSON por corrida).
- Se conservan hasta 1008 corridas (7 dias a 30 min de intervalo).
- Permite calcular tendencia (si el retraso esta mejorando o empeorando) y fiabilidad (% de corridas en OK).

### Modo claro/oscuro

| Modo | Comportamiento |
|------|---------------|
| **Auto** (default) | Claro entre 6:00 y 18:00, oscuro de 18:00 a 6:00 |
| **Claro** | Forzado claro, ignora horario |
| **Oscuro** | Forzado oscuro, ignora horario |

La eleccion se guarda en el navegador (`localStorage`). El modo auto se re-evalua cada minuto.

### Tests

El proyecto tiene 194 tests automaticos que verifican:
- Logica de calculo de estados (umbrales, ordenamiento)
- Persistencia (escritura/lectura atomica de JSON, archivos corruptos)
- Consulta a Power BI (mockeada, sin tocar la API real)
- API del frontend (endpoints, estructura de respuesta)
- Metricas derivadas (ranking, tendencia, fiabilidad)
- Worker completo (corrida end-to-end mockeada)

Para ejecutarlos:
```bash
python -m pytest tests/ -v
```

### Limitaciones conocidas

- **Sin notificaciones push moviles**: las notificaciones son solo del navegador (escritorio). Para alertas moviles habria que restaurar el sistema de Expo Push que estaba en la version original.
- **Login no es automatico**: la primera vez hay que hacer login interactivo. No se puede automatizar sin un service account con permisos delegados.
- **Un solo usuario**: el token es de un usuario de Azure. No es multi-tenant ni multi-usuario.

---

## Estructura del proyecto (resumen)

```
dashboardcontrol/
├── src/                    # Backend Python
│   ├── config.py           # Configuracion y variables de entorno
│   ├── auth.py             # Login con Azure AD (MSAL)
│   ├── powerbi.py          # Consulta DAX a Power BI
│   ├── estados.py          # Calculo de estados (OK/Adv/Demorado)
│   ├── metricas.py         # Metricas derivadas (ranking, tendencia)
│   ├── persistencia.py     # Lectura/escritura de JSON en disco
│   ├── cambios.py          # Deteccion de cambios entre corridas
│   ├── worker.py           # Orquestador de una corrida completa
│   ├── scheduler.py        # Loop infinito (ejecuta worker cada N min)
│   └── logger.py           # Logging a archivo + consola
├── frontend/               # Servidor web + interfaz
│   ├── server.py           # FastAPI: endpoints /api/todos, /api/corrida
│   ├── templates/index.html # Pagina web (HTML)
│   ├── static/style.css    # Estilos (dark/light, animaciones)
│   └── static/app.js       # Logica del frontend (render, refresh)
├── scripts/                # Utilidades
│   ├── auth_test.py        # Login interactivo (device flow)
│   ├── check_port.py       # Verifica si puerto 8501 esta libre
│   └── list_*.py           # Scripts de diagnostico de Power BI
├── tests/                  # 194 tests automaticos
├── config_tableros.csv     # Lista de 23 tableros a monitorear
├── .env                    # Credenciales (no commitear)
├── token_cache.bin         # Token Azure cacheado
├── Dockerfile              # Imagen Docker multi-arch (x86 + ARM)
├── docker-compose.yml      # Deploy con volumenes + healthcheck
├── start.bat               # Script de inicio (verifica puerto + levanta)
└── requirements.txt        # Dependencias Python
```

---

## Para un LLM: contexto de mantenimiento

Si un LLM necesita entender el proyecto para modificarlo:

1. **No tocar `src/auth.py`**: la autenticacion MSAL es delicada. Si se rompe, no hay forma de consultar Power BI.
2. **`src/persistencia.py` usa `path=None` como default** (no `path=config.X`): esto es intencional. Los defaults capturados al importar causaban bugs.
3. **`config_tableros.csv` usa `;` como separador**, no `,`.
4. **Los JSON de estado se escriben atomicamente** (.tmp + os.replace). Nunca escribir directo al archivo final.
5. **El historico es append-only** (`historico_corridas.jsonl`). Una linea JSON por corrida. No modificar lineas existentes.
6. **El frontend es vanilla HTML/CSS/JS**: sin React, sin Vue, sin bundler. Se sirve directo desde FastAPI.
7. **Los tests mockean `requests.post`** para no tocar Power BI real. El worker se testea con `monkeypatch` de todos los paths de JSON.
8. **El modo dark/light se controla con `data-theme` en `<html>`**. Auto = segun horario (JS), manual = forzado via atributo.
9. **El auto-refresh es dinamico**: 30s con atrasados, 5min sin ellos. Se re-programa despues de cada carga.