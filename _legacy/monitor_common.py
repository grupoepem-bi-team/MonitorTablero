"""
Lógica compartida: consulta Power BI, estados, snapshot, ntfy y lectura/escritura de JSON
para el worker y el frontend (solo lectura en app).
"""
from __future__ import annotations

import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from functools import partial

import pandas as pd
import requests
from msal import PublicClientApplication, SerializableTokenCache

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))

CLIENT_ID = "04f0c124-f2bc-4f59-8241-bf6df9866bbd"
AUTHORITY = "https://login.microsoftonline.com/organizations"
SCOPES = ["https://analysis.windows.net/powerbi/api/.default"]
CACHE_FILE = os.path.join(ROOT_DIR, "token_cache.bin")

CONFIG_TABLEROS_CSV = os.path.join(ROOT_DIR, "config_tableros.csv")
ESTADO_ACTUAL_JSON = os.path.join(ROOT_DIR, "estado_actual.json")
CAMBIOS_RECIENTES_JSON = os.path.join(ROOT_DIR, "cambios_recientes.json")
SNAPSHOT_ESTADOS_JSON = os.path.join(ROOT_DIR, "estado_tableros_snapshot.json")
CORRIDA_MONITOR_META_JSON = os.path.join(ROOT_DIR, "corrida_monitor_meta.json")
NTFY_PUSH_PREF_JSON = os.path.join(ROOT_DIR, "ntfy_push_pref.json")
MOBILE_PUSH_TOKENS_JSON = os.path.join(ROOT_DIR, "mobile_push_tokens.json")

EXPO_PUSH_API_URL = "https://exp.host/--/api/v2/push/send"
EXPO_PUSH_CHUNK = 90

MAX_WORKERS_POWERBI = 12


def _env_bool(name: str, default: bool = False) -> bool:
    v = os.environ.get(name)
    if v is None or str(v).strip() == "":
        return default
    return str(v).strip().lower() in ("1", "true", "yes", "on", "si", "sí")


def _env_float(name: str, default: float) -> float:
    v = os.environ.get(name)
    if v is None or str(v).strip() == "":
        return default
    try:
        return float(str(v).strip())
    except ValueError:
        return default


def cargar_dotenv_local() -> None:
    env_path = os.path.join(ROOT_DIR, ".env")
    if not os.path.isfile(env_path):
        return
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(env_path)


cargar_dotenv_local()

NTFY_ENABLED = _env_bool("NTFY_ENABLED", False)
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "dashboardmonitorepem").strip() or "dashboardmonitorepem"
NTFY_BASE_URL = os.environ.get("NTFY_BASE_URL", "https://ntfy.sh").rstrip("/")
ALERTAR_SOLO_CRITICOS = _env_bool("ALERTAR_SOLO_CRITICOS", True)

EXPO_PUSH_ENABLED = _env_bool("EXPO_PUSH_ENABLED", False)
EXPO_PUSH_SOLO_CRITICOS = _env_bool("EXPO_PUSH_SOLO_CRITICOS", True)

LABEL_ESTADO = {
    "OK": "OK",
    "Advertencia": "Advertencia",
    "Demorado": "Demorado",
    "Error": "Error",
}

ORDEN_ESTADO = {"Error": 0, "Demorado": 1, "Advertencia": 2, "OK": 3}
ESTADOS_PROBLEMA = ("Error", "Demorado", "Advertencia")

RETASO_OK_MAX_MIN = 60
RETASO_ADVERTENCIA_MAX_MIN = 80


