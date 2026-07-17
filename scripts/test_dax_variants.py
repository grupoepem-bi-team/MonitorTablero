"""
test_dax_variants.py - Prueba diferentes formas de obtener el maximo de una columna.
"""
import json
import requests
from src.auth import obtener_token
from src import config

WORKSPACE_ID = "8ac545a2-7e14-41a4-8029-9cba4e6ac469"
DATASET_ID = "c21a13af-ce21-452c-8ccd-b6e1db2ef242"
TABLA = "conceptos_facturados"
COLUMNA = "Actualizado_al"

def run_dax(token: str, query: str) -> tuple[int, str]:
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
    return resp.status_code, resp.text[:2000]

def main() -> int:
    token = obtener_token()

    variants = [
        ("MAX original", f"EVALUATE ROW(\"v\", MAX('{TABLA}'[{COLUMNA}']))"),
        ("MAX sin comilla en col", f"EVALUATE ROW(\"v\", MAX('{TABLA}'[{COLUMNA}]))"),
        ("TOPN(1) ORDER DESC", f"EVALUATE TOPN(1, '{TABLA}', '{TABLA}'[{COLUMNA}], DESC)"),
        ("SELECTCOLUMNS TOPN(1)", f"EVALUATE TOPN(1, SELECTCOLUMNS('{TABLA}', \"v\", [{COLUMNA}]))"),
        ("LASTDATE", f"EVALUATE ROW(\"v\", LASTDATE('{TABLA}'[{COLUMNA}]))"),
        ("MAXA", f"EVALUATE ROW(\"v\", MAXA('{TABLA}'[{COLUMNA}]))"),
    ]

    for label, query in variants:
        print(f"--- {label} ---")
        print(f"DAX: {query}")
        status, body = run_dax(token, query)
        print(f"Status: {status}")
        print(f"Body: {body[:800]}")
        print()
        if status == 200:
            print("FUNCIONA!")
            return 0

    return 1

if __name__ == "__main__":
    raise SystemExit(main())