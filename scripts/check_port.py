"""check_port.py - Verifica si el puerto 8501 esta libre antes de levantar el server.

Uso:
    python scripts/check_port.py [puerto]

Si el puerto esta ocupado, muestra que proceso lo tiene y sale con error.
Si esta libre, sale con 0.
"""
import sys
import socket


def check_port(port: int = 8501) -> bool:
    """True si el puerto esta libre."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(1)
    try:
        result = sock.connect_ex(("127.0.0.1", port))
        if result == 0:
            return False  # esta ocupado
        return True  # esta libre
    except Exception:
        return True
    finally:
        sock.close()


def find_process_on_port(port: int) -> str:
    """Intenta identificar que proceso tiene el puerto (Windows)."""
    try:
        import subprocess
        result = subprocess.run(
            ["netstat", "-ano"],
            capture_output=True, text=True, timeout=5,
        )
        for line in result.stdout.splitlines():
            if f":{port}" in line and "LISTENING" in line:
                parts = line.split()
                if len(parts) >= 5:
                    pid = parts[-1]
                    # Intentar obtener el nombre del proceso
                    try:
                        task = subprocess.run(
                            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                            capture_output=True, text=True, timeout=5,
                        )
                        proc_name = task.stdout.strip().split(",")[0].strip('"')
                        return f"PID {pid} ({proc_name})"
                    except Exception:
                        return f"PID {pid}"
    except Exception:
        pass
    return "proceso desconocido"


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8501

    print(f"Verificando puerto {port}...", end=" ")

    if check_port(port):
        print(f"LIBRE - OK")
        sys.exit(0)
    else:
        proc = find_process_on_port(port)
        print(f"OCUPADO por {proc}")
        print()
        print(f"Soluciones:")
        print(f"  1. Detener el proceso:  taskkill /PID <PID> /F")
        print(f"  2. Usar otro puerto:    python -m uvicorn frontend.server:app --port {port + 1}")
        print(f"  3. Docker con otro puerto: docker compose up -d --build  (editar ports en docker-compose.yml)")
        sys.exit(1)


if __name__ == "__main__":
    main()