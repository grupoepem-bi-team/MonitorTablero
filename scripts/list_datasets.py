"""
list_datasets.py - Lista los datasets de un workspace de Power BI.

Uso:  python -m scripts.list_datasets
"""
import requests

from src.auth import obtener_token

WORKSPACE_ID = "8ac545a2-7e14-41a4-8029-9cba4e6ac469"


def main() -> int:
    token = obtener_token()
    url = f"https://api.powerbi.com/v1.0/myorg/groups/{WORKSPACE_ID}/datasets"
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(url, headers=headers, timeout=30)
    print("STATUS:", resp.status_code)
    print(resp.text)
    return 0 if resp.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())