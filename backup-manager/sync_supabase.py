"""
sync_proveedores.py
====================
Paso 5 del pipeline diario. Lee la pestaña 'NV_Proveedores' del Excel ya generado
por restaurar_y_extraer.py (query dedicada: ConsultasSQL/NV_Proveedores.sql) y
sincroniza los proveedores reales de Manager (TIPO IN (2,3) AND IMPUTABLE = 1,
confirmado cruzando contra OC_DB.NRUTPROV) hacia la tabla `proveedores` de
Supabase, usada por la app OC Polchile.

Comportamiento (upsert manual por RUT, NO reemplazo total):
- Proveedor nuevo (RUT no existe en Supabase)  -> se inserta
- Proveedor existente (mismo RUT)              -> se actualiza nombre/dirección/
                                                    ciudad/comuna/teléfono
                                                    (no se toca su historial de OCs)

Requiere que la tabla `proveedores` tenga UNIQUE(rut) — ver 02_migracion_rut_unique.sql,
ejecutar UNA VEZ en el SQL Editor de Supabase antes de correr este script.

Se ejecuta como Paso 5, después de sync_supabase.py (NVs), leyendo el mismo Excel
que ya generó el Paso 2 (ultimo_excel.txt). No abre ninguna conexión nueva a SQL Server.

Requiere: pip install supabase pandas openpyxl --break-system-packages
"""

import os
import logging
from pathlib import Path

import pandas as pd
from supabase import create_client

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────
# Proyecto consolidado (el mismo que usan dashboard-produccion, cockpit-comercial
# y calendario-despachos). Antes apuntaba al proyecto viejo "Grupo SHG Dashboards"
# (hauricnpsamnwyhondse) — corregido para que todo el pipeline escriba en un solo
# lugar y las apps dejen de ver datos desactualizados.
SUPABASE_URL = "https://ffxopvzxyeacpbtxuagu.supabase.co"
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")  # Service Role key, NUNCA la publishable
SUPABASE_SCHEMA = "shg_dashboards"  # esquema donde viven todas las tablas del proyecto consolidado

NOMBRE_PESTANA = "NV_Proveedores"  # debe calzar con el nombre del .sql en ConsultasSQL/ (sin extensión)

LOG_PATH = os.environ.get("PIPELINE_MAIN_LOG", r"C:\Scripts\BackupManager\pipeline_main.log")  # mismo log que el orquestador principal
# ─────────────────────────────────────────────

log = logging.getLogger(__name__)

# Si este módulo se ejecuta suelto (no importado por el orquestador), configura su propio logging.
if not logging.getLogger().handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.FileHandler(LOG_PATH, encoding="utf-8"),
            logging.StreamHandler()
        ]
    )


def leer_proveedores_desde_excel() -> pd.DataFrame:
    """Lee la pestaña NV_Proveedores del Excel que ya generó el Paso 2."""
    excel_txt = Path("ultimo_excel.txt")
    if not excel_txt.exists():
        raise FileNotFoundError("No se encontró 'ultimo_excel.txt'. Ejecuta primero restaurar_y_extraer.py")

    ruta_excel = Path(excel_txt.read_text().strip())
    if not ruta_excel.exists():
        raise FileNotFoundError(f"El archivo Excel no existe: {ruta_excel}")

    xls = pd.ExcelFile(ruta_excel)
    nombre_pestana = NOMBRE_PESTANA[:31]
    if nombre_pestana not in xls.sheet_names:
        raise ValueError(f"Pestaña '{nombre_pestana}' no encontrada en {ruta_excel.name}. "
                          f"Pestañas disponibles: {xls.sheet_names}")

    df = pd.read_excel(ruta_excel, sheet_name=nombre_pestana)
    log.info(f"Leídas {len(df):,} filas de la pestaña '{nombre_pestana}'")
    return df


def _a_texto(v):
    """Las columnas de proveedores son text. NaN no se puede mandar en JSON, y en
    columnas numéricas (ej. teléfono) pandas vuelve a convertir None en NaN; por
    eso cada valor se pasa a str (o None) uno por uno."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    if isinstance(v, float) and v.is_integer():
        return str(int(v))          # 22334455.0 -> "22334455"
    return str(v).strip() or None


def normalizar_proveedores(df: pd.DataFrame) -> pd.DataFrame:
    """Limpia nulos y descarta filas sin RUT (no se puede hacer match sin RUT)."""
    df = df[df["rut"].notna()].copy()
    cols = ["rut", "nombre", "direccion", "ciudad", "comuna", "telefono", "email"]
    df = df[cols].astype(object)
    return df


def sincronizar_a_supabase(df: pd.DataFrame):
    if not SUPABASE_KEY:
        raise RuntimeError("Falta la variable de entorno SUPABASE_SERVICE_KEY")

    sb = create_client(SUPABASE_URL, SUPABASE_KEY).schema(SUPABASE_SCHEMA)

    existentes = sb.table("proveedores").select("rut").execute().data
    ruts_existentes = {row["rut"] for row in existentes if row["rut"]}

    nuevos = 0
    actualizados = 0
    errores = 0

    for _, fila in df.iterrows():
        # Se limpia al armar el envío: iterrows() vuelve a convertir los None en NaN.
        row = {k: _a_texto(fila[k]) for k in df.columns}
        payload = {
            "rut": row["rut"],
            "nombre": row["nombre"],
            "direccion": row["direccion"],
            "ciudad": row["ciudad"],
            "comuna": row["comuna"],
            "telefono": row["telefono"],
            "email": row["email"],
        }
        try:
            if row["rut"] in ruts_existentes:
                sb.table("proveedores").update({
                    "nombre": payload["nombre"],
                    "direccion": payload["direccion"],
                    "ciudad": payload["ciudad"],
                    "comuna": payload["comuna"],
                    "telefono": payload["telefono"],
                    "email": payload["email"],
                }).eq("rut", row["rut"]).execute()
                actualizados += 1
            else:
                sb.table("proveedores").insert(payload).execute()
                nuevos += 1
        except Exception as e:
            errores += 1
            log.error(f"Error sincronizando proveedor RUT {row['rut']}: {e}")

    log.info(f"Sync proveedores completa. Nuevos: {nuevos} | Actualizados: {actualizados} | Errores: {errores}")


def main():
    log.info("PASO 5 — Sincronizar proveedores a Supabase (OC Polchile)")

    df_raw = leer_proveedores_desde_excel()
    df = normalizar_proveedores(df_raw)
    log.info(f"Proveedores a sincronizar: {len(df):,}")

    sincronizar_a_supabase(df)

    log.info("✅ Sync proveedores → Supabase completado.")


if __name__ == "__main__":
    main()