def _atomic_write_json(path: str, data: dict) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def _atomic_write_json_any(path: str, data: object) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def _cargar_push_pref_dict() -> dict:
    """
    Preferencias en `ntfy_push_pref.json`: toggle ntfy y toggle global Expo (independientes).
    """
    defaults = {
        "version": 1,
        "push_enabled": True,
        "expo_push_enabled": True,
    }
    if not os.path.isfile(NTFY_PUSH_PREF_JSON):
        return defaults.copy()
    try:
        with open(NTFY_PUSH_PREF_JSON, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return defaults.copy()
        out = defaults.copy()
        out["push_enabled"] = bool(data.get("push_enabled", True))
        out["expo_push_enabled"] = bool(data.get("expo_push_enabled", True))
        return out
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return defaults.copy()


def _guardar_push_pref_dict(payload: dict) -> None:
    _atomic_write_json(NTFY_PUSH_PREF_JSON, payload)


def leer_push_ntfy_usuario() -> bool:
    """
    Preferencia persistida (Streamlit). True = enviar ntfy si NTFY_ENABLED.
    False = pausa ntfy; no afecta el toggle de Expo.
    """
    return bool(_cargar_push_pref_dict().get("push_enabled", True))


def leer_expo_push_global() -> bool:
    """
    Interruptor global persistido (Streamlit). Independiente de ntfy.
    """
    return bool(_cargar_push_pref_dict().get("expo_push_enabled", True))


def escribir_push_ntfy_usuario(habilitado: bool) -> None:
    cur = _cargar_push_pref_dict()
    cur["version"] = 1
    cur["push_enabled"] = bool(habilitado)
    _guardar_push_pref_dict(cur)


def escribir_expo_push_global(habilitado: bool) -> None:
    cur = _cargar_push_pref_dict()
    cur["version"] = 1
    cur["expo_push_enabled"] = bool(habilitado)
    _guardar_push_pref_dict(cur)


def ntfy_push_efectivo() -> bool:
    """Envío ntfy permitido: variable de entorno + preferencia persistida."""
    return bool(NTFY_ENABLED) and leer_push_ntfy_usuario()


def _ruta_archivo_tokens_expo_push() -> str:
    raw = os.environ.get("EXPO_PUSH_TOKENS_FILE", "").strip()
    if not raw:
        return MOBILE_PUSH_TOKENS_JSON
    if os.path.isabs(raw):
        return raw
    return os.path.join(ROOT_DIR, raw)


def _norm_token_dict_legacy_str(t: str) -> dict:
    now = pd.Timestamp.now().isoformat()
    return {
        "token": t.strip(),
        "enabled": True,
        "platform": "unknown",
        "app_name": "",
        "app_version": "",
        "updated_at": now,
    }


def _norm_token_dict_record(d: dict) -> dict | None:
    t = d.get("token")
    if not isinstance(t, str) or not t.strip():
        return None
    now = pd.Timestamp.now().isoformat()
    return {
        "token": t.strip(),
        "enabled": bool(d.get("enabled", True)),
        "platform": str(d.get("platform") or "unknown"),
        "app_name": str(d.get("app_name") or ""),
        "app_version": str(d.get("app_version") or ""),
        "updated_at": str(d.get("updated_at") or now),
    }


def leer_registros_push_mobile(path: str | None = None) -> list[dict]:
    """
    Lee `mobile_push_tokens.json`: lista de objetos. Soporta formato viejo (lista de strings)
    y migra una sola vez a objetos en disco.
    """
    path = path or _ruta_archivo_tokens_expo_push()
    if not os.path.isfile(path):
        return []
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, json.JSONDecodeError, TypeError, UnicodeError):
        return []
    if not isinstance(raw, list):
        return []
    legacy = False
    norm: list[dict] = []
    for x in raw:
        if isinstance(x, str):
            legacy = True
            s = x.strip()
            if s:
                norm.append(_norm_token_dict_legacy_str(s))
        elif isinstance(x, dict):
            rec = _norm_token_dict_record(x)
            if rec:
                norm.append(rec)
    by_t: dict[str, dict] = {}
    for r in norm:
        by_t[r["token"]] = r
    result = list(by_t.values())
    need_write = legacy or (len(result) < len(norm))
    if need_write:
        try:
            _atomic_write_json_any(path, result)
            if legacy:
                print("[ExpoPush] migrado mobile_push_tokens.json (lista plana → objetos)", flush=True)
            else:
                print("[ExpoPush] deduplicados registros en mobile_push_tokens.json", flush=True)
        except OSError as e:
            print(f"[ExpoPush] aviso: no se pudo guardar normalización de tokens: {e}", flush=True)
    return result


