"""
test_tablas_posibles.py - Prueba nombres de tabla alternativos para Facturacion.
"""
import json
import requests
from src.auth import obtener_token
from src import config

WORKSPACE_ID = "8ac545a2-7e14-41a4-8029-9cba4e6ac469"
DATASET_ID = "c21a13af-ce21-452c-8ccd-b6e1db2ef242"

def run_dax(token: str, query: str) -> dict:
    url = (
        f"https://api.powerbi.com/v1.0/myorg/groups/{WORKSPACE_ID}"
        f"/datasets/{DATASET_ID}/executeQueries"
    )
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    payload = {
        "queries": [{"query": query}],
        "serializerSettings": {"includeNulls": True},
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=config.POWERBI_API_TIMEOUT_S)
    if not resp.ok:
        return {"_status": resp.status_code, "_error": resp.text[:500]}
    return resp.json()

def main() -> int:
    token = obtener_token()

    tablas_posibles = [
        "conceptos_facturados",
        "Facturacion",
        "facturacion",
        "Conceptos_Facturados",
        "conceptosfacturados",
        "Conceptos Facturados",
    ]
    columnas_posibles = [
        "Actualizado_al",
        "Actualizado_al",
        "actualizado_al",
        "Actualizado_Al",
        "ACTUALIZADO_AL",
    ]

    for tabla in tablas_posibles:
        for col in columnas_posibles:
            query = f"EVALUATE TOPN(1, SELECTCOLUMNS('{tabla}', \"{col}\", [{col}]))"
            data = run_dax(token, query)
            status = data.get("_status", 200)
            if "_error" not in data:
                print(f"OK  tabla='{tabla}' col='{col}'")
                print(json.dumps(data, indent=2)[:500])
                return 0
            err_msg = data.get("_error", "")
            if "cannot be found" not in err_msg and "not a valid" not in err_msg:
                print(f"??? tabla='{tabla}' col='{col}' status={status} err={err_msg[:200]}")
            else:
                print(f"NO  tabla='{tabla}' col='{col}'")
    return 1

if __name__ == "__main__":
    raise SystemExit(main())