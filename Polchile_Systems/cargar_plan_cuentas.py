"""Carga el plan de cuentas contables (Excel o CSV) en shg_dashboards.plan_cuentas.

Uso:
  python3 Polchile_Systems/cargar_plan_cuentas.py <archivo.xlsx|.xls|.csv> [--empresa polchile] [--hoja NOMBRE]
         [--simular] [--desactivar-faltantes]

  --empresa              polchile (por defecto) o m5
  --hoja                 nombre de la hoja del Excel (por defecto, la primera)
  --simular              no escribe en Supabase, solo muestra lo que leyó
  --desactivar-faltantes marca activo=false las cuentas que ya estaban en Supabase
                         y no vienen en el archivo (por defecto se dejan como están)

Columnas: el script reconoce los encabezados por nombre, sin importar mayúsculas ni
tildes. Obligatorias: código ("codigo", "código", "cuenta", "cod", "q_cod"), nombre
("nombre", "descripcion", "glosa", "detalle", "q_nom"). Opcionales: tipo, nivel,
imputable ("imputable", "movimiento", "analitica": S/N, Sí/No, 1/0, true/false). Si no
vienen, se infieren como en el export de Manager: nivel = sangría del nombre (3 espacios
por nivel), imputable = el código no termina en "00", tipo = nombre de la cuenta raíz
(ACTIVOS, PASIVOS, ...). Si no hay fila de encabezado reconocible, toma la primera
columna como código y la segunda como nombre. Las filas sin código o sin nombre se saltan;
otras columnas de la hoja (el export de Manager trae un listado de facturas al lado) se ignoran.

Requiere SUPABASE_SERVICE_KEY (en .env o en el entorno). Para .xlsx usa openpyxl;
para .xls (Excel 97-2003, como exporta Manager) usa xlrd: `pip install openpyxl xlrd`.
"""
import csv
import io
import json
import os
import re
import sys
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

SUPABASE_URL = "https://ffxopvzxyeacpbtxuagu.supabase.co"
SCHEMA = "shg_dashboards"
LOTE = 200

ALIAS = {
    "codigo":    ["codigo", "cod", "cuenta", "codigo cuenta", "cod cuenta", "numero", "nro", "n", "q cod"],
    "nombre":    ["nombre", "descripcion", "glosa", "detalle", "nombre cuenta", "denominacion", "titulo", "q nom"],
    "tipo":      ["tipo", "clasificacion", "clase", "naturaleza", "grupo"],
    "nivel":     ["nivel", "level", "profundidad"],
    "imputable": ["imputable", "movimiento", "analitica", "analitico", "acepta movimiento", "detalle s/n", "imp"],
}


def normalizar(s):
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def a_bool(v):
    s = normalizar(v)
    if s in ("", "none"):
        return None
    return s in ("s", "si", "y", "yes", "1", "true", "verdadero", "x", "imputable", "movimiento")


def leer_filas(ruta, hoja=None):
    ext = os.path.splitext(ruta)[1].lower()
    if ext == ".csv":
        with io.open(ruta, encoding="utf-8-sig", newline="") as f:
            muestra = f.read(4096); f.seek(0)
            try:
                dialecto = csv.Sniffer().sniff(muestra, delimiters=";,\t")
            except csv.Error:
                dialecto = csv.excel
            return [list(r) for r in csv.reader(f, dialecto)]
    if ext == ".xlsx" or ext == ".xlsm":
        import openpyxl
        wb = openpyxl.load_workbook(ruta, read_only=True, data_only=True)
        ws = wb[hoja] if hoja else wb.worksheets[0]
        return [list(r) for r in ws.iter_rows(values_only=True)]
    if ext == ".xls":
        import xlrd
        wb = xlrd.open_workbook(ruta)
        ws = wb.sheet_by_name(hoja) if hoja else wb.sheet_by_index(0)
        return [ws.row_values(i) for i in range(ws.nrows)]
    raise SystemExit(f"Formato no soportado: {ext} (usa .xlsx, .xls o .csv)")


def detectar_columnas(filas):
    """Busca en las primeras 15 filas una que tenga encabezados reconocibles."""
    for idx, fila in enumerate(filas[:15]):
        celdas = [normalizar(c) for c in fila]
        mapa = {}
        for campo, alias in ALIAS.items():
            for j, c in enumerate(celdas):
                if c and (c in alias or any(c.startswith(a + " ") or c.endswith(" " + a) for a in alias)):
                    if j not in mapa.values():
                        mapa[campo] = j
                        break
        if "codigo" in mapa and "nombre" in mapa:
            return idx + 1, mapa
    return 0, {"codigo": 0, "nombre": 1}