def registrar_token_push_desde_app(body: dict) -> tuple[bool, str, dict]:
    """
    Alta/actualización desde la app móvil. Requiere body['token'].
    Retorna (éxito, mensaje, detalles_minimos).
    """
    token = body.get("token")
    if not isinstance(token, str) or not token.strip():
        return False, "token requerido", {}
    token = token.strip()
    platform = str(body.get("platform") or "unknown")
    app_name = str(body.get("app_name") or "")
    app_version = str(body.get("app_version") or "")
    now = pd.Timestamp.now().isoformat()
    path = _ruta_archivo_tokens_expo_push()
    recs = leer_registros_push_mobile(path)
    found = False
    for r in recs:
        if r.get("token") == token:
            r["enabled"] = True
            r["platform"] = platform
            r["app_name"] = app_name
            r["app_version"] = app_version
            r["updated_at"] = now
            found = True
            break
    if not found:
        recs.append(
            {
                "token": token,
                "enabled": True,
                "platform": platform,
                "app_name": app_name,
                "app_version": app_version,
                "updated_at": now,
            }
        )
    by_t: dict[str, dict] = {}
    for r in recs:
        by_t[r["token"]] = r
    recs_final = list(by_t.values())
    try:
        _atomic_write_json_any(path, recs_final)
    except OSError as e:
        return False, str(e), {}
    return True, "ok", {"registered": True}


def deshabilitar_tokens_expo_push_invalidos(
    tokens: list[str],
    path: str | None = None,
) -> int:
    """Marca tokens como enabled=false (p. ej. DeviceNotRegistered en Expo)."""
    if not tokens:
        return 0
    path = path or _ruta_archivo_tokens_expo_push()
    st = {t.strip() for t in tokens if isinstance(t, str) and t.strip()}
    if not st:
        return 0
    recs = leer_registros_push_mobile(path)
    n = 0
    for r in recs:
        if r.get("token") in st and r.get("enabled", True):
            r["enabled"] = False
            r["updated_at"] = pd.Timestamp.now().isoformat()
            n += 1
    if n:
        try:
            _atomic_write_json_any(path, recs)
            print(
                f"[ExpoPush] {n} registro(s) con enabled=false "
                "(Expo: DeviceNotRegistered / token ya no válido).",
                flush=True,
            )
        except OSError as e:
            print(f"[ExpoPush] no se pudo persistir baja de tokens: {e}", flush=True)
    return n


def _extraer_tokens_invalidos_expo_chunk(
    chunk_messages: list[dict],
    items: list[object],
) -> list[str]:
    invalid: list[str] = []
    for idx, it in enumerate(items):
        if not isinstance(it, dict):
            continue
        if str(it.get("status", "")).lower() == "ok":
            continue
        details = it.get("details")
        err_code = ""
        if isinstance(details, dict):
            err_code = str(details.get("error", "") or "")
        msg = str(it.get("message", "") or "")
        if err_code == "DeviceNotRegistered" or "DeviceNotRegistered" in msg:
            if idx < len(chunk_messages):
                to = chunk_messages[idx].get("to")
                if isinstance(to, str) and to.strip():
                    invalid.append(to.strip())
    return invalid


def cargar_tokens_expo_push(path: str | None = None) -> list[str]:
    """Tokens Expo habilitados, sin duplicados, para envío."""
    recs = leer_registros_push_mobile(path)
    out: list[str] = []
    seen: set[str] = set()
    for r in recs:
        if not r.get("enabled", True):
            continue
        t = str(r.get("token", "")).strip()
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    return out


def expo_push_efectivo_con_tokens_cargados(tokens: list[str]) -> bool:
    """Habilitado por env, toggle global persistido y al menos un token registrado."""
    return bool(EXPO_PUSH_ENABLED) and leer_expo_push_global() and len(tokens) > 0


