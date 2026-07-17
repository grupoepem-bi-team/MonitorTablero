"""
auth_test.py - Login interactivo (device flow) con Azure AD.

Guarda el token en token_cache.bin para que el worker lo use silenciosamente.
Uso:  python -m scripts.auth_test
"""
from src.auth import login_device_flow


def main() -> int:
    print("Iniciando device flow de Azure AD...")
    result = login_device_flow()
    if result and "access_token" in result:
        print("LOGIN OK")
        print("Token cache guardado en token_cache.bin")
        return 0
    print("ERROR")
    print(result)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())