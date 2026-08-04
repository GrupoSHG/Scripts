"""
00_pipeline_completo.py
========================
Orquestador principal. Ejecuta en orden:
    1. Descargar .bak desde Manager
    2. Restaurar en SQL Server y extraer Ventas Full a Excel
    3. Subir Excel a Google Drive
    4. Sincronizar NVs aprobadas a Supabase (app OC Polchile)
    5. Carga masiva de todas las tablas a Supabase
    6. Sincronizar NVs pendientes por vendedor (dashboard vendedores)
    7. Sincronizar facturación por período (21-20) por vendedor

Uso: python 00_pipeline_completo.py
"""

import os
import logging
import sys
import traceback
from datetime import datetime
from pathlib import Path

# En tu notebook, sigue escribiendo en la ruta de siempre si no seteas la
# variable de entorno. En GitHub Actions, el workflow la apunta a un
# archivo relativo (dentro de BackupManager/, que ya es el working-directory).
PIPELINE_MAIN_LOG = os.environ.get("PIPELINE_MAIN_LOG", r"C:\Scripts\BackupManager\pipeline_main.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    handlers=[
        logging.FileHandler(PIPELINE_MAIN_LOG, encoding="utf-8"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)


def paso(numero: int, nombre: str):
    log.info("")
    log.info("━" * 55)
    log.info(f"  PASO {numero}/7 — {nombre}")
    log.info("━" * 55)


def main():
    inicio = datetime.now()
    log.info("╔" + "═" * 53 + "╗")
    log.info("║   PIPELINE VENTAS FULL — Inicio: " + inicio.strftime("%Y-%m-%d %H:%M") + "   ║")
    log.info("╚" + "═" * 53 + "╝")

    try:
        # ── PASO 1: Descargar .bak ─────────────────────────────
        paso(1, "Descargar backup desde Manager")
        from descargar_backup_manager import main as descargar
        descargar()

        # ── PASO 2: Restaurar BD y extraer Excel ───────────────
        paso(2, "Restaurar BD y extraer Ventas Full")
        from restaurar_y_extraer import main as restaurar
        restaurar()

        # ── PASO 3: Subir a Google Drive ───────────────────────
        paso(3, "Subir Excel a Google Drive")
        from subir_a_drive import main as subir
        subir()

        # ── PASO 4: Sincronizar NVs a Supabase (OC Polchile) ───
        paso(4, "Sincronizar NVs a Supabase (OC Polchile)")
        from sync_supabase import main as sync_nv
        sync_nv()

        # ── PASO 5: Carga masiva de todas las tablas a Supabase ─
        paso(5, "Carga masiva a Supabase (todas las tablas)")
        from bulk_sync_supabase import main as bulk_sync
        bulk_sync()


        # ── PASO 6: Sincronizar NVs pendientes por vendedor ────
        paso(6, "Sincronizar NVs pendientes por vendedor")
        from sync_nv_pendientes import main as sync_pendientes
        sync_pendientes()

        # ── PASO 7: Sincronizar facturación por período (21-20) ─
        paso(7, "Sincronizar facturación por período (21-20)")
        from sync_facturacion_periodo import main as sync_facturacion
        sync_facturacion()

        # ── Resumen ────────────────────────────────────────────
        duracion = (datetime.now() - inicio).seconds
        log.info("")
        log.info("╔" + "═" * 53 + "╗")
        log.info(f"║  ✅ PIPELINE COMPLETADO en {duracion}s".ljust(54) + "║")
        log.info(f"║  📊 Excel en Drive: VentasFull_Actualizado.xlsx".ljust(54) + "║")
        log.info(f"║  🔄 NVs sincronizadas en Supabase (OC Polchile)".ljust(54) + "║")
        log.info(f"║  🔄 NVs pendientes sincronizadas por vendedor".ljust(54) + "║")
        log.info(f"║  🔄 Facturación por período sincronizada".ljust(54) + "║")
        log.info("╚" + "═" * 53 + "╝")

    except Exception as e:
        log.error("")
        log.error("╔" + "═" * 53 + "╗")
        log.error("║  ❌ PIPELINE FALLÓ".ljust(54) + "║")
        log.error(f"║  Error: {str(e)[:44]}".ljust(54) + "║")
        log.error("╚" + "═" * 53 + "╝")
        log.error(traceback.format_exc())
        sys.exit(1)


if __name__ == "__main__":
    main()