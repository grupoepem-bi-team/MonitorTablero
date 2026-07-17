"""
check_token_security.py - Decodifica el access_token y muestra sus permisos (scopes/roles).
Uso: python -m scripts.check_token_security
"""
import base64
import json
from src.auth import obtener_token

def decode_jwt_payload(token: str) -> dict:
    parts = token.split(".")
    if len(parts) < 2:
        return {}
    payload_b64 = parts[1]
    padding = 4 - len(payload_b64) % 4
    payload_b64 += "=" * padding
    decoded = base64.urlsafe_b64decode(payload_b64)
    return json.loads(decoded)

def main() -> int:
    token = obtener_token()
    payload = decode_jwt_payload(token)

    print("=== Token de Azure AD ===")
    print(f"Usuario: {payload.get('upn', payload.get('email', '?'))}")
    print(f"Nombre:  {payload.get('name', '?')}")
    print(f"App ID:  {payload.get('appid', '?')}")
    print(f"Tenant:  {payload.get('tid', '?')}")
    print(f"Expira:  {payload.get('exp', '?')}")
    print(f"Issued:  {payload.get('iat', '?')}")
    print()

    # Scopes (delegated permissions)
    scp = payload.get("scp", "")
    print(f"Scopes (permisos delegados): {scp}")
    print()

    # Roles (application permissions, solo para SP)
    roles = payload.get("roles", [])
    if roles:
        print(f"Roles: {roles}")
    else:
        print("Roles: (ninguno - token de usuario, no de service principal)")
    print()

    # Audencia
    print(f"Audience: {payload.get('aud', '?')}")
    print()

    # Verificar si tiene permisos de escritura
    all_perms = (scp or "").split() + (roles or [])
    write_perms = [p for p in all_perms if "Write" in p]
    read_perms = [p for p in all_perms if "Read" in p and "Write" not in p]

    print("=== Analisis de seguridad ===")
    if write_perms:
        print(f"PERMISOS DE ESCRITURA (riesgo): {write_perms}")
    else:
        print("No hay permisos de escritura")

    if read_perms:
        print(f"Permisos de lectura (OK): {read_perms}")

    if write_perms:
        print()
        print("ADVERTENCIA: El token tiene permisos de escritura.")
        print("Si alguien roba token_cache.bin, podria modificar/borrar recursos de Power BI.")
    else:
        print()
        print("OK: El token solo tiene permisos de lectura.")

    return 0

if __name__ == "__main__":
    raise SystemExit(main())