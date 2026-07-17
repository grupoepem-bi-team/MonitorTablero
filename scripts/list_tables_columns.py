"""
list_tables_columns.py - Lista tablas de un dataset probando nombres comunes.
Uso: python -m scripts.list_tables_columns
"""
import json
import requests
from src.auth import obtener_token
from src import config

WORKSPACE_ID = "8ac545a2-7e14-41a4-8029-9cba4e6ac469"
DATASET_ID = "c21a13af-ce21-452c-8ccd-b6e1db2ef242"

def run_dax(token: str, query: str) -> dict | None:
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
        return {"_error": resp.text[:1000], "_status": resp.status_code}
    return resp.json()

def main() -> int:
    token = obtener_token()

    # Probar varias queries para descubrir tablas y columnas
    queries = [
        ("Tablas via $SYSTEM.TMSCHEMA_TABLES", "SELECT * FROM $SYSTEM.TMSCHEMA_TABLES"),
        ("Tablas via $SYSTEM.DBSCHEMA_TABLES", "SELECT * FROM $SYSTEM.DBSCHEMA_TABLES"),
        ("Tablas via $SYSTEM.MDSCHEMA_TABLES", "SELECT * FROM $SYSTEM.MDSCHEMA_TABLES"),
        ("Columnas via $SYSTEM.MDSCHEMA_COLUMNS", "SELECT * FROM $SYSTEM.MDSCHEMA_COLUMNS"),
    ]

    for label, query in queries:
        print(f"=== {label} ===")
        data = run_dax(token, query)
        if data is None:
            print("  Sin respuesta")
        elif "_error" in data:
            print(f"  Status {data['_status']}: {data['_error'][:300]}")
        else:
            print(json.dumps(data, indent=2)[:5000])
        print()
        if data and "_error" not in data:
            break

    return 0

if __name__ == "__main__":
    raise SystemExit(main())