def _resumir_respuesta_expo_push_payload(data: object) -> str:
    if not isinstance(data, dict):
        return "respuesta inesperada"
    items = data.get("data")
    if not isinstance(items, list):
        return str(data.get("errors") or data)[:300]
    n_ok = n_err = 0
    err_msgs: list[str] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        st = str(it.get("status", ""))
        if st == "ok":
            n_ok += 1
        else:
            n_err += 1
            m = str(it.get("message", "") or it.get("details") or "")[:120]
            if m and m not in err_msgs:
                err_msgs.append(m)
    if n_err == 0:
        return f"ok ({n_ok})"
    return f"errores {n_err}/{len(items)}; " + "; ".join(err_msgs[:3])


def enviar_expo_push_cambio_estado(
    nombre_tablero: str,
    anterior: str,
    nuevo: str,
    tokens: list[str],
    timeout: float,
) -> str | None:
    """
    Envía el mismo aviso de cambio de estado a todos los tokens (chunks si hace falta).
    Retorna None si todo OK; string breve si hubo fallo de red o errores Expo.
    """
    if not tokens:
        return None
    titulo = "Dashboard Control · cambio de estado"
    cuerpo = f"{nombre_tablero}: {anterior} → {nuevo}"
    messages = [
        {
            "to": t,
            "title": titulo,
            "body": cuerpo,
            "sound": "default",
        }
        for t in tokens
    ]
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Accept-Encoding": "gzip, deflate",
    }
    fatigas: list[str] = []
    invalid_accum: list[str] = []
    for i in range(0, len(messages), EXPO_PUSH_CHUNK):
        chunk = messages[i : i + EXPO_PUSH_CHUNK]
        try:
            r = requests.post(
                EXPO_PUSH_API_URL,
                headers=headers,
                json=chunk,
                timeout=timeout,
            )
        except requests.RequestException as e:
            return str(e)[:300] or "error de red Expo Push"
        try:
            payload = r.json()
        except ValueError:
            fatigas.append(f"HTTP {r.status_code}: cuerpo no JSON")
            continue
        if r.status_code >= 400:
            fatigas.append(f"HTTP {r.status_code}: {_resumir_respuesta_expo_push_payload(payload)}")
            continue
        items = payload.get("data") if isinstance(payload, dict) else None
        if isinstance(items, list):
            invalid_accum.extend(_extraer_tokens_invalidos_expo_chunk(chunk, items))
        res = _resumir_respuesta_expo_push_payload(payload)
        if "errores" in res or "inesperada" in res:
            fatigas.append(res)
    if invalid_accum:
        deshabilitar_tokens_expo_push_invalidos(invalid_accum)
    if not fatigas:
        print(f"[ExpoPush] ok · {nombre_tablero} · n={len(tokens)}", flush=True)
    return "; ".join(fatigas) if fatigas else None


def obtener_token() -> str:
    cache = SerializableTokenCache()
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, encoding="utf-8") as f:
            cache.deserialize(f.read())

    app = PublicClientApplication(
        client_id=CLIENT_ID,
        authority=AUTHORITY,
        token_cache=cache,
    )

    accounts = app.get_accounts()
    result = None
    if accounts:
        result = app.acquire_token_silent(SCOPES, account=accounts[0])

    if not result or "access_token" not in result:
        raise RuntimeError("No se pudo obtener token silencioso. Ejecutá auth_test.py de nuevo.")

    return result["access_token"]


def consultar_tablero_desde_fila(row, access_token: str):
    workspace_id = row["workspace_id"]
    dataset_id = row["dataset_id"]
    tabla_dax = row["tabla_dax"]
    columna_dax = row["columna_dax"]

    url = f"https://api.powerbi.com/v1.0/myorg/groups/{workspace_id}/datasets/{dataset_id}/executeQueries"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    query = f'EVALUATE ROW("ultima_actualizacion", MAX(\'{tabla_dax}\'[{columna_dax}]))'

    payload = {
        "queries": [{"query": query}],
        "serializerSettings": {"includeNulls": True},
    }

    resp = requests.post(url, headers=headers, json=payload, timeout=30)
    resp.raise_for_status()

    data = resp.json()
    raw_value = data["results"][0]["tables"][0]["rows"][0]["[ultima_actualizacion]"]
    return pd.to_datetime(raw_value)


