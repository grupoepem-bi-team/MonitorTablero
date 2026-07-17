"""
test_refresh_history.py - Historial de refrescos de un dataset de Power BI.

Muestra los ultimos 5 refrescos del dataset Facturacion.
Uso:  python -m scripts.test_refresh_history
"""
import requests

from src.auth import obtener_token

WORKSPACE_ID = "8ac545a2-7e14-41a4-8029-9cba4e6ac469"
DATASET_ID = "c21a13af-ce21-452c-8ccd-b6e1db2ef242"
TOP = 5


def main() -> int:
    token = obtener_token()
    url = (
        f"https://api.powerbi.com/v1.0/myorg/groups/{WORKSPACE_ID}"
        f"/datasets/{DATASET_ID}/refreshes?$top={TOP}"
    )
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(url, headers=headers, timeout=30)
    print("STATUS:", resp.status_code)
    print(resp.text)
    return 0 if resp.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())