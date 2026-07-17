"""
test_execute_query.py - Prueba executeQueries contra un dataset de Power BI.

Consulta MAX('conceptos_facturados'[Actualizado_al]) en el dataset Facturacion.
Uso:  python -m scripts.test_execute_query
"""
from src.auth import obtener_token
from src.powerbi import consultar_tablero

WORKSPACE_ID = "8ac545a2-7e14-41a4-8029-9cba4e6ac469"
DATASET_ID = "c21a13af-ce21-452c-8ccd-b6e1db2ef242"
TABLA_DAX = "conceptos_facturados"
COLUMNA_DAX = "Actualizado_al"


def main() -> int:
    token = obtener_token()
    row = {
        "workspace_id": WORKSPACE_ID,
        "dataset_id": DATASET_ID,
        "tabla_dax": TABLA_DAX,
        "columna_dax": COLUMNA_DAX,
    }
    try:
        resultado = consultar_tablero(row, token)
        print("Consulta OK")
        print("Ultima actualizacion:", resultado)
        return 0
    except Exception as e:
        print("ERROR:", e)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())