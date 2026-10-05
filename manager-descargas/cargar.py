"""Carga los informes exportados de Manager (.xls) a Supabase.

  python cargar.py ventas_full    ruta\\...-NOMBREVF.xls
  python cargar.py notas_de_venta ruta\\...-NOMBRENVS.xls
  python cargar.py ... --simular   (solo convierte y muestra un resumen, no sube)

El reemplazo es atómico: la función shg_dashboards.reemplazar_<tabla> borra e
inserta en una sola transacción, así los dashboards nunca ven la tabla vacía.
"""
import json
import os
import sys
import urllib.error
import urllib.request

import xlrd
from dotenv import load_dotenv

SUPABASE_URL = "https://ffxopvzxyeacpbtxuagu.supabase.co"
MESES_EN = ["January", "February", "March", "April", "May", "June", "July",
            "August", "September", "October", "November", "December"]

# Columnas de cada tabla y cómo convertir el valor de la celda.
# texto | entero | decimal | fecha (fecha Excel -> timestamp ISO)
COLUMNAS = {
    "ventas_full": {
        "docto": "texto", "num_docto": "entero", "tipo_vta": "texto",
        "fecha_emision": "fecha", "fecha_vencimie": "fecha",
        "cod_vddor": "texto", "nom_vddor": "texto", "apell_vddor": "texto", "mes": "texto",
        "rut": "texto", "cliente": "texto", "tipo_cliente": "texto",
        "cod_articulo": "texto", "producto": "texto",
        "codclase1": "decimal", "clase1": "texto", "codclase2": "decimal", "clase2": "texto",
        "cantidad": "decimal", "unidmed": "texto", "monevta": "texto",
        "precio_vta_base": "decimal", "tcambio": "entero",
        "pct_descto_linea": "decimal", "descto_linea_pesos": "decimal", "descto_portada_pesos": "decimal",
        "precio_vta_unit": "decimal", "cto_prom_unit": "decimal", "cto_repos_unit": "entero",
        "cto_ult_compra_unit": "decimal", "total_neto": "decimal", "cto_promedio_total": "decimal",
        "cto_repos_total": "entero", "cto_ult_compra_total": "decimal",
        "resultado_cto_prom": "decimal", "resultado_cto_repos": "decimal", "resultado_cto_ult_compra": "decimal",
        # Trazabilidad (ver backup-manager/ConsultasSQL/Ventas_Full.sql): NV de origen de
        # cada línea y, en las notas de crédito, la factura referenciada.
        "nota_venta": "entero", "factura_ref": "entero",
    },
    "ordenes_de_produccion": {
        "nota_vta": "entero", "num_op": "entero", "fechacrea": "fecha", "fechaent": "fecha", "fechain": "fecha",
        "iniciada": "fecha", "fechafin": "fecha", "cantidad_op": "decimal", "unidmed": "texto",
        "cantidad_terminada": "decimal", "cantidad_pendiente": "decimal", "nombre_op": "texto",
        "codigo_producto": "texto", "nombre_producto": "texto", "clase1": "texto", "clase2": "texto",
        "clase3": "texto", "clase4": "texto", "bodega_id_op": "entero", "bodega_nombre_op": "texto",
        "bodega_id_nv": "decimal", "bodega_nombre_nv": "texto",
    },
    # Documentos Pendientes (FAV): las columnas del Excel tienen otros nombres -> (tipo, columna de origen)
    "documentos_pendientes_fav": {
        "documento": ("entero", "numfact"), "doc_cod": ("texto", "doc_cod"),
        "fecha": ("fecha", "fecha"), "vencimiento": ("fecha", "vencimie"),
        "debe": ("entero", "debe"), "haber": ("entero", "haber"), "saldo": ("entero", "doc_sdo"),
        "total": ("entero", "total"), "total_neto": ("entero", "totneto"), "total_iva": ("entero", "totiva"),
        "razon_social": ("texto", "razsoc"), "rut": ("texto", "rut"), "cod_vendedor": ("texto", "pers_cod"),
        "vendedor": ("texto", "pers_nom"), "cuenta": ("texto", "cta_cod"), "numreg": ("entero", "numreg"),
    },
    "notas_de_venta": {
        "numreg": "entero", "numnota": "entero", "fecha": "texto",
        "nrutclie": "entero", "nrutfact": "entero", "rutfact": "texto",
        "codvend": "texto", "nom_vddor": "texto", "apell_vddor": "texto", "moneda": "texto",
        "dctopje": "entero", "totneto": "entero", "dctotipo": "entero", "dctopeso": "entero", "tasacbio": "entero",
    },
}


