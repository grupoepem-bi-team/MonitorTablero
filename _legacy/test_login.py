from msal import PublicClientApplication

CLIENT_ID = "04f0c124-f2bc-4f59-8241-bf6df9866bbd"
AUTHORITY = "https://login.microsoftonline.com/organizations"
SCOPES = ["https://analysis.windows.net/powerbi/api/.default"]

app = PublicClientApplication(client_id=CLIENT_ID, authority=AUTHORITY)

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

if "access_token" in result:
    print("LOGIN OK")
else:
    print("ERROR")
    print(result)