def limpiar_codigo(v):
    if v is None:
        return None
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    s = str(v).strip()
    return s or None


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        raise SystemExit(__doc__)
    ruta = args[0]
    empresa = sys.argv[sys.argv.index("--empresa") + 1] if "--empresa" in sys.argv else "polchile"
    hoja = sys.argv[sys.argv.index("--hoja") + 1] if "--hoja" in sys.argv else None
    simular = "--simular" in sys.argv
    desactivar = "--desactivar-faltantes" in sys.argv

    filas = leer_filas(ruta, hoja)
    inicio, mapa = detectar_columnas(filas)
    print(f"Archivo {os.path.basename(ruta)}: {len(filas)} filas; columnas detectadas: "
          + ", ".join(f"{k}=col {v + 1}" for k, v in mapa.items()) + f"; datos desde la fila {inicio + 1}")

    # El export de Manager ("Plan de Cuentas Manager.xlsx") no trae tipo, nivel ni
    # imputable: el nivel va en la sangría del nombre (3 espacios por nivel), las
    # cuentas de agrupación son las que terminan en "00" y el tipo es el nombre de la
    # cuenta raíz (ACTIVOS, PASIVOS, ...) bajo la que cuelgan. Se infieren si faltan.
    # Primera pasada: las cuentas raíz del plan (código de 6 dígitos terminado en 00000)
    # dan el tipo de todas las que comparten su primer dígito (1 Activos, 2 Pasivos,
    # 3 Ingresos, 4 Gastos...). Es más fiable que la sangría, que el export a veces pierde.
    raices = {}
    for fila in filas[inicio:]:
        j_c, j_n = mapa.get("codigo"), mapa.get("nombre")
        if j_c is None or j_n is None or j_c >= len(fila) or j_n >= len(fila):
            continue
        cod = limpiar_codigo(fila[j_c])
        if cod and cod.isdigit() and len(cod) == 6 and cod.endswith("00000") and fila[j_n]:
            raices[cod[0]] = re.sub(r"\s+", " ", str(fila[j_n])).strip().title()

    def nivel_por_codigo(cod):
        if not (cod.isdigit() and len(cod) == 6):
            return None
        if cod.endswith("00000"): return 1
        if cod.endswith("0000"):  return 2
        if cod.endswith("00"):    return 3
        return 4

    cuentas, vistos, tipo_raiz = [], set(), None
    for fila in filas[inicio:]:
        def celda(campo):
            j = mapa.get(campo)
            return fila[j] if j is not None and j < len(fila) else None
        codigo = limpiar_codigo(celda("codigo"))
        nombre_crudo = str(celda("nombre") or "")
        nombre = re.sub(r"\s+", " ", nombre_crudo).strip()
        if not codigo or not nombre or codigo in vistos:
            continue
        vistos.add(codigo)
        nivel = celda("nivel")
        try:
            nivel = int(float(nivel)) if nivel not in (None, "") else None
        except (TypeError, ValueError):
            nivel = None
        sangria = len(nombre_crudo) - len(nombre_crudo.lstrip(" "))
        if nivel is None:
            nivel = nivel_por_codigo(codigo) or (sangria // 3 + 1)
        imputable = a_bool(celda("imputable"))
        if imputable is None:
            imputable = not (codigo.isdigit() and codigo.endswith("00"))
        tipo = celda("tipo")
        tipo = str(tipo).strip() if tipo not in (None, "") else None
        if nivel == 1:
            tipo_raiz = nombre.title()
        if tipo is None:
            tipo = raices.get(codigo[0]) if codigo.isdigit() else None
        if tipo is None:
            tipo = tipo_raiz
        cuentas.append({
            "empresa": empresa, "codigo": codigo, "nombre": nombre,
            "tipo": tipo,
            "nivel": nivel,
            "imputable": imputable,
            "activo": True,
            "actualizado_en": datetime.now(timezone.utc).isoformat(),
        })
    print(f"{len(cuentas)} cuentas válidas ({sum(1 for c in cuentas if c['imputable'])} imputables)")
    for c in cuentas[:8]:
        print(f"  {c['codigo']:<14} {c['nombre'][:50]:<50} {c['tipo'] or '':<12} {'imputable' if c['imputable'] else 'agrupación'}")
    if simular or not cuentas:
        return

    key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not key:
        raise SystemExit("Falta SUPABASE_SERVICE_KEY")
    headers = {"apikey": key, "Authorization": "Bearer " + key, "Content-Type": "application/json",
               "Accept-Profile": SCHEMA, "Content-Profile": SCHEMA,
               "Prefer": "resolution=merge-duplicates,return=minimal"}

    def pedir(metodo, ruta_api, datos=None):
        req = urllib.request.Request(f"{SUPABASE_URL}/rest/v1/{ruta_api}", method=metodo, headers=headers,
                                     data=json.dumps(datos, ensure_ascii=False).encode("utf-8") if datos is not None else None)
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.read().decode()
        except urllib.error.HTTPError as e:
            raise SystemExit(f"Supabase HTTP {e.code} en {metodo} {ruta_api}: {e.read().decode('utf-8', 'replace')[:500]}")

    for i in range(0, len(cuentas), LOTE):
        pedir("POST", "plan_cuentas?on_conflict=empresa,codigo", cuentas[i:i + LOTE])
        print(f"  {min(i + LOTE, len(cuentas))}/{len(cuentas)} cargadas")

    if desactivar:
        codigos = ",".join(urllib.parse.quote(f'"{c["codigo"]}"') for c in cuentas)
        pedir("PATCH", f"plan_cuentas?empresa=eq.{empresa}&codigo=not.in.({codigos})", {"activo": False})
        print("Cuentas ausentes en el archivo marcadas como inactivas")
    print(f"Listo: plan de cuentas de {empresa} cargado en {SCHEMA}.plan_cuentas")


if __name__ == "__main__":
    main()