# Columnas que pueden faltar en el Excel (quedan en NULL) mientras el informe de
# Manager no se actualice con la misma query que usa el pipeline.
OPCIONALES = {"ventas_full": {"nota_venta", "factura_ref"}}


def convertir(valor, tipo, ctype, datemode):
    if ctype in (xlrd.XL_CELL_EMPTY, xlrd.XL_CELL_BLANK) or (ctype == xlrd.XL_CELL_TEXT and not valor.strip()):
        return None
    if tipo == "texto":
        if ctype == xlrd.XL_CELL_NUMBER and float(valor).is_integer():
            return str(int(valor))
        return str(valor)
    if tipo == "fecha":
        if ctype == xlrd.XL_CELL_DATE or ctype == xlrd.XL_CELL_NUMBER:
            return xlrd.xldate_as_datetime(valor, datemode).isoformat()
        return str(valor)
    numero = float(str(valor).replace(",", "."))
    return round(numero) if tipo == "entero" else numero


def leer_xls(tabla, ruta):
    libro = xlrd.open_workbook(ruta, logfile=open(os.devnull, "w"))
    hoja = libro.sheet_by_index(0)
    header = [str(c.value).strip().lower() for c in hoja.row(0)]
    # Cada columna es "tipo" (mismo nombre en el Excel) o ("tipo", "columna_en_el_excel").
    columnas = {col: (d if isinstance(d, tuple) else (d, col)) for col, d in COLUMNAS[tabla].items()}

    opcionales = OPCIONALES.get(tabla, set())
    faltan = [origen for _, origen in columnas.values() if origen not in header]
    if [c for c in faltan if c not in opcionales]:
        raise SystemExit(f"{os.path.basename(ruta)} no parece ser el informe de {tabla}: faltan columnas {faltan}")
    if faltan:
        print(f"Aviso: {os.path.basename(ruta)} no trae {faltan}; esas columnas quedan vacías")

    filas = []
    for r in range(1, hoja.nrows):
        fila = {}
        for col, (tipo, origen) in columnas.items():
            if origen in faltan:
                fila[col] = None
                continue
            celda = hoja.cell(r, header.index(origen))
            fila[col] = convertir(celda.value, tipo, celda.ctype, libro.datemode)
        if all(v is None for v in fila.values()):
            continue
        # Igual que la carga histórica: el mes va en inglés, derivado de la fecha.
        if tabla == "ventas_full" and fila["fecha_emision"]:
            fila["mes"] = MESES_EN[int(fila["fecha_emision"][5:7]) - 1]
        if tabla == "documentos_pendientes_fav":
            apellido = hoja.cell(r, header.index("pers_apell")).value
            if fila["vendedor"] and str(apellido).strip():
                fila["vendedor"] = f'{fila["vendedor"].strip()} {str(apellido).strip()}'
            for k in ("razon_social", "rut", "vendedor", "doc_cod"):
                if fila[k]:
                    fila[k] = fila[k].strip()
        filas.append(fila)
    return filas


def reemplazar(tabla, filas):
    key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not key:
        raise SystemExit("Falta SUPABASE_SERVICE_KEY en .env")
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/rpc/reemplazar_{tabla}",
        data=json.dumps({"filas": filas}).encode("utf-8"),
        headers={"apikey": key, "Authorization": "Bearer " + key, "Content-Type": "application/json",
                 "Content-Profile": "shg_dashboards"},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise SystemExit(f"Supabase rechazó la carga de {tabla} (HTTP {e.code}): {e.read().decode('utf-8', 'replace')[:500]}")


def cargar(tabla, ruta, simular=False):
    filas = leer_xls(tabla, ruta)
    if not filas:
        raise SystemExit(f"{os.path.basename(ruta)} no tiene filas; no se reemplaza {tabla}.")
    if simular:
        print(f"[simulación] {tabla}: {len(filas)} filas. Primera: {json.dumps(filas[0], ensure_ascii=False)[:300]}")
        return len(filas)
    n = reemplazar(tabla, filas)
    print(f"{tabla}: {n} filas cargadas desde {os.path.basename(ruta)}")
    return n


if __name__ == "__main__":
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) != 2 or args[0] not in COLUMNAS:
        raise SystemExit(__doc__)
    cargar(args[0], args[1], simular="--simular" in sys.argv)