def calcular_estado(retraso_min):
    if retraso_min <= RETASO_OK_MAX_MIN:
        return "OK"
    if retraso_min <= RETASO_ADVERTENCIA_MAX_MIN:
        return "Advertencia"
    return "Demorado"


def _ordenar_por_prioridad_estado(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    df = df.copy()
    df["_prio_estado"] = df["estado"].map(ORDEN_ESTADO)
    return (
        df.sort_values(
            by=["_prio_estado", "retraso_min"],
            ascending=[True, False],
            na_position="last",
        )
        .drop(columns=["_prio_estado"])
        .reset_index(drop=True)
    )


def _fila_resultado_ok(row_config, hora_consulta, ultima_actualizacion):
    retraso_min = round(
        (hora_consulta - ultima_actualizacion).total_seconds() / 60,
        2,
    )
    estado = calcular_estado(retraso_min)
    return {
        "tablero": row_config["tablero"],
        "critico": row_config["critico"],
        "estado": estado,
        "ultima_actualizacion": ultima_actualizacion,
        "hora_consulta": hora_consulta,
        "retraso_min": retraso_min,
        "error_detalle": "",
    }


def _fila_resultado_error(row_config, hora_consulta, mensaje_error):
    return {
        "tablero": row_config["tablero"],
        "critico": row_config["critico"],
        "estado": "Error",
        "ultima_actualizacion": pd.NaT,
        "hora_consulta": hora_consulta,
        "retraso_min": float("nan"),
        "error_detalle": mensaje_error,
    }


def _procesar_un_tablero(
    row_dict: dict,
    access_token: str,
    hora_consulta: pd.Timestamp,
) -> dict:
    try:
        ultima_actualizacion = consultar_tablero_desde_fila(row_dict, access_token)
        return _fila_resultado_ok(row_dict, hora_consulta, ultima_actualizacion)
    except Exception as e:
        return _fila_resultado_error(row_dict, hora_consulta, str(e))


def cargar_y_procesar_tableros_activos(access_token: str, path_csv: str | None = None) -> pd.DataFrame:
    if path_csv is None:
        path_csv = CONFIG_TABLEROS_CSV
    config_df = pd.read_csv(path_csv)
    config_df = config_df[config_df["activo"] == 1].copy()

    hora_consulta = pd.Timestamp.now()
    records = config_df.to_dict("records")

    if not records:
        return _ordenar_por_prioridad_estado(pd.DataFrame())

    workers = max(1, min(MAX_WORKERS_POWERBI, len(records)))
    worker_fn = partial(
        _procesar_un_tablero,
        access_token=access_token,
        hora_consulta=hora_consulta,
    )

    with ThreadPoolExecutor(max_workers=workers) as executor:
        results = list(executor.map(worker_fn, records))

    df = pd.DataFrame(results)
    return _ordenar_por_prioridad_estado(df)


def cargar_snapshot_estados(path: str) -> dict[str, dict]:
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        raw = data.get("by_tablero") or {}
        out: dict[str, dict] = {}
        for nombre, info in raw.items():
            if isinstance(info, dict) and "estado" in info:
                out[str(nombre)] = {"estado": str(info["estado"])}
            elif isinstance(info, str):
                out[str(nombre)] = {"estado": info}
        return out
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return {}


def guardar_snapshot_estados(path: str, df: pd.DataFrame) -> None:
    by_tablero = {
        str(r["tablero"]): {"estado": str(r["estado"])}
        for _, r in df.iterrows()
    }
    payload = {
        "version": 1,
        "updated_at": pd.Timestamp.now().isoformat(),
        "by_tablero": by_tablero,
    }
    _atomic_write_json(path, payload)


def detectar_cambios_estado(
    df: pd.DataFrame, prev: dict[str, dict]
) -> list[tuple[str, str, str, bool]]:
    if df.empty:
        return []
    cambios = []
    for _, row in df.iterrows():
        nombre = str(row["tablero"])
        nuevo = str(row["estado"])
        old_entry = prev.get(nombre)
        if not old_entry:
            continue
        anterior = str(old_entry.get("estado", ""))
        if anterior == nuevo:
            continue
        try:
            crit = int(float(row["critico"])) == 1
        except (TypeError, ValueError):
            crit = False
        cambios.append((nombre, anterior, nuevo, crit))
    return cambios


def texto_cambio_ui(nombre: str, anterior: str, nuevo: str) -> str:
    return f"**{nombre}** pasó de {LABEL_ESTADO.get(anterior, anterior)} a {LABEL_ESTADO.get(nuevo, nuevo)}"


def enviar_ntfy_cambio(nombre_tablero: str, anterior: str, nuevo: str) -> str | None:
    url = f"{NTFY_BASE_URL}/{NTFY_TOPIC}"
    titulo = "Dashboard Control · cambio de estado"
    cuerpo = f"{nombre_tablero}: {anterior} → {nuevo}"
    try:
        r = requests.post(
            url,
            data=cuerpo.encode("utf-8"),
            headers={"Title": titulo, "Tags": "chart"},
            timeout=12,
        )
        r.raise_for_status()
    except requests.RequestException as e:
        return str(e) or "Error de red ntfy"
    return None


def _df_a_payload_estado_actual(df: pd.DataFrame) -> dict:
    tableros = []
    for _, row in df.iterrows():
        ua = row["ultima_actualizacion"]
        hc = row["hora_consulta"]
        rm = row["retraso_min"]
        try:
            crit = int(float(row["critico"]))
        except (TypeError, ValueError):
            crit = 0
        tableros.append(
            {
                "tablero": str(row["tablero"]),
                "critico": crit,
                "estado": str(row["estado"]),
                "ultima_actualizacion": None
                if pd.isna(ua)
                else pd.Timestamp(ua).isoformat(),
                "hora_consulta": pd.Timestamp(hc).isoformat(),
                "retraso_min": None if pd.isna(rm) else float(rm),
                "error_detalle": str(row.get("error_detalle") or ""),
            }
        )
    return {
        "version": 1,
        "updated_at": pd.Timestamp.now().isoformat(),
        "tableros": tableros,
    }


def dataframe_desde_estado_actual(path: str) -> pd.DataFrame | None:
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError, TypeError):
        return None
    rows = data.get("tableros")
    if not isinstance(rows, list):
        return None
    if not rows:
        return _ordenar_por_prioridad_estado(pd.DataFrame())
    recs = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        ua = r.get("ultima_actualizacion")
        hc = r.get("hora_consulta")
        rm = r.get("retraso_min")
        recs.append(
            {
                "tablero": r.get("tablero", ""),
                "critico": r.get("critico", 0),
                "estado": r.get("estado", ""),
                "ultima_actualizacion": pd.NaT
                if ua is None
                else pd.to_datetime(ua, utc=False),
                "hora_consulta": pd.to_datetime(hc, utc=False)
                if hc
                else pd.NaT,
                "retraso_min": float("nan") if rm is None else float(rm),
                "error_detalle": str(r.get("error_detalle") or ""),
            }
        )
    df = pd.DataFrame(recs)
    return _ordenar_por_prioridad_estado(df)


