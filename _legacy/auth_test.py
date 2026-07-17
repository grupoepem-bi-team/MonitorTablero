from msal import PublicClientApplication, SerializableTokenCache
import os

CLIENT_ID = "04f0c124-f2bc-4f59-8241-bf6df9866bbd"
AUTHORITY = "https://login.microsoftonline.com/organizations"
SCOPES = ["https://analysis.windows.net/powerbi/api/.default"]

_ROOT = os.path.dirname(os.path.abspath(__file__))
CACHE_FILE = os.path.join(_ROOT, "token_cache.bin")

cache = SerializableTokenCache()

if os.path.exists(CACHE_FILE):
    cache.deserialize(open(CACHE_FILE, "r").read())

app = PublicClientApplication(
    client_id=CLIENT_ID,
    authority=AUTHORITY,
    token_cache=cache
)

accounts = app.get_accounts()

result = None

if accounts:
    result = app.acquire_token_silent(SCOPES, account=accounts[0])

if not result:
    flow = app.initiate_device_flow(scopes=SCOPES)

    if "user_code" not in flow:
        raise Exception("No se pudo iniciar el device flow")

    print("Abrí este link en tu navegador:")
    print(flow["verification_uri"])
    print()
    print("Y pegá este código:")
    print(flow["user_code"])
    print()

    result = app.acquire_token_by_device_flow(flow)

if cache.has_state_changed:
    with open(CACHE_FILE, "w") as f:
        f.write(cache.serialize())

if "access_token" in result:
    print("LOGIN OK")
    print("Token cache guardado en:", CACHE_FILE)
else:
    print("ERROR")
    print(result)