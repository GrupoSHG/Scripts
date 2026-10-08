"""Facturas recibidas por correo (XML de DTE) -> Supabase shg_dashboards.dte_recibidos

Lee la casilla dedicada a DTE (dte@polchile.cl) por IMAP, toma los adjuntos XML
(sueltos o dentro de un .zip) de cada correo nuevo, parsea cada documento
(encabezado, emisor, receptor, totales, ítems y referencias) y lo deja en la
tabla shg_dashboards.dte_recibidos junto con el XML completo. La pantalla
RCV del Dashboard Finanzas (Edge Function rcv-sii, ruta /dte/folio/...) lee de
esa tabla para mostrar el detalle de cada factura de compra y descargar su XML.

Solo procesa correos nuevos: guarda el último UID leído en
shg_dashboards.dte_correo_cursor (uno por casilla). La primera vez, o con
--desde-cero, revisa los últimos DTE_DIAS_INICIAL días (90 por defecto).

Variables de entorno (secretos del workflow dte-correo-sync.yml):
  DTE_MAIL_USER        casilla (dte@polchile.cl)
  DTE_MAIL_PASSWORD    contraseña de aplicación de Google (no la clave normal)
  SUPABASE_SERVICE_KEY clave service_role de Supabase
Opcionales: DTE_MAIL_IMAP_HOST (imap.gmail.com), DTE_MAIL_CARPETA (INBOX),
  DTE_DIAS_INICIAL (90).

Uso local:  python3 Polchile_Systems/sync_dte_correo.py [--simular] [--desde-cero] [--dias N]
  --simular    no escribe en Supabase, solo imprime lo que encontró
  --desde-cero ignora el cursor y relee los últimos N días
"""
import email
import email.header
import email.utils
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime, timedelta, timezone

try:
    from dotenv import load_dotenv  # opcional, solo para pruebas locales
    load_dotenv()
except ImportError:
    pass

import imaplib

SUPABASE_URL = "https://ffxopvzxyeacpbtxuagu.supabase.co"
SCHEMA = "shg_dashboards"
IMAP_HOST = os.environ.get("DTE_MAIL_IMAP_HOST", "imap.gmail.com")
IMAP_PORT = int(os.environ.get("DTE_MAIL_IMAP_PORT", "993"))
CARPETA = os.environ.get("DTE_MAIL_CARPETA", "INBOX")
DIAS_INICIAL = int(os.environ.get("DTE_DIAS_INICIAL", "90"))
LOTE_CORREOS = 25     # correos por fetch
LOTE_FILAS = 50       # filas por upsert

SIMULAR = "--simular" in sys.argv
DESDE_CERO = "--desde-cero" in sys.argv
if "--dias" in sys.argv:
    DIAS_INICIAL = int(sys.argv[sys.argv.index("--dias") + 1])


# ── Supabase (PostgREST) ────────────────────────────────────────────────────
def _sb(metodo, ruta, datos=None, prefer=None):
    key = os.environ["SUPABASE_SERVICE_KEY"]
    headers = {
        "apikey": key, "Authorization": "Bearer " + key,
        "Accept-Profile": SCHEMA, "Content-Profile": SCHEMA,
        "Content-Type": "application/json",
    }
    if prefer:
        headers["Prefer"] = prefer
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/{ruta}",
        data=json.dumps(datos, ensure_ascii=False).encode("utf-8") if datos is not None else None,
        headers=headers, method=metodo)
    for intento in range(3):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                cuerpo = r.read().decode("utf-8")
                return json.loads(cuerpo) if cuerpo else None
        except urllib.error.HTTPError as e:
            detalle = e.read().decode("utf-8", "replace")[:500]
            if e.code >= 500 and intento < 2:
                time.sleep(3 * (intento + 1))
                continue
            raise SystemExit(f"Supabase respondió HTTP {e.code} en {metodo} {ruta}: {detalle}")
        except urllib.error.URLError as e:
            if intento < 2:
                time.sleep(3 * (intento + 1))
                continue
            raise SystemExit(f"No se pudo conectar a Supabase: {e}")


def leer_cursor(buzon):
    filas = _sb("GET", f"dte_correo_cursor?buzon=eq.{urllib.parse.quote(buzon)}&select=ultimo_uid,uidvalidity")
    return filas[0] if filas else None


def guardar_cursor(buzon, ultimo_uid, uidvalidity, nuevos):
    _sb("POST", "dte_correo_cursor?on_conflict=buzon",
        [{"buzon": buzon, "ultimo_uid": ultimo_uid, "uidvalidity": uidvalidity,
          "actualizado_en": datetime.now(timezone.utc).isoformat(),
          "ultimos_nuevos": nuevos}],
        prefer="resolution=merge-duplicates,return=minimal")


def upsert_documentos(filas):
    for i in range(0, len(filas), LOTE_FILAS):
        _sb("POST", "dte_recibidos?on_conflict=rut_emisor,tipo_dte,folio",
            filas[i:i + LOTE_FILAS], prefer="resolution=merge-duplicates,return=minimal")


