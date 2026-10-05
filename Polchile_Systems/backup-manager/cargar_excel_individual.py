"""
cargar_excel_individual.py
============================
Carga UN Excel suelto a Supabase — para reportes individuales que no
forman parte del Excel multipestaña combinado del pipeline principal.

Reutiliza exactamente la misma lógica de bulk_sync_supabase.py: detecta
columnas y tipos automáticamente, recrea la tabla (DROP + CREATE), habilita
RLS + política de lectura pública, y carga los datos con COPY.

USO:
  python cargar_excel_individual.py "C:\\ruta\\mi_reporte.xlsx"
  python cargar_excel_individual.py "C:\\ruta\\mi_reporte.xlsx" nombre_tabla_custom

- Si el Excel tiene UNA sola pestaña: la tabla se llama como el archivo
  (o el nombre que le pases como segundo argumento).
- Si el Excel tiene VARIAS pestañas: se crea una tabla por pestaña,
  nombrada "<archivo>_<pestaña>" (o "<nombre_custom>_<pestaña>" si
  pasaste un nombre).

Requiere la misma variable de entorno que bulk_sync_supabase.py:
  SUPABASE_DB_URL
"""

import sys
import logging
from pathlib import Path

import pandas as pd
import psycopg2

# Reutiliza toda la lógica ya armada en bulk_sync_supabase.py
from bulk_sync_supabase import (
    slugify_tabla,
    preparar_dataframe,
    crear_tabla,
    cargar_datos_copy,
    SUPABASE_DB_URL,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
)
log = logging.getLogger(__name__)


def cargar_excel(ruta_excel: Path, nombre_base: str = None):
    if not SUPABASE_DB_URL:
        raise RuntimeError("Falta la variable de entorno SUPABASE_DB_URL")

    if not ruta_excel.exists():
        raise FileNotFoundError(f"No existe el archivo: {ruta_excel}")

    nombre_base = nombre_base or ruta_excel.stem

    xls = pd.ExcelFile(ruta_excel)
    conn = psycopg2.connect(SUPABASE_DB_URL)

    try:
        multi_pestana = len(xls.sheet_names) > 1

        for nombre_pestana in xls.sheet_names:
            if multi_pestana:
                nombre_tabla = slugify_tabla(f"{nombre_base}_{nombre_pestana}")
            else:
                nombre_tabla = slugify_tabla(nombre_base)

            log.info(f"Cargando pestaña '{nombre_pestana}' → tabla '{nombre_tabla}'...")

            df = pd.read_excel(ruta_excel, sheet_name=nombre_pestana)
            df = preparar_dataframe(df)
            crear_tabla(conn, nombre_tabla, df)
            cargar_datos_copy(conn, nombre_tabla, df)

            log.info(f"  └─ ✅ {nombre_tabla}: {len(df):,} filas cargadas")

    finally:
        conn.close()


def main():
    if len(sys.argv) < 2:
        print("Uso: python cargar_excel_individual.py <ruta_excel> [nombre_tabla]")
        sys.exit(1)

    ruta_excel = Path(sys.argv[1])
    nombre_base = sys.argv[2] if len(sys.argv) > 2 else None

    log.info("=" * 60)
    log.info(f"  CARGA INDIVIDUAL — {ruta_excel.name}")
    log.info("=" * 60)

    cargar_excel(ruta_excel, nombre_base)

    log.info("✅ Carga completada.")


if __name__ == "__main__":
    main()