def leer_cambios_recientes(path: str = CAMBIOS_RECIENTES_JSON) -> tuple[list[str], list[str]]:
    if not os.path.isfile(path):
        return [], []
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        lc = data.get("lineas_cambios_ui") or []
        lf = data.get("lineas_fallos") or []
        if not isinstance(lc, list):
            lc = []
        if not isinstance(lf, list):
            lf = []
        return [str(x) for x in lc], [str(x) for x in lf]
    except (OSError, json.JSONDecodeError, TypeError):
        return [], []


def leer_meta_corrida(path: str = CORRIDA_MONITOR_META_JSON) -> dict:
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError, TypeError):
        return {}


def cargar_datos_para_frontend() -> tuple[pd.DataFrame | None, list[str], list[str], dict, str | None]:
    """
    Retorna (df o None si no hay estado), lineas_cambios, lineas_fallos, meta, mensaje_error_lectura.
    """
    meta = leer_meta_corrida()
    lc, lf = leer_cambios_recientes()
    df = dataframe_desde_estado_actual(ESTADO_ACTUAL_JSON)
    if df is None:
        return (
            None,
            lc,
            lf,
            meta,
            "No se encontró `estado_actual.json` o está corrupto. Ejecutá el monitor: `python monitor_worker.py`.",
        )
    return df, lc, lf, meta, None