# ── Parseo del XML de DTE ───────────────────────────────────────────────────
def _tag(el):
    return el.tag.split("}")[-1]


def _hijo(el, nombre):
    if el is None:
        return None
    return next((c for c in el if _tag(c) == nombre), None)


def _texto(el, *ruta):
    for nombre in ruta:
        el = _hijo(el, nombre)
        if el is None:
            return None
    return (el.text or "").strip() or None


def _num(el, *ruta):
    t = _texto(el, *ruta)
    if t is None:
        return None
    try:
        return float(t.replace(",", "."))
    except ValueError:
        return None


def _entero(el, *ruta):
    n = _num(el, *ruta)
    return int(n) if n is not None else None


def normalizar_rut(rut):
    if not rut:
        return None
    rut = rut.replace(".", "").replace(" ", "").upper()
    if "-" not in rut and len(rut) > 1:
        rut = rut[:-1] + "-" + rut[-1]
    return rut


def parsear_items(doc):
    items = []
    for det in [c for c in doc if _tag(c) == "Detalle"]:
        codigo = None
        cdg = _hijo(det, "CdgItem")
        if cdg is not None:
            codigo = _texto(cdg, "VlrCodigo")
        items.append({
            "linea": _entero(det, "NroLinDet"),
            "codigo": codigo,
            "descripcion": _texto(det, "NmbItem") or "",
            "detalle": _texto(det, "DscItem"),
            "cantidad": _num(det, "QtyItem"),
            "unidad": _texto(det, "UnmdItem"),
            "precioUnitario": _num(det, "PrcItem"),
            "descuento": _num(det, "DescuentoMonto"),
            "monto": _num(det, "MontoItem"),
        })
    return items


def parsear_referencias(doc):
    refs = []
    for ref in [c for c in doc if _tag(c) == "Referencia"]:
        refs.append({
            "tipoDoc": _texto(ref, "TpoDocRef"),
            "folio": _texto(ref, "FolioRef"),
            "fecha": _texto(ref, "FchRef"),
            "codigo": _texto(ref, "CodRef"),
            "razon": _texto(ref, "RazonRef"),
        })
    return refs


def parsear_xml(xml_bytes, contexto):
    """Devuelve una fila por documento (Documento/Exportaciones/Liquidacion) del XML."""
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as e:
        print(f"  XML ilegible ({contexto['archivo']}): {e}")
        return []
    filas = []
    for doc in [el for el in root.iter() if _tag(el) in ("Documento", "Exportaciones", "Liquidacion")]:
        enc = _hijo(doc, "Encabezado")
        if enc is None:
            continue
        iddoc, emisor, receptor, totales = (_hijo(enc, n) for n in ("IdDoc", "Emisor", "Receptor", "Totales"))
        tipo = _entero(iddoc, "TipoDTE")
        folio = _entero(iddoc, "Folio")
        rut_emisor = normalizar_rut(_texto(emisor, "RUTEmisor"))
        if tipo is None or folio is None or not rut_emisor:
            continue
        # Se guarda el elemento DTE completo (con firma), o el Documento si viene suelto
        padre = next((p for p in root.iter() if any(c is doc for c in p)), None)
        xml_el = padre if padre is not None and _tag(padre) == "DTE" else doc
        filas.append({
            "rut_emisor": rut_emisor,
            "tipo_dte": tipo,
            "folio": folio,
            "fecha_emision": _texto(iddoc, "FchEmis"),
            "fecha_vencimiento": _texto(iddoc, "FchVenc"),
            "forma_pago": _texto(iddoc, "FmaPago"),
            "razon_social_emisor": _texto(emisor, "RznSoc") or _texto(emisor, "RznSocEmisor"),
            "giro_emisor": _texto(emisor, "GiroEmis") or _texto(emisor, "GiroEmisor"),
            "rut_receptor": normalizar_rut(_texto(receptor, "RUTRecep")),
            "razon_social_receptor": _texto(receptor, "RznSocRecep"),
            "monto_neto": _num(totales, "MntNeto"),
            "monto_exento": _num(totales, "MntExe"),
            "iva": _num(totales, "IVA"),
            "monto_total": _num(totales, "MntTotal"),
            "items": parsear_items(doc),
            "referencias": parsear_referencias(doc),
            "xml": ET.tostring(xml_el, encoding="unicode"),
            **contexto,
        })
    return filas


# ── Correo ──────────────────────────────────────────────────────────────────
def adjuntos_xml(msg):
    """(nombre, bytes) de cada XML del correo, incluidos los que vienen en .zip."""
    out = []
    for parte in msg.walk():
        if parte.get_content_maintype() == "multipart":
            continue
        nombre = parte.get_filename() or ""
        ctype = parte.get_content_type()
        datos = parte.get_payload(decode=True)
        if not datos:
            continue
        n = nombre.lower()
        if n.endswith(".xml") or (ctype in ("text/xml", "application/xml") and not n.endswith(".pdf")):
            out.append((nombre or "adjunto.xml", datos))
        elif n.endswith(".zip") or ctype in ("application/zip", "application/x-zip-compressed"):
            try:
                with zipfile.ZipFile(io.BytesIO(datos)) as z:
                    for info in z.infolist():
                        if info.filename.lower().endswith(".xml"):
                            out.append((f"{nombre}/{info.filename}", z.read(info)))
            except zipfile.BadZipFile:
                print(f"  zip ilegible: {nombre}")
    return out


