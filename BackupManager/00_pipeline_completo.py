"""
00_pipeline_completo.py
========================
Orquestador principal. Ejecuta en orden:
    1. Descargar .bak desde Manager
    2. Restaurar en SQL Server y extraer Ventas Full a Excel
    3. Subir Excel a Google Drive

Uso: python 00_pipeline_completo.py
"""

import logging
import sys
import traceback
from datetime import datetime
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    handlers=[
        logging.FileHandler(r"C:\Scripts\BackupManager\pipeline_main.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)


def paso(numero: int, nombre: str):
    log.info("")
    log.info("━" * 55)
    log.info(f"  PASO {numero}/3 — {nombre}")
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

        # ── Resumen ────────────────────────────────────────────
        duracion = (datetime.now() - inicio).seconds
        log.info("")
        log.info("╔" + "═" * 53 + "╗")
        log.info(f"║  ✅ PIPELINE COMPLETADO en {duracion}s".ljust(54) + "║")
        log.info(f"║  📊 Excel en Drive: VentasFull_Actualizado.xlsx".ljust(54) + "║")
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
