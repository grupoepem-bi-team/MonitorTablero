"""
test_dax_debug.py - Ejecuta una consulta DAX y muestra el cuerpo del error.
"""
import json
import requests
from src.auth import obtener_token
from src import config

WORKSPACE_ID = "8ac545a2-7e14-41a4-8029-9cba4e6ac469"
DATASET_ID = "c21a13af-ce21-452c-8ccd-b6e1db2ef242"
TABLA = "conceptos_facturados"
COLUMNA = "Actualizado_al"

def main() -> int:
    token = obtener_token()
    url = (
        f"https://api.powerbi.com/v1.0/myorg/groups/{WORKSPACE_ID}"
        f"/datasets/{DATASET_ID}/executeQueries"
    )
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    query = f"EVALUATE ROW(\"ultima_actualizacion\", MAX('{TABLA}'[{COLUMNA}']))"
    payload = {
        "queries": [{"query": query}],
        "serializerSettings": {"includeNulls": True},
    }

    print("URL:", url)
    print("DAX:", query)
    print("Payload:", json.dumps(payload, indent=2))
    print()

    resp = requests.post(url, headers=headers, json=payload, timeout=config.POWERBI_API_TIMEOUT_S)
    print("Status:", resp.status_code)
    print("Response:", resp.text[:2000])
    return 0 if resp.ok else 1

if __name__ == "__main__":
    raise SystemExit(main())