def decodificar(cabecera):
    if not cabecera:
        return None
    partes = email.header.decode_header(cabecera)
    return "".join(p.decode(enc or "utf-8", "replace") if isinstance(p, bytes) else p for p, enc in partes).strip()


def fecha_correo(msg):
    try:
        d = email.utils.parsedate_to_datetime(msg.get("Date"))
        return d.astimezone(timezone.utc).isoformat() if d else None
    except (TypeError, ValueError):
        return None


def main():
    usuario = os.environ.get("DTE_MAIL_USER")
    clave = os.environ.get("DTE_MAIL_PASSWORD")
    if not usuario or not clave:
        raise SystemExit("Faltan DTE_MAIL_USER / DTE_MAIL_PASSWORD")
    if not SIMULAR and not os.environ.get("SUPABASE_SERVICE_KEY"):
        raise SystemExit("Falta SUPABASE_SERVICE_KEY")

    cursor = None if (SIMULAR or DESDE_CERO) else leer_cursor(usuario)

    imap = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
    try:
        try:
            imap.login(usuario, clave)
        except imaplib.IMAP4.error as e:
            raise SystemExit(f"Gmail rechazó el login de {usuario}: {e}. "
                             "Revisa que IMAP esté activo y que la clave sea una contraseña de aplicación.")
        estado, datos = imap.select(f'"{CARPETA}"', readonly=True)
        if estado != "OK":
            raise SystemExit(f"No se pudo abrir la carpeta {CARPETA}: {datos}")
        uidvalidity = int((imap.response("UIDVALIDITY")[1][0] or b"0").decode())

        if cursor and int(cursor.get("uidvalidity") or 0) == uidvalidity and int(cursor.get("ultimo_uid") or 0) > 0:
            desde_uid = int(cursor["ultimo_uid"]) + 1
            criterio = f"UID {desde_uid}:*"
        else:
            desde = (datetime.now(timezone.utc) - timedelta(days=DIAS_INICIAL)).strftime("%d-%b-%Y")
            criterio = f"SINCE {desde}"
            desde_uid = 1
        estado, resp = imap.uid("search", None, criterio)
        if estado != "OK":
            raise SystemExit(f"Búsqueda IMAP falló: {resp}")
        uids = [int(u) for u in resp[0].split() if int(u) >= desde_uid]
        print(f"Casilla {usuario} ({CARPETA}): {len(uids)} correo(s) por revisar ({criterio})")

        filas, ultimo_uid, correos_con_xml = [], (cursor or {}).get("ultimo_uid") or 0, 0
        for i in range(0, len(uids), LOTE_CORREOS):
            lote = uids[i:i + LOTE_CORREOS]
            estado, resp = imap.uid("fetch", ",".join(map(str, lote)), "(UID BODY.PEEK[])")
            if estado != "OK":
                raise SystemExit(f"Fetch IMAP falló: {resp}")
            for item in resp:
                if not isinstance(item, tuple):
                    continue
                m = re.search(rb"UID (\d+)", item[0])
                uid = int(m.group(1)) if m else 0
                msg = email.message_from_bytes(item[1])
                contexto_base = {
                    "correo_uid": uid,
                    "correo_asunto": decodificar(msg.get("Subject")),
                    "correo_de": decodificar(msg.get("From")),
                    "correo_fecha": fecha_correo(msg),
                }
                xmls = adjuntos_xml(msg)
                if xmls:
                    correos_con_xml += 1
                for nombre, datos in xmls:
                    filas.extend(parsear_xml(datos, {**contexto_base, "archivo": nombre}))
                ultimo_uid = max(ultimo_uid, uid)
            # Se escribe por lote para no perder avance si el runner se corta
            if filas and not SIMULAR:
                upsert_documentos(filas)
                print(f"  {len(filas)} documento(s) guardados hasta el UID {ultimo_uid}")
                filas = []
            if not SIMULAR and uids:
                guardar_cursor(usuario, ultimo_uid, uidvalidity, correos_con_xml)

        if SIMULAR:
            print(f"{correos_con_xml} correo(s) con XML, {len(filas)} documento(s):")
            for f in filas[:20]:
                print(f"  {f['tipo_dte']:>3} folio {f['folio']:>8}  {f['rut_emisor']:<13} {f['razon_social_emisor'] or '':<40.40} "
                      f"{f['fecha_emision'] or '':<10} total {f['monto_total'] or 0:>12,.0f}  ítems {len(f['items'])}")
        else:
            if not uids:
                guardar_cursor(usuario, ultimo_uid, uidvalidity, 0)
            print(f"Listo: {correos_con_xml} correo(s) con XML procesados; cursor en UID {ultimo_uid}")
    finally:
        try:
            imap.logout()
        except Exception:
            pass


if __name__ == "__main__":
    main()