def ejecutar_corrida_monitor(path_csv: str | None = None) -> None:
    """
    Una corrida completa: Power BI → cambios → ntfy → escritura de JSON (incl. snapshot).
    """
    t0 = time.perf_counter()
    path_csv = path_csv or CONFIG_TABLEROS_CSV

    token = obtener_token()
    df = cargar_y_procesar_tableros_activos(token, path_csv)

    prev = cargar_snapshot_estados(SNAPSHOT_ESTADOS_JSON)
    cambios = detectar_cambios_estado(df, prev)
    lineas_cambios = [texto_cambio_ui(a, b, c) for a, b, c, _ in cambios]
    lineas_fallos: list[str] = []

    if ntfy_push_efectivo() and cambios:
        for nombre, ant, nuevo, es_critico in cambios:
            if ALERTAR_SOLO_CRITICOS and not es_critico:
                continue
            err = enviar_ntfy_cambio(nombre, ant, nuevo)
            if err:
                lineas_fallos.append(f"{nombre} (ntfy): {err}")

    tokens_expo = cargar_tokens_expo_push()
    expo_timeout = max(3.0, _env_float("EXPO_PUSH_TIMEOUT_S", 15.0))
    if expo_push_efectivo_con_tokens_cargados(tokens_expo) and cambios:
        for nombre, ant, nuevo, es_critico in cambios:
            if EXPO_PUSH_SOLO_CRITICOS and not es_critico:
                continue
            err = enviar_expo_push_cambio_estado(
                nombre, ant, nuevo, tokens_expo, expo_timeout
            )
            if err:
                lineas_fallos.append(f"{nombre} (Expo Push): {err}")

    try:
        guardar_snapshot_estados(SNAPSHOT_ESTADOS_JSON, df)
    except OSError as e:
        lineas_fallos.append(f"Snapshot local: {e}")

    payload_cambios = {
        "version": 1,
        "corrida_finalizada_at": pd.Timestamp.now().isoformat(),
        "lineas_cambios_ui": lineas_cambios,
        "lineas_fallos": lineas_fallos,
        "hubo_cambios": bool(lineas_cambios),
    }
    _atomic_write_json(CAMBIOS_RECIENTES_JSON, payload_cambios)

    _atomic_write_json(ESTADO_ACTUAL_JSON, _df_a_payload_estado_actual(df))

    dur = time.perf_counter() - t0
    meta = {
        "version": 1,
        "ultima_corrida_fin": pd.Timestamp.now().isoformat(),
        "duracion_s": round(dur, 3),
        "exito": True,
        "error": None,
        "n_tableros": len(df),
        "n_cambios_estado": len(cambios),
    }
    _atomic_write_json(CORRIDA_MONITOR_META_JSON, meta)


def ejecutar_corrida_monitor_con_manejo_error(path_csv: str | None = None) -> tuple[bool, str | None]:
    """Para CLI: (exito, mensaje_error). No borra estado_actual.json si falla."""
    try:
        ejecutar_corrida_monitor(path_csv)
        return True, None
    except Exception as e:
        msg = str(e)
        meta = {
            "version": 1,
            "ultima_corrida_fin": pd.Timestamp.now().isoformat(),
            "exito": False,
            "error": msg,
            "n_tableros": 0,
            "n_cambios_estado": 0,
        }
        try:
            _atomic_write_json(CORRIDA_MONITOR_META_JSON, meta)
        except OSError:
            pass
        return False, msg
