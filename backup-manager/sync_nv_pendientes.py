"""
sync_nv_pendientes.py
======================
Sincroniza las NVs pendientes (con % de avance de producción vía OP)
a la tabla notas_venta_pendientes en Supabase, para el dashboard
de facturación/avance por vendedor.

Se conecta directamente a la BD ya restaurada por 01_restaurar_y_extraer.py
(mismo servidor y BD), sin depender de importar ese módulo.
"""

import logging
import os
import pyodbc
from decimal import Decimal
from supabase import create_client

log = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# CONFIGURACIÓN — misma que 01_restaurar_y_extraer.py
# ─────────────────────────────────────────────
SQL_SERVER = os.environ.get("SQL_SERVER", r"localhost\SQLEXPRESS")
# Mismo patrón que restaurar_y_extraer.py: local sigue usando autenticación
# de Windows sin tocar nada; en GitHub Actions se activa autenticación SQL
# (usuario 'sa' + password) vía estas 2 variables de entorno.
SQL_USE_SQL_AUTH = os.environ.get("SQL_USE_SQL_AUTH", "false").lower() == "true"
SQL_SA_PASSWORD = os.environ.get("SQL_SA_PASSWORD", "")
NOMBRE_BD = "T779354202C"
# ─────────────────────────────────────────────

# Proyecto consolidado (el mismo que usan dashboard-produccion, cockpit-comercial
# y calendario-despachos). Antes apuntaba al proyecto viejo "Grupo SHG Dashboards"
# (hauricnpsamnwyhondse) — corregido para que todo el pipeline escriba en un solo
# lugar y las apps dejen de ver datos desactualizados.
SUPABASE_URL = "https://ffxopvzxyeacpbtxuagu.supabase.co"
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")
SUPABASE_SCHEMA = "shg_dashboards"  # esquema donde viven todas las tablas del proyecto consolidado

QUERY = """
SET NOCOUNT ON;
SELECT
    nv.CODVEND AS codvend,
    o.PRP AS nota_venta,
    nv.TOTNETO AS monto_nv,
    SUM(CAST(o.CANTPP AS DECIMAL(18,6))) AS cantidad_total_op,
    SUM(CAST(o.CANTOK AS DECIMAL(18,6))) AS cantidad_terminada,
    SUM(CAST(o.CANTPP - o.CANTOK AS DECIMAL(18,6))) AS cantidad_pendiente,
    CASE WHEN SUM(o.CANTPP) = 0 THEN 0
         ELSE ROUND(SUM(o.CANTOK) * 100.0 / SUM(o.CANTPP), 1) END AS porcentaje_avance,
    CASE WHEN MAX(o.INICIADA) IS NOT NULL THEN 'En proceso' ELSE 'Sin iniciar' END AS estado
FROM dbo.ORDTR_DB o
LEFT JOIN dbo.NOTV_DB nv ON nv.NUMNOTA = o.PRP
WHERE o.FECHACREA >= CONVERT(datetime, '20180101', 112)
  AND o.FECHACREA <= CONVERT(datetime, '20301231', 112)
GROUP BY nv.CODVEND, o.PRP, nv.TOTNETO
HAVING SUM(o.CANTPP - o.CANTOK) > 0
ORDER BY nv.CODVEND, o.PRP
"""


def conectar_bd() -> pyodbc.Connection:
    if SQL_USE_SQL_AUTH:
        auth_clause = f"UID=sa;PWD={SQL_SA_PASSWORD};"
    else:
        auth_clause = "Trusted_Connection=yes;"
    conn_str = (
        f"DRIVER={{ODBC Driver 17 for SQL Server}};"
        f"SERVER={SQL_SERVER};DATABASE={NOMBRE_BD};{auth_clause}"
    )
    return pyodbc.connect(conn_str)


def _limpiar_para_json(filas):
    """Convierte Decimal (y otros tipos no serializables por json) a float/str."""
    limpias = []
    for fila in filas:
        nueva = {}
        for k, v in fila.items():
            if isinstance(v, Decimal):
                nueva[k] = float(v)
            else:
                nueva[k] = v
        limpias.append(nueva)
    return limpias


def main():
    if not SUPABASE_SERVICE_KEY:
        raise RuntimeError("Falta la variable de entorno SUPABASE_SERVICE_KEY")

    log.info("Conectando a '%s' para extraer NVs pendientes...", NOMBRE_BD)
    conn = conectar_bd()
    cursor = conn.cursor()
    cursor.execute(QUERY)
    columnas = [c[0].lower() for c in cursor.description]
    filas = [dict(zip(columnas, row)) for row in cursor.fetchall()]
    cursor.close()
    conn.close()

    if not filas:
        log.info("Sin NVs pendientes para sincronizar.")
        return

    filas = _limpiar_para_json(filas)

    supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY).schema(SUPABASE_SCHEMA)

    supabase.table("notas_venta_pendientes").upsert(
        filas, on_conflict="nota_venta"
    ).execute()

    nvs_actuales = [f["nota_venta"] for f in filas]
    supabase.table("notas_venta_pendientes") \
        .delete() \
        .not_.in_("nota_venta", nvs_actuales) \
        .execute()

    log.info("✅ Sincronizadas %d NVs pendientes en Supabase.", len(filas))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()