"""
auth_step1.py - Inicia el device flow y guarda URL+codigo en un archivo.

Paso 1: python -m scripts.auth_step1
  -> Escribe device_flow_info.txt con la URL y el codigo
  -> Bloquea esperando a que el usuario se autentique en el navegador
  -> Cuando se autentica, guarda token_cache.bin

El usuario puede leer device_flow_info.txt para ver la URL y el codigo
mientras este script espera la autenticacion.
"""
import os
import sys

from msal import PublicClientApplication, SerializableTokenCache

from src import config


def main() -> int:
    cache = SerializableTokenCache()
    if os.path.exists(config.CACHE_FILE):
        with open(config.CACHE_FILE, encoding="utf-8") as f:
            cache.deserialize(f.read())

    app = PublicClientApplication(
        client_id=config.CLIENT_ID,
        authority=config.AUTHORITY,
        token_cache=cache,
    )

    flow = app.initiate_device_flow(scopes=config.SCOPES)
    if "user_code" not in flow:
        print("ERROR: No se pudo iniciar el device flow.")
        return 1

    info_path = os.path.join(config._ROOT_DIR, "device_flow_info.txt")
    with open(info_path, "w", encoding="utf-8") as f:
        f.write(f"URL: {flow['verification_uri']}\n")
        f.write(f"CODIGO: {flow['user_code']}\n")
        f.write(f"\nAbrí la URL en tu navegador y pegá el código.\n")
        f.write(f"Este script va a esperar hasta que te autentiques.\n")

    print(f"Info escrita en {info_path}")
    print(f"URL: {flow['verification_uri']}")
    print(f"CODIGO: {flow['user_code']}")
    print("Esperando autenticacion en el navegador...")

    result = app.acquire_token_by_device_flow(flow)

    if cache.has_state_changed:
        with open(config.CACHE_FILE, "w", encoding="utf-8") as f:
            f.write(cache.serialize())

    if result and "access_token" in result:
        print("LOGIN OK - token_cache.bin guardado")
        if os.path.exists(info_path):
            os.remove(info_path)
        return 0

    print("ERROR:", result.get("error_description", result))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())