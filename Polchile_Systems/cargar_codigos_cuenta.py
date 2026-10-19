"""Carga el calce código de artículo → cuenta contable en shg_dashboards.codigos_cuenta
desde el export "artículos y cuentas" de Manager (Excel o CSV).

Columnas que reconoce (export estándar de Manager, oct-2026):
  codigo       código del artículo                      → codigo_item
  art_ctacom   cuenta contable de compra                → cuenta  (la que usa el detalle de facturas)
  art_ctavta   cuenta de venta                          → cuenta_venta
  art_ctacto   cuenta de costo                          → cuenta_costo
Las demás columnas (art_ctatom, art_ctaop, centros de costo, dato1..5) se ignoran.
Un valor '0' o vacío se trata como "sin cuenta"; las filas sin cuenta de compra se saltan.

Uso:
  python3 Polchile_Systems/cargar_codigos_cuenta.py <archivo.xlsx|.xls|.csv> [--empresa polchile] [--simular]

Requiere SUPABASE_SERVICE_KEY (en .env o en el entorno). Para .xlsx usa openpyxl; para .xls, xlrd.
Volver a cargar actualiza las cuentas de los códigos que ya existen (upsert) y respeta las
asignaciones hechas desde la pantalla solo si el export trae la misma cuenta: la última
carga gana, así que conviene exportar desde Manager después de corregir ahí.
"""
import csv
import io
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

SUPABASE_URL = "https://ffxopvzxyeacpbtxuagu.supabase.co"
SCHEMA = "shg_dashboards"
LOTE = 500
COLUMNAS = {"codigo": "codigo_item", "art_ctacom": "cuenta", "art_ctavta": "cuenta_venta", "art_ctacto": "cuenta_costo"}


def leer_filas(ruta):
    ext = os.path.splitext(ruta)[1].lower()
    if ext == ".csv":
        with io.open(ruta, encoding="utf-8-sig", newline="") as f:
            muestra = f.read(4096); f.seek(0)
            try:
                dialecto = csv.Sniffer().sniff(muestra, delimiters=";,\t")
            except csv.Error:
                dialecto = csv.excel
            return [list(r) for r in csv.reader(f, dialecto)]
    if ext in (".xlsx", ".xlsm"):
        import openpyxl
        wb = openpyxl.load_workbook(ruta, read_only=True, data_only=True)
        return [list(r) for r in wb.worksheets[0].iter_rows(values_only=True)]
    if ext == ".xls":
        import xlrd
        ws = xlrd.open_workbook(ruta).sheet_by_index(0)
        return [ws.row_values(i) for i in range(ws.nrows)]
    raise SystemExit(f"Formato no soportado: {ext}")


def limpiar(v):
    if v is None:
        return None
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    s = str(v).strip()
    return None if s in ("", "0", "0.0", "None") else s


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        raise SystemExit(__doc__)
    ruta = args[0]
    empresa = sys.argv[sys.argv.index("--empresa") + 1] if "--empresa" in sys.argv else "polchile"
    simular = "--simular" in sys.argv

    filas = leer_filas(ruta)
    hdr = [str(h or "").strip().lower() for h in filas[0]]
    faltan = [c for c in ("codigo", "art_ctacom") if c not in hdr]
    if faltan:
        raise SystemExit(f"El archivo no trae las columnas {faltan}; encabezado leído: {hdr}")
    idx = {destino: hdr.index(origen) for origen, destino in COLUMNAS.items() if origen in hdr}

    ahora = datetime.now(timezone.utc).isoformat()
    filas_out, sin_cuenta, vistos = [], 0, set()
    for fila in filas[1:]:
        def celda(campo):
            j = idx.get(campo)
            return limpiar(fila[j]) if j is not None and j < len(fila) else None
        codigo = celda("codigo_item")
        cuenta = celda("cuenta")
        if not codigo or codigo in vistos:
            continue
        vistos.add(codigo)
        if not cuenta:
            sin_cuenta += 1
            continue
        filas_out.append({
            "empresa": empresa, "codigo_item": codigo, "cuenta": cuenta,
            "cuenta_venta": celda("cuenta_venta"), "cuenta_costo": celda("cuenta_costo"),
            "actualizado_por": "manager-export", "actualizado_en": ahora,
        })
    import collections
    resumen = collections.Counter(f["cuenta"] for f in filas_out)
    print(f"Archivo {os.path.basename(ruta)}: {len(filas) - 1} filas, {len(filas_out)} códigos con cuenta de compra, "
          f"{sin_cuenta} sin cuenta (se saltan)")
    print("Cuentas de compra más usadas: " + ", ".join(f"{c} ({n})" for c, n in resumen.most_common(8)))
    for f in filas_out[:5]:
        print(f"  {f['codigo_item']:<22} compra {f['cuenta']}  venta {f['cuenta_venta'] or '-'}  costo {f['cuenta_costo'] or '-'}")
    if simular or not filas_out:
        return

    key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not key:
        raise SystemExit("Falta SUPABASE_SERVICE_KEY")
    headers = {"apikey": key, "Authorization": "Bearer " + key, "Content-Type": "application/json",
               "Accept-Profile": SCHEMA, "Content-Profile": SCHEMA,
               "Prefer": "resolution=merge-duplicates,return=minimal"}
    for i in range(0, len(filas_out), LOTE):
        req = urllib.request.Request(f"{SUPABASE_URL}/rest/v1/codigos_cuenta?on_conflict=empresa,codigo_item",
                                     method="POST", headers=headers,
                                     data=json.dumps(filas_out[i:i + LOTE], ensure_ascii=False).encode("utf-8"))
        try:
            with urllib.request.urlopen(req, timeout=120):
                pass
        except urllib.error.HTTPError as e:
            raise SystemExit(f"Supabase HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:500]}")
        print(f"  {min(i + LOTE, len(filas_out))}/{len(filas_out)} cargados")
    print(f"Listo: {len(filas_out)} códigos de {empresa} en {SCHEMA}.codigos_cuenta")


if __name__ == "__main__":
    main()
