"""
subir_a_drive.py
=================
1. Sube el Excel completo a una carpeta de Drive (archivo de respaldo)
2. Actualiza hojas específicas en Google Sheets:
   - Base Produccion: Ordenes_de_produccion, Pendiente_a_facturar,
                      Vales_de_Salida, Ventas_Full, WIP
   - Presupuestos P&L 2026: Ventas_Full → hoja "Ventas Full Manager"

Usa cuenta de servicio — nunca expira.
Requiere: pip install google-auth google-api-python-client gspread pandas openpyxl
"""

import logging
from pathlib import Path

import pandas as pd
import gspread
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# ─────────────────────────────────────────────
#  CONFIG
# ─────────────────────────────────────────────
CREDENTIALS_FILE = r"C:\Users\atorr\Polchile\Credencialesbot.json"

# Carpeta Drive donde se sube el Excel completo de respaldo
DRIVE_FOLDER_ID  = "1AQgW1Mrr4MbBNi7yXA8kPNpjZBoo9Ntq"
NOMBRE_EN_DRIVE  = "Reportes_Completos_Actualizado.xlsx"

# IDs de los Google Sheets
ID_BASE_PRODUCCION = "10PvCCTw31gOhvSgcbIy15V3lBNdQZwX7Naa0R-yPO0k"
ID_PRESUPUESTOS    = "1sIoLlGRhmgPAny9rAatUBpw7ojTidjVuJppLMCzi8W8"

# Mapeo: nombre del reporte (igual al nombre del .sql sin extensión) → hoja en Base Produccion
MAPEO_BASE_PRODUCCION = {
    "Ordenes_de_produccion": "Orden de Produccion",
    "calendario":  "Por Facturar",
    "Inventario_aceros": "Control Inventario",
    "Notas_de_venta": "Notas de Venta",
    "Aceros":       "Vales de Salida",
    "Productos_Stock": "Stock",
    "Consumos_pol":"Consumos POL",
    "Ventas_Full":           "Ventas_Full",
    "WIP":                   "WIP",
    "Stock_vendido": "Stock Vendido",
    "Consumos_acero":"Consumos Acero",
    "Guias":"Guias"
}

# Mapeo adicional: reporte → (ID Sheets, nombre hoja)
MAPEO_ADICIONAL = {
    "Ventas_Full": (ID_PRESUPUESTOS, "Ventas Full Manager"),
    "Notas_de_venta": (ID_PRESUPUESTOS, "Notas de Venta"),
    "Cotizaciones":(ID_PRESUPUESTOS, "Cotizaciones"),
    "calendario":(ID_PRESUPUESTOS,"Calendario")
}

# Reportes que solo van al Excel de Drive (no a Sheets)
SOLO_DRIVE = {"base_completo", "Ordenes_de_Compra"}
# ─────────────────────────────────────────────

SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/spreadsheets",
]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    handlers=[
        logging.FileHandler(r"C:\Users\atorr\Documents\pipeline_ventas.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)


def autenticar():
    creds = service_account.Credentials.from_service_account_file(
        CREDENTIALS_FILE, scopes=SCOPES
    )
    drive_service  = build("drive", "v3", credentials=creds)
    sheets_service = build("sheets", "v4", credentials=creds)
    gc             = gspread.authorize(creds)
    return drive_service, sheets_service, gc


def subir_excel_drive(drive_service, ruta_excel: Path):
    """Sube el Excel completo a la carpeta de Drive como respaldo."""
    mime  = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    media = MediaFileUpload(str(ruta_excel), mimetype=mime, resumable=False)

    # Busca si ya existe
    query     = f"name='{NOMBRE_EN_DRIVE}' and '{DRIVE_FOLDER_ID}' in parents and trashed=false"
    resultado = drive_service.files().list(q=query, fields="files(id)", supportsAllDrives=True).execute()
    archivos  = resultado.get("files", [])

    if archivos:
        archivo_id = archivos[0]["id"]
        log.info(f"Actualizando Excel en Drive (ID: {archivo_id})...")
        drive_service.files().update(
            fileId=archivo_id,
            media_body=media,
            supportsAllDrives=True
        ).execute()
    else:
        log.info("Creando Excel nuevo en Drive...")
        metadata   = {"name": NOMBRE_EN_DRIVE, "parents": [DRIVE_FOLDER_ID]}
        file       = drive_service.files().create(
            body=metadata, media_body=media,
            fields="id", supportsAllDrives=True
        ).execute()
        archivo_id = file.get("id")

    log.info(f"✅ Excel subido a Drive: {NOMBRE_EN_DRIVE}")
    return archivo_id


def limpiar_y_escribir_hoja(gc, spreadsheet_id: str, nombre_hoja: str, df: pd.DataFrame):
    try:
        sh = gc.open_by_key(spreadsheet_id)
    except Exception as e:
        raise Exception(f"No se pudo abrir el Sheets {spreadsheet_id}: {e}")

    try:
        ws = sh.worksheet(nombre_hoja)
    except gspread.exceptions.WorksheetNotFound:
        log.warning(f"  Hoja '{nombre_hoja}' no encontrada, creándola...")
        ws = sh.add_worksheet(title=nombre_hoja, rows=1, cols=1)

    log.info(f"  Limpiando hoja '{nombre_hoja}'...")
    ws.clear()

    # Headers
    headers = df.columns.tolist()

    # Filas — mantiene números como números, limpia NaN, convierte fechas
    filas = []
    for _, row in df.iterrows():
        fila = []
        for val in row:
            if val is None:
                fila.append("")
            elif isinstance(val, float) and val != val:  # NaN
                fila.append("")
            elif str(val) in ("nan", "NaT", "None", "nat", "<NA>"):
                fila.append("")
            elif hasattr(val, 'strftime'):  # datetime / Timestamp → string
                try:
                    if hasattr(val, 'hour') and (val.hour or val.minute or val.second):
                        fila.append(val.strftime("%Y-%m-%d %H:%M:%S"))
                    else:
                        fila.append(val.strftime("%Y-%m-%d"))
                except Exception:
                    fila.append(str(val))
            elif hasattr(val, 'item'):  # numpy types → Python nativo
                fila.append(val.item())
            else:
                fila.append(val)
        filas.append(fila)

    data = [headers] + filas

    log.info(f"  Escribiendo {len(df):,} filas en '{nombre_hoja}'...")
    ws.update(data, value_input_option="RAW")
    log.info(f"  ✅ Hoja '{nombre_hoja}' actualizada.")


def actualizar_sheets(gc, ruta_excel: Path):
    """Lee el Excel generado y actualiza las hojas correspondientes en Sheets."""
    log.info("Leyendo Excel para actualizar Google Sheets...")

    # Lee todas las pestañas del Excel
    xls = pd.ExcelFile(ruta_excel)
    hojas_excel = xls.sheet_names
    log.info(f"Pestañas encontradas en Excel: {hojas_excel}")

    for nombre_reporte, nombre_hoja_sheets in MAPEO_BASE_PRODUCCION.items():
        # Busca la pestaña en el Excel (puede tener hasta 31 chars por límite de Excel)
        nombre_pestana = nombre_reporte[:31]

        if nombre_pestana not in hojas_excel:
            log.warning(f"  Pestaña '{nombre_pestana}' no encontrada en el Excel, saltando...")
            continue

        df = pd.read_excel(ruta_excel, sheet_name=nombre_pestana)
        log.info(f"Actualizando Base Produccion → '{nombre_hoja_sheets}' ({len(df):,} filas)...")
        limpiar_y_escribir_hoja(gc, ID_BASE_PRODUCCION, nombre_hoja_sheets, df)

    # Mapeos adicionales (Ventas_Full → Presupuestos)
    for nombre_reporte, (sheet_id, nombre_hoja) in MAPEO_ADICIONAL.items():
        nombre_pestana = nombre_reporte[:31]

        if nombre_pestana not in hojas_excel:
            log.warning(f"  Pestaña '{nombre_pestana}' no encontrada en el Excel, saltando...")
            continue

        df = pd.read_excel(ruta_excel, sheet_name=nombre_pestana)
        log.info(f"Actualizando Presupuestos → '{nombre_hoja}' ({len(df):,} filas)...")
        limpiar_y_escribir_hoja(gc, sheet_id, nombre_hoja, df)


def main():
    log.info("=" * 55)
    log.info("  PASO 2 — Subir a Drive y actualizar Google Sheets")
    log.info("=" * 55)

    excel_txt = Path("ultimo_excel.txt")
    if not excel_txt.exists():
        raise FileNotFoundError("No se encontró 'ultimo_excel.txt'. Ejecuta primero restaurar_y_extraer.py")

    ruta_excel = Path(excel_txt.read_text().strip())
    if not ruta_excel.exists():
        raise FileNotFoundError(f"El archivo Excel no existe: {ruta_excel}")

    log.info(f"Procesando: {ruta_excel.name} ({ruta_excel.stat().st_size/1e6:.1f} MB)")

    drive_service, sheets_service, gc = autenticar()

    # 1. Sube el Excel completo a Drive
    subir_excel_drive(drive_service, ruta_excel)

    # 2. Actualiza hojas en Google Sheets
    actualizar_sheets(gc, ruta_excel)

    log.info("")
    log.info("✅ Todo actualizado:")
    log.info(f"   📁 Drive: {NOMBRE_EN_DRIVE}")
    log.info(f"   📊 Base Produccion: {list(MAPEO_BASE_PRODUCCION.values())}")
    log.info(f"   📊 Presupuestos: Ventas Full Manager")


if __name__ == "__main__":
    main()