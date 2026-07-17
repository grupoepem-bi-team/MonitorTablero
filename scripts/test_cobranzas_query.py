"""
test_cobranzas_query.py - Prueba consulta DAX contra dataset Seguimiento Cobranzas.

Ejecuta un DAX de diagnostico (INFO.VIEW.COLUMNS) sobre el dataset de Cobranzas.
Uso:  python -m scripts.test_cobranzas_query
"""
import json

import requests

from src import config
from src.auth import obtener_token

WORKSPACE_ID = "8ac545a2-7e14-41a4-8029-9cba4e6ac469"
DATASET_ID = "ef777842-77d1-476f-bb3f-572fd4d2bec9"
DAX_QUERY = 'EVALUATE FILTER(INFO.VIEW.COLUMNS(), [Table] = "cobros_prepagas_resumen")'


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
    payload = {
        "queries": [{"query": DAX_QUERY}],
        "serializerSettings": {"includeNulls": True},
    }
    resp = requests.post(
        url, headers=headers, json=payload, timeout=config.POWERBI_API_TIMEOUT_S
    )
    print("STATUS:", resp.status_code)
    print(json.dumps(resp.json(), indent=2, ensure_ascii=False))
    return 0 if resp.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())