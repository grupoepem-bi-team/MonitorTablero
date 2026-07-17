from msal import PublicClientApplication, SerializableTokenCache
import os
import requests

CLIENT_ID = "04f0c124-f2bc-4f59-8241-bf6df9866bbd"
AUTHORITY = "https://login.microsoftonline.com/organizations"
SCOPES = ["https://analysis.windows.net/powerbi/api/.default"]

CACHE_FILE = "token_cache.bin"
WORKSPACE_ID = "8ac545a2-7e14-41a4-8029-9cba4e6ac469"  # 3.- Producción

cache = SerializableTokenCache()
if os.path.exists(CACHE_FILE):
    with open(CACHE_FILE, "r") as f:
        cache.deserialize(f.read())

app = PublicClientApplication(
    client_id=CLIENT_ID,
    authority=AUTHORITY,
    token_cache=cache
)

accounts = app.get_accounts()
result = None

if accounts:
    result = app.acquire_token_silent(SCOPES, account=accounts[0])

if not result or "access_token" not in result:
    raise Exception("No se pudo obtener token silencioso. Probá de nuevo con auth_test.py")

access_token = result["access_token"]

url = f"https://api.powerbi.com/v1.0/myorg/groups/{WORKSPACE_ID}/datasets"
headers = {
    "Authorization": f"Bearer {access_token}"
}

resp = requests.get(url, headers=headers)
print("STATUS:", resp.status_code)
print(resp.text)