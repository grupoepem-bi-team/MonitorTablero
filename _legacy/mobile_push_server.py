"""
HTTP mínimo para POST /api/mobile/register-push-token → `mobile_push_tokens.json`.

- Embebido: `app.py` (Streamlit) arranca un hilo daemon vía `ensure_embedded_server_started()`.
- Aislado: `python mobile_push_api.py` si no tenés Streamlit o preferís proceso dedicado.
"""
from __future__ import annotations

import errno
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse

import monitor_common as mc

REGISTER_PATH = "/api/mobile/register-push-token"

_embed_lock = threading.Lock()
_embed_started = False


def _env_embed_in_streamlit() -> bool:
    v = os.environ.get("MOBILE_PUSH_API_EMBED_IN_STREAMLIT", "1").strip().lower()
    return v not in ("0", "false", "no", "off")


class _ReusableHTTPServer(HTTPServer):
    allow_reuse_address = True


class PushRegisterHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        print(f"[MobilePushAPI] {args[0]}", flush=True)

    def _send_json(self, code: int, body: dict) -> None:
        raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(raw)

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Max-Age", "86400")
        self.end_headers()

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != REGISTER_PATH:
            self._send_json(404, {"ok": False, "error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0") or "0")
        except ValueError:
            length = 0
        if length > 2_000_000:
            self._send_json(413, {"ok": False, "error": "payload demasiado grande"})
            return
        raw_body = self.rfile.read(length) if length > 0 else b"{}"
        try:
            body = json.loads(raw_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._send_json(400, {"ok": False, "error": "JSON inválido"})
            return
        if not isinstance(body, dict):
            self._send_json(400, {"ok": False, "error": "el cuerpo debe ser un objeto JSON"})
            return
        ok, msg, _ = mc.registrar_token_push_desde_app(body)
        if ok:
            self._send_json(200, {"ok": True, "message": msg})
            return
        low = msg.lower()
        if "token" in low and "requerido" in low:
            self._send_json(400, {"ok": False, "error": msg})
            return
        self._send_json(500, {"ok": False, "error": msg})


def _bind_host_port() -> tuple[str, int]:
    host = (os.environ.get("MOBILE_PUSH_API_HOST") or "0.0.0.0").strip() or "0.0.0.0"
    try:
        port = int((os.environ.get("MOBILE_PUSH_API_PORT") or "8091").strip())
    except ValueError:
        port = 8091
    return host, port


def ensure_embedded_server_started() -> None:
    """
    Una vez por proceso. Llamar desde `app.py`. Si el puerto está ocupado, se asume
    otra instancia (p. ej. mobile_push_api.py) y no se reintenta.
    """
    global _embed_started
    if not _env_embed_in_streamlit():
        return
    with _embed_lock:
        if _embed_started:
            return
        host, port = _bind_host_port()
        try:
            server = _ReusableHTTPServer((host, port), PushRegisterHandler)
        except OSError as e:
            errn = getattr(e, "errno", None)
            # EADDRINUSE; en Windows suele ser 10048 (WSAEADDRINUSE).
            if errn == errno.EADDRINUSE or errn == 10048:
                print(
                    f"[MobilePushAPI] puerto {port} en uso; la API de registro ya está activa.",
                    flush=True,
                )
                _embed_started = True
                return
            print(f"[MobilePushAPI] no se pudo iniciar servidor embebido: {e}", flush=True)
            return
        threading.Thread(
            target=server.serve_forever,
            daemon=True,
            name="MobilePushAPI",
        ).start()
        _embed_started = True
        print(
            f"[MobilePushAPI] embebido (Streamlit) · http://{host}:{port}{REGISTER_PATH}",
            flush=True,
        )


def main() -> None:
    host, port = _bind_host_port()
    print(
        f"[MobilePushAPI] escuchando http://{host}:{port}{REGISTER_PATH}",
        flush=True,
    )
    _ReusableHTTPServer((host, port), PushRegisterHandler).serve_forever()


if __name__ == "__main__":
    main()
