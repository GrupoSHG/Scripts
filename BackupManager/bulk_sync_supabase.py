"""
bulk_sync_supabase.py
======================
Paso 5 del pipeline. Lee TODAS las pestañas del Excel multipestaña ya
generado por restaurar_y_extraer.py (mismo ultimo_excel.txt que usan los
demás pasos) y las replica en Supabase — una tabla Postgres por pestaña,
con el esquema de columnas (tipos) autodetectado desde el propio DataFrame.

Cada tabla se recrea completa en cada corrida (DROP + CREATE + COPY masivo).
Esto es correcto porque estas tablas son un ESPEJO de Manager (de solo
lectura para los dashboards), no datos maestros — no hace falta upsert
incremental por clave.

Todas las tablas se crean dentro del esquema Postgres SCHEMA_NAME (ver CONFIG),
en vez de depender del search_path por defecto de la conexión — así el destino
queda fijo en el código, sin importar cómo esté configurada la connection string.

EXCEPCIÓN: la pestaña 'NV_Proveedores' se salta a propósito — esa ya tiene
su propio script (sync_supabase.py) que hace upsert cuidadoso por RUT para
no perder el historial de OCs de la app OC Polchile.

Requiere:
pip install psycopg2-binary pandas openpyxl --break-system-packages

Variable de entorno requerida:
SUPABASE_DB_URL — connection string de Postgres (NO la REST API key) DEL
PROYECTO CONSOLIDADO (ffxopvzxyeacpbtxuagu). Se obtiene en Supabase →
ese proyecto → Project Settings → Database → Connection string (URI).
Ejemplo:
postgresql://postgres:TU_PASSWORD@db.ffxopvzxyeacpbtxuagu.supabase.co:5432/postgres
"""

import os
import re
import logging
from io import StringIO
from pathlib import Path

import pandas as pd
import psycopg2
from psycopg2 import sql

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────
SUPABASE_DB_URL = os.environ.get("SUPABASE_DB_URL")

# Esquema Postgres del proyecto consolidado donde viven todas las tablas
# que leen dashboard-produccion, cockpit-comercial y calendario-despachos.
SCHEMA_NAME = "shg_dashboards"

# Pestañas que NO se replican con este script genérico (tienen su propio
# manejo especial en otro lado).
# 'Productos_Stock' la maneja sync_stock_productos.py — va a stock_productos.stock
# (otro esquema, otra tabla, con upsert por fila) en vez de recrearse acá.
EXCLUIR_PESTANAS = {"NV_Proveedores", "NV_Supabase", "Productos_Stock"}

LOG_PATH = r"C:\Scripts\BackupManager\pipeline_main.log"
# ─────────────────────────────────────────────

log = logging.getLogger(__name__)

if not logging.getLogger().handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.FileHandler(LOG_PATH, encoding="utf-8"),
            logging.StreamHandler()
        ]
    )


