"""
test_login.py - Login sin cache (diagnostico puro del device flow).

No usa token_cache.bin: fuerza el flujo de dispositivo desde cero.
Uso:  python -m scripts.test_login
"""
from msal import PublicClientApplication

from src import config


def main() -> int:
    app = PublicClientApplication(
        client_id=config.CLIENT_ID,
        authority=config.AUTHORITY,
    )
    flow = app.initiate_device_flow(scopes=config.SCOPES)
    if "user_code" not in flow:
        print("No se pudo iniciar el device flow")
        return 1

    print("Abri este link en tu navegador:")
    print(flow["verification_uri"])
    print()
    print("Y pega este codigo:")
    print(flow["user_code"])
    print()

    result = app.acquire_token_by_device_flow(flow)
    if "access_token" in result:
        print("LOGIN OK")
        return 0
    print("ERROR")
    print(result)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())