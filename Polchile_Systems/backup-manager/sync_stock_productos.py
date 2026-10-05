"""
sync_stock_productos.py
========================
Paso del pipeline dedicado a mantener al día stock_productos.stock en
Supabase — la tabla que lee la app "Control de Stock por Familias".

A diferencia de bulk_sync_supabase.py (que recrea tablas completas como
espejo de solo lectura), esta tabla usa UPSERT fila por fila, porque el
front la lee agrupando por familia/bodega y necesita saber CUÁNDO se
actualizó cada fila individualmente (columna `actualizado`), no solo
cuándo corrió la última sincronización completa.

Lee la pestaña 'Productos_Stock' del mismo Excel multipestaña que ya
generó restaurar_y_extraer.py (mismo ultimo_excel.txt que usan los demás
pasos) — no abre una conexión aparte a SQL Server.

Clave de upsert: (codigo, bodega_nombre) — un mismo código de producto
puede existir en varias bodegas a la vez (visto en los datos reales:
PA304650STKL6 en LOS PALTOS y en TRINIDAD con stocks distintos), así que
el código solo no alcanza como clave única.

Requiere:
pip install psycopg2-binary pandas openpyxl --break-system-packages

Variable de entorno requerida:
SUPABASE_DB_URL — connection string de Postgres del proyecto consolidado
(ffxopvzxyeacpbtxuagu), igual que los demás scripts de BackupManager.
"""

import os
import logging
from pathlib import Path

import pandas as pd
import psycopg2
from psycopg2 import sql
from psycopg2.extras import execute_values

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────
SUPABASE_DB_URL = os.environ.get("SUPABASE_DB_URL")

SCHEMA_NAME = "stock_productos"
TABLE_NAME = "stock"
PESTANA_EXCEL = "Productos_Stock"

# Columnas que vienen de Productos_Stock.sql, en el orden que las produce
# la consulta (ver ConsultasSQL/Productos_Stock.sql):
#   bodega, bodega_nombre, codigo, nombre, unidmed, stk_fisico
# La tabla destino no tiene columna 'bodega' (código de bodega), solo
# 'bodega_nombre' — así que esa columna del SQL se descarta acá.

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


def preparar_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Normaliza nombres de columna a los que espera stock_productos.stock
    y descarta lo que esa tabla no guarda (código de bodega)."""
    df = df.copy()
    df.columns = [str(c).strip().lower() for c in df.columns]

    columnas_esperadas = {"bodega_nombre", "codigo", "nombre", "unidmed", "stk_fisico"}
    faltantes = columnas_esperadas - set(df.columns)
    if faltantes:
        raise RuntimeError(
            f"Faltan columnas esperadas en la pestaña '{PESTANA_EXCEL}': {faltantes}. "
            f"¿Cambió Productos_Stock.sql? Columnas disponibles: {list(df.columns)}"
        )

    df = df[["codigo", "bodega_nombre", "nombre", "unidmed", "stk_fisico"]]

    # Limpieza básica: sin código no hay fila válida que upsertear
    df = df.dropna(subset=["codigo", "bodega_nombre"])
    df["codigo"] = df["codigo"].astype(str).str.strip()
    df["bodega_nombre"] = df["bodega_nombre"].astype(str).str.strip()
    df["nombre"] = df["nombre"].astype(str).str.strip()
    df["unidmed"] = df["unidmed"].astype(str).str.strip()
    df["stk_fisico"] = pd.to_numeric(df["stk_fisico"], errors="coerce").fillna(0)

    return df


def asegurar_tabla(conn):
    """Crea el esquema/tabla si todavía no existen (no-op si ya están).
    No hace DROP nunca — esta tabla vive vía upsert, no recreación."""
    with conn.cursor() as cur:
        cur.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(SCHEMA_NAME)))
        cur.execute(
            sql.SQL("""
                CREATE TABLE IF NOT EXISTS {} (
                    codigo TEXT NOT NULL,
                    bodega_nombre TEXT NOT NULL,
                    nombre TEXT,
                    unidmed TEXT,
                    stk_fisico NUMERIC,
                    actualizado TIMESTAMPTZ NOT NULL DEFAULT now(),
                    PRIMARY KEY (codigo, bodega_nombre)
                )
            """).format(sql.Identifier(SCHEMA_NAME, TABLE_NAME))
        )
    conn.commit()


def upsert_stock(conn, df: pd.DataFrame):
    """UPSERT por (codigo, bodega_nombre): cada fila que viene en esta
    corrida queda con su propio 'actualizado' = ahora. Al final se borran
    las combinaciones (codigo, bodega_nombre) que ya NO vinieron en el
    Excel — esta tabla es un espejo de Manager, no un historial, así que
    un producto sin stock real no debe quedar mostrando el último valor
    que tuvo."""
    if df.empty:
        log.warning("  └─ Productos_Stock: 0 filas en el Excel, no se actualiza nada")
        return

    filas = list(df.itertuples(index=False, name=None))
    tabla_id = sql.Identifier(SCHEMA_NAME, TABLE_NAME).as_string(conn)

    query = f"""
        INSERT INTO {tabla_id} (codigo, bodega_nombre, nombre, unidmed, stk_fisico, actualizado)
        VALUES %s
        ON CONFLICT (codigo, bodega_nombre) DO UPDATE SET
            nombre = EXCLUDED.nombre,
            unidmed = EXCLUDED.unidmed,
            stk_fisico = EXCLUDED.stk_fisico,
            actualizado = now()
    """
    with conn.cursor() as cur:
        execute_values(
            cur, query, filas,
            template="(%s, %s, %s, %s, %s, now())"
        )
    conn.commit()
    log.info(f"  └─ {SCHEMA_NAME}.{TABLE_NAME}: {len(df):,} filas upserteadas")

    # Borra lo que ya no vino en esta corrida (producto/bodega sin stock real)
    #
    # FIX: el pooler de Supabase (PgBouncer/Supavisor) puede reciclar la
    # misma sesión de Postgres entre corridas distintas de este script
    # (sobre todo en runners de GitHub Actions, que abren conexiones
    # nuevas seguido) — así que una tabla temporal creada en una corrida
    # anterior puede seguir "viva" para la sesión que nos toca esta vez.
    # DROP IF EXISTS antes de crearla asegura que siempre partamos de
    # cero, sin depender de que la sesión de Postgres sea nueva.
    claves = [(codigo, bodega) for codigo, bodega, *_ in filas]
    with conn.cursor() as cur:
        cur.execute(sql.SQL("DROP TABLE IF EXISTS _claves_vigentes"))
        cur.execute(
            sql.SQL("CREATE TEMP TABLE _claves_vigentes (codigo TEXT, bodega_nombre TEXT)")
        )
        execute_values(
            cur,
            "INSERT INTO _claves_vigentes (codigo, bodega_nombre) VALUES %s",
            claves
        )
        cur.execute(
            sql.SQL("""
                DELETE FROM {} t
                WHERE NOT EXISTS (
                    SELECT 1 FROM _claves_vigentes v
                    WHERE v.codigo = t.codigo AND v.bodega_nombre = t.bodega_nombre
                )
            """).format(sql.Identifier(SCHEMA_NAME, TABLE_NAME))
        )
        borradas = cur.rowcount
        # Limpieza explícita al final también, para no dejarla ni siquiera
        # para el resto de esta misma sesión (por si el pooler la reutiliza
        # para otro script del pipeline que corra después, en la misma
        # conexión).
        cur.execute(sql.SQL("DROP TABLE IF EXISTS _claves_vigentes"))
    conn.commit()
    if borradas:
        log.info(f"  └─ {SCHEMA_NAME}.{TABLE_NAME}: {borradas:,} filas obsoletas eliminadas (sin stock ya / bodega distinta)")


def sincronizar(ruta_excel: Path):
    if not SUPABASE_DB_URL:
        raise RuntimeError("Falta la variable de entorno SUPABASE_DB_URL (connection string de Postgres)")

    xls = pd.ExcelFile(ruta_excel)
    if PESTANA_EXCEL not in xls.sheet_names:
        raise RuntimeError(
            f"No se encontró la pestaña '{PESTANA_EXCEL}' en el Excel. "
            f"Pestañas disponibles: {xls.sheet_names}"
        )

    df = pd.read_excel(ruta_excel, sheet_name=PESTANA_EXCEL)
    df = preparar_dataframe(df)

    conn = psycopg2.connect(SUPABASE_DB_URL)
    try:
        asegurar_tabla(conn)
        upsert_stock(conn, df)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def main():
    log.info("=" * 60)
    log.info(" SYNC — Productos_Stock → stock_productos.stock (Supabase)")
    log.info("=" * 60)

    excel_txt = Path("ultimo_excel.txt")
    if not excel_txt.exists():
        raise FileNotFoundError("No se encontró 'ultimo_excel.txt'. Ejecuta primero restaurar_y_extraer.py")

    ruta_excel = Path(excel_txt.read_text().strip())
    if not ruta_excel.exists():
        raise FileNotFoundError(f"El archivo Excel no existe: {ruta_excel}")

    log.info(f"Usando Excel: {ruta_excel.name}")
    sincronizar(ruta_excel)

    log.info("✅ Sync de stock_productos.stock completado.")


if __name__ == "__main__":
    main()