def slugify_tabla(nombre: str) -> str:
    """Convierte 'Notas_de_venta' / 'Ordenes de Compra' -> 'notas_de_venta' / 'ordenes_de_compra'."""
    s = nombre.strip().lower()
    s = re.sub(r"[^\w]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s


def slugify_columna(nombre) -> str:
    """Convierte nombres de columna de pandas (pueden venir raros del SQL) a snake_case seguro para Postgres."""
    s = str(nombre).strip().lower()
    s = re.sub(r"[^\w]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    if not s or s[0].isdigit():
        s = "c_" + s
    return s


def tipo_postgres(dtype) -> str:
    """Mapea un dtype de pandas al tipo Postgres más apropiado."""
    nombre = str(dtype)
    if nombre.startswith("int"):
        return "BIGINT"
    if nombre.startswith("float"):
        return "DOUBLE PRECISION"
    if nombre.startswith("bool"):
        return "BOOLEAN"
    if nombre.startswith("datetime"):
        return "TIMESTAMP"
    return "TEXT"  # catch-all seguro: strings, objetos mixtos, etc.


def preparar_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Limpia nombres de columna y evita duplicados tras el slugify."""
    nuevas_cols = []
    vistas = {}
    for col in df.columns:
        base = slugify_columna(col)
        if base in vistas:
            vistas[base] += 1
            base = f"{base}_{vistas[base]}"
        else:
            vistas[base] = 0
        nuevas_cols.append(base)
    df = df.copy()
    df.columns = nuevas_cols
    return df


def asegurar_esquema(conn):
    """Crea el esquema SCHEMA_NAME si todavía no existe (no-op si ya está)."""
    with conn.cursor() as cur:
        cur.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(SCHEMA_NAME)))
    conn.commit()


def crear_tabla(conn, nombre_tabla: str, df: pd.DataFrame):
    """DROP + CREATE de la tabla dentro de SCHEMA_NAME, con columnas y tipos autodetectados.
    También habilita RLS + una política de lectura pública (SELECT), ya que
    la tabla se recrea desde cero en cada corrida y perdería cualquier
    configuración de seguridad hecha a mano en el dashboard de Supabase."""
    columnas_def = [
        sql.SQL("{} {}").format(sql.Identifier(col), sql.SQL(tipo_postgres(df[col].dtype)))
        for col in df.columns
    ]
    tabla_id = sql.Identifier(SCHEMA_NAME, nombre_tabla)
    with conn.cursor() as cur:
        cur.execute(sql.SQL("DROP TABLE IF EXISTS {}").format(tabla_id))
        cur.execute(
            sql.SQL("CREATE TABLE {} ({})").format(
                tabla_id,
                sql.SQL(", ").join(columnas_def)
            )
        )
        cur.execute(
            sql.SQL("ALTER TABLE {} ENABLE ROW LEVEL SECURITY").format(tabla_id)
        )
        cur.execute(
            sql.SQL("CREATE POLICY {} ON {} FOR SELECT USING (true)").format(
                sql.Identifier("lectura_publica_" + nombre_tabla),
                tabla_id
            )
        )
    conn.commit()


def cargar_datos_copy(conn, nombre_tabla: str, df: pd.DataFrame):
    """Carga masiva rápida vía COPY (mucho más veloz que INSERT fila por fila)."""
    if df.empty:
        log.info(f"  └─ {nombre_tabla}: sin filas, tabla queda vacía")
        return

    buffer = StringIO()
    # Reemplaza NaN/NaT por cadena vacía; COPY con NULL '' las interpreta como NULL real
    df_csv = df.copy()
    for col in df_csv.columns:
        if str(df_csv[col].dtype).startswith("datetime"):
            df_csv[col] = df_csv[col].dt.strftime("%Y-%m-%d %H:%M:%S")
    df_csv.to_csv(buffer, index=False, header=False, na_rep="")
    buffer.seek(0)

    tabla_id = sql.Identifier(SCHEMA_NAME, nombre_tabla)
    with conn.cursor() as cur:
        cur.copy_expert(
            sql.SQL("COPY {} FROM STDIN WITH (FORMAT csv, NULL '')").format(
                tabla_id
            ).as_string(conn),
            buffer
        )
    conn.commit()
    log.info(f"  └─ {nombre_tabla}: {len(df):,} filas cargadas")


def sincronizar_todo(ruta_excel: Path):
    if not SUPABASE_DB_URL:
        raise RuntimeError("Falta la variable de entorno SUPABASE_DB_URL (connection string de Postgres)")

    xls = pd.ExcelFile(ruta_excel)
    conn = psycopg2.connect(SUPABASE_DB_URL)

    resumen_ok = []
    resumen_error = []

    try:
        asegurar_esquema(conn)

        for nombre_pestana in xls.sheet_names:
            if nombre_pestana in EXCLUIR_PESTANAS:
                log.info(f"Saltando '{nombre_pestana}' (manejo especial aparte)")
                continue

            nombre_tabla = slugify_tabla(nombre_pestana)
            log.info(f"Procesando '{nombre_pestana}' → tabla '{SCHEMA_NAME}.{nombre_tabla}'...")

            try:
                df = pd.read_excel(ruta_excel, sheet_name=nombre_pestana)
                df = preparar_dataframe(df)
                crear_tabla(conn, nombre_tabla, df)
                cargar_datos_copy(conn, nombre_tabla, df)
                resumen_ok.append((nombre_tabla, len(df)))
            except Exception as e:
                conn.rollback()
                log.error(f"  └─ Error en '{nombre_pestana}': {e}")
                resumen_error.append((nombre_pestana, str(e)))
    finally:
        conn.close()

    log.info("")
    log.info(f"✅ Tablas cargadas correctamente: {len(resumen_ok)}")
    for tabla, filas in resumen_ok:
        log.info(f"   • {SCHEMA_NAME}.{tabla}: {filas:,} filas")
    if resumen_error:
        log.warning(f"⚠️ Tablas con error: {len(resumen_error)}")
        for pestana, err in resumen_error:
            log.warning(f"   • {pestana}: {err}")


def main():
    log.info("=" * 60)
    log.info(" CARGA MASIVA — Todas las consultas SQL → Supabase")
    log.info("=" * 60)

    excel_txt = Path("ultimo_excel.txt")
    if not excel_txt.exists():
        raise FileNotFoundError("No se encontró 'ultimo_excel.txt'. Ejecuta primero restaurar_y_extraer.py")

    ruta_excel = Path(excel_txt.read_text().strip())
    if not ruta_excel.exists():
        raise FileNotFoundError(f"El archivo Excel no existe: {ruta_excel}")

    log.info(f"Usando Excel: {ruta_excel.name}")
    sincronizar_todo(ruta_excel)

    log.info("✅ Carga masiva a Supabase completada.")


if __name__ == "__main__":
    main()