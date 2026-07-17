"""
list_groups.py - Lista los workspaces (groups) de Power BI.

Uso:  python -m scripts.list_groups
"""
import requests

from src.auth import obtener_token


def main() -> int:
    token = obtener_token()
    url = "https://api.powerbi.com/v1.0/myorg/groups"
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(url, headers=headers, timeout=30)
    print("STATUS:", resp.status_code)
    print(resp.text)
    return 0 if resp.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())