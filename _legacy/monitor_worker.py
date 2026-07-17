"""
Proceso server-side: consulta Power BI, detecta cambios, alertas ntfy y escribe JSON
para que app.py (Streamlit) solo visualice.

Uso manual:
    python monitor_worker.py

Programar como servicio Windows (NSSM, etc.) apuntando a este script con el mismo
directorio de trabajo que el proyecto (donde está config_tableros.csv y token_cache.bin).
"""
from __future__ import annotations

import argparse
import sys

import monitor_common as mc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Monitor Power BI → JSON + ntfy")
    parser.add_argument(
        "--config",
        default=None,
        help="Ruta a config_tableros.csv (por defecto: junto a este proyecto)",
    )
    args = parser.parse_args(argv)

    ok, err = mc.ejecutar_corrida_monitor_con_manejo_error(args.config)
    if ok:
        meta = mc.leer_meta_corrida()
        print(
            "Corrida OK ·",
            meta.get("n_tableros", 0),
            "tableros ·",
            meta.get("n_cambios_estado", 0),
            "cambios de estado ·",
            f"{meta.get('duracion_s', 0)} s",
        )
        return 0
    print(f"Error: {err}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
