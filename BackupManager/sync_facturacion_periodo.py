"""
sync_facturacion_periodo.py
============================
Calcula la facturación de cada vendedor para el período vigente
(día 21 al día 20, móvil) y la sube a Supabase, acumulando
historial mensual (no borra períodos anteriores).
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

DECLARE @FechaRef DATETIME = GETDATE();
DECLARE @Inicio DATETIME, @Fin DATETIME;

IF DAY(@FechaRef) <= 20
BEGIN
    SET @Inicio = DATEADD(MONTH, -1, DATEFROMPARTS(YEAR(@FechaRef), MONTH(@FechaRef), 21));
    SET @Fin = DATEFROMPARTS(YEAR(@FechaRef), MONTH(@FechaRef), 20);
END
ELSE
BEGIN
    SET @Inicio = DATEFROMPARTS(YEAR(@FechaRef), MONTH(@FechaRef), 21);
    SET @Fin = DATEADD(MONTH, 1, DATEFROMPARTS(YEAR(@FechaRef), MONTH(@FechaRef), 20));
END

SELECT
    docu_db.CODVEND AS codvend,
    CAST(@Inicio AS DATE) AS periodo_inicio,
    CAST(@Fin AS DATE) AS periodo_fin,
    SUM(
        -- Las Notas de Crédito de Venta (TIPODOC=4) se RESTAN de la facturación,
        -- sin depender de si el ERP ya las guarda con cantidad/precio en negativo.
        (CASE WHEN docu_db.tipodoc = 4 THEN -1 ELSE 1 END)
        * ABS(docde_db.cantidad) *
        (((docde_db.precunit*tasacbio - ((docde_db.precunit*tasacbio - docde_db.precunit*tasacbio*(1-docde_db.descto/100))))
        * (1-docu_db.dctopje/100)))
    ) AS total_facturado

FROM docde_db
JOIN docu_db ON docu_db.numreg = docde_db.numrecor

WHERE docu_db.tipodoc IN (1, 3, 4, 79, 146)
  AND docu_db.fecha >= @Inicio
  AND docu_db.fecha <= @Fin

GROUP BY docu_db.CODVEND
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

    log.info("Conectando a '%s' para calcular facturación del período vigente...", NOMBRE_BD)
    conn = conectar_bd()
    cursor = conn.cursor()
    cursor.execute(QUERY)
    columnas = [c[0].lower() for c in cursor.description]
    filas = [dict(zip(columnas, row)) for row in cursor.fetchall()]
    cursor.close()
    conn.close()

    # Convertir fechas a string ISO para el upsert
    for f in filas:
        f["periodo_inicio"] = str(f["periodo_inicio"])
        f["periodo_fin"] = str(f["periodo_fin"])

    if not filas:
        log.info("Sin facturación para el período vigente.")
        return

    filas = _limpiar_para_json(filas)

    supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY).schema(SUPABASE_SCHEMA)

    # Upsert por (codvend, periodo_inicio) — NUNCA se borra historial,
    # solo se actualiza el período actual si se corre más de una vez
    # dentro del mismo período (ej. corre diario, refresca el acumulado).
    supabase.table("facturacion_periodo").upsert(
        filas, on_conflict="codvend,periodo_inicio"
    ).execute()

    log.info("✅ Facturación del período actualizada para %d vendedores.", len(filas))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()