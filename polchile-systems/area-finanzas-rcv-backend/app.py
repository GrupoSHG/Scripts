"""
Backend RCV Polchile
---------------------
Guarda TODAS las credenciales (certificado .pfx, password del certificado,
ApiKey de SimpleAPI, credenciales de Manager) en variables de entorno,
leidas desde un archivo .env que NUNCA se sube a git.

El frontend (carpeta static/) no maneja ningun secreto: solo pide un
periodo y recibe el resultado ya consultado. La carga a Manager tambien
pasa por aqui, para que el ApiKey de Manager tampoco viaje al navegador.
"""
import os
import re
import json
import base64
import email
import imaplib
import xml.etree.ElementTree as ET
import requests
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv

load_dotenv()  # lee el archivo .env (no versionado)

app = Flask(__name__, static_folder="areafinanzas", static_url_path="")
CORS(app)  # en producción, restringe origins= a tu dominio real

# ---------------------------------------------------------------
# Credenciales (solo existen en memoria del servidor, nunca en el navegador)
# ---------------------------------------------------------------
SIMPLEAPI_KEY     = os.environ.get("SIMPLEAPI_KEY")
RUT_CERTIFICADO   = os.environ.get("RUT_CERTIFICADO")
RUT_EMPRESA       = os.environ.get("RUT_EMPRESA")
PASSWORD_CERT     = os.environ.get("PASSWORD_CERT")
AMBIENTE          = os.environ.get("AMBIENTE", "1")  # 1=produccion, 0=certificacion
PFX_PATH          = os.environ.get("PFX_PATH", "/tmp/certificado.pfx")
PFX_BASE64        = os.environ.get("PFX_BASE64")     # alternativa para hosts en la nube (Render/Railway)

MANAGER_DOMAIN      = os.environ.get("MANAGER_DOMAIN")
MANAGER_BUSINESS_ID = os.environ.get("MANAGER_BUSINESS_ID")
MANAGER_APIKEY      = os.environ.get("MANAGER_APIKEY")

# Casilla dedicada que solo recibe XML de DTE
DTE_MAIL_IMAP_HOST = os.environ.get("DTE_MAIL_IMAP_HOST", "imap.gmail.com")
DTE_MAIL_IMAP_PORT = int(os.environ.get("DTE_MAIL_IMAP_PORT", "993"))
DTE_MAIL_USER      = os.environ.get("DTE_MAIL_USER")
DTE_MAIL_PASSWORD  = os.environ.get("DTE_MAIL_PASSWORD")  # app password, no la clave normal

# Boufin - confirmación de transferencias recibidas (Santander)
BOUFIN_API_KEY                = os.environ.get("BOUFIN_API_KEY")
SANTANDER_RUT_HOMEBANKING     = os.environ.get("SANTANDER_RUT_HOMEBANKING")
SANTANDER_CLAVE_HOMEBANKING   = os.environ.get("SANTANDER_CLAVE_HOMEBANKING")
BOUFIN_HOST = "https://api.boufin.cl"  # confirmar host exacto en la documentación de Boufin

SIMPLEAPI_HOST = "https://servicios.simpleapi.cl"

REQUIRED_VARS = [
    "SIMPLEAPI_KEY", "RUT_CERTIFICADO", "RUT_EMPRESA", "PASSWORD_CERT",
]


def preparar_certificado():
    """En hosts en la nube no se puede simplemente 'copiar' el .pfx al
    filesystem (es efímero y no está en git). Si viene PFX_BASE64, lo
    decodifica y lo escribe en PFX_PATH al arrancar. Localmente, si ya
    tienes el archivo en secrets/, esto no hace nada."""
    if PFX_BASE64 and not os.path.isfile(PFX_PATH):
        with open(PFX_PATH, "wb") as f:
            f.write(base64.b64decode(PFX_BASE64))


def validar_config():
    faltantes = [v for v in REQUIRED_VARS if not os.environ.get(v)]
    if faltantes:
        raise RuntimeError(
            "Faltan variables de entorno en .env: " + ", ".join(faltantes)
        )
    if not os.path.isfile(PFX_PATH):
        raise RuntimeError(f"No se encuentra el certificado .pfx en: {PFX_PATH}")


# ---------------------------------------------------------------
# SimpleAPI - Registro de Compras y Ventas (RCV)
# ---------------------------------------------------------------
def consultar_rcv(tipo, mes, anio):
    """tipo: 'compras' | 'ventas'. mes/anio: strings, ej '07','2026'."""
    url = f"{SIMPLEAPI_HOST}/api/RCV/{tipo}/{mes}/{anio}"
    payload = {
        "RutCertificado": RUT_CERTIFICADO,
        "RutEmpresa": RUT_EMPRESA,
        "Ambiente": int(AMBIENTE),
        "Password": PASSWORD_CERT,
    }
    with open(PFX_PATH, "rb") as f:
        files = {"files": (os.path.basename(PFX_PATH), f, "application/x-pkcs12")}
        data = {"input": json.dumps(payload)}
        resp = requests.post(
            url,
            headers={"Authorization": SIMPLEAPI_KEY},
            data=data,
            files=files,
            timeout=150,  # el endpoint real demora 40-120s
        )
    resp.raise_for_status()
    return resp.json()


def extraer_documentos(data, tipo):
    """Parseo defensivo: la forma exacta de la respuesta se debe confirmar
    con una llamada real. Ajustar las llaves candidatas segun corresponda."""
    candidatos = [data.get(tipo), data.get("detalle"), data.get("registros"),
                  data.get("documentos"), data.get("data")]
    arr = next((c for c in candidatos if isinstance(c, list)), None)
    if arr is None:
        return []
    origen = "compra" if tipo == "compras" else "venta"
    out = []
    for i, d in enumerate(arr):
        out.append({
            "id": f"{origen}-{i}",
            "origen": origen,
            "subido": False,
            "folio": d.get("folio") or d.get("Folio") or "",
            "tipoDoc": d.get("tipoDte") or d.get("TipoDTE") or d.get("tipoDoc") or "",
            "rut": d.get("rutProveedor") or d.get("rutCliente") or d.get("rut") or "",
            "razonSocial": d.get("razonSocial") or d.get("RazonSocial") or "",
            "fecha": d.get("fechaEmision") or d.get("FchEmis") or "",
            "neto": float(d.get("montoNeto") or d.get("MntNeto") or 0),
            "iva": float(d.get("montoIVA") or d.get("IVA") or 0),
            "total": float(d.get("montoTotal") or d.get("MntTotal") or 0),
            "estado": str(d.get("estado") or d.get("Estado") or "pendiente").lower(),
        })
    return out


@app.route("/api/rcv")
def api_rcv():
    periodo = request.args.get("periodo")  # "YYYY-MM"
    if not periodo or "-" not in periodo:
        return jsonify({"error": "Falta o es inválido el parámetro periodo (YYYY-MM)"}), 400
    anio, mes = periodo.split("-")
    try:
        raw_compras = consultar_rcv("compras", mes, anio)
        raw_ventas = consultar_rcv("ventas", mes, anio)
    except requests.HTTPError as e:
        return jsonify({"error": f"SimpleAPI respondió con error: {e}"}), 502
    except requests.Timeout:
        return jsonify({"error": "SimpleAPI no respondió a tiempo (timeout)"}), 504

    return jsonify({
        "compra": extraer_documentos(raw_compras, "compras"),
        "venta": extraer_documentos(raw_ventas, "ventas"),
    })


# ---------------------------------------------------------------
# Correo DTE - buscar la factura por folio y extraer sus items del XML
# ---------------------------------------------------------------
def buscar_xml_por_folio(folio):
    """Busca en la casilla dedicada a DTE un correo que mencione el folio
    y trae el primer adjunto .xml. Requiere DTE_MAIL_USER/PASSWORD (app
    password de Gmail, no la clave normal) en .env."""
    if not (DTE_MAIL_USER and DTE_MAIL_PASSWORD):
        raise RuntimeError("Falta configurar DTE_MAIL_USER / DTE_MAIL_PASSWORD en .env")

    imap = imaplib.IMAP4_SSL(DTE_MAIL_IMAP_HOST, DTE_MAIL_IMAP_PORT)
    try:
        imap.login(DTE_MAIL_USER, DTE_MAIL_PASSWORD)
        imap.select("INBOX")
        # Busca el folio en el asunto. Si tus correos DTE no traen el folio
        # en el asunto, ajusta este criterio (ej. buscar en el cuerpo).
        status, ids = imap.search(None, f'(SUBJECT "{folio}")')
        if status != "OK" or not ids[0]:
            return None
        # Se toma el correo más reciente que calce
        ultimo_id = ids[0].split()[-1]
        status, msg_data = imap.fetch(ultimo_id, "(RFC822)")
        if status != "OK":
            return None
        msg = email.message_from_bytes(msg_data[0][1])
        for parte in msg.walk():
            nombre = parte.get_filename()
            if nombre and nombre.lower().endswith(".xml"):
                return parte.get_payload(decode=True)
        return None
    finally:
        imap.logout()


def parsear_items_dte(xml_bytes):
    """Extrae los items (Detalle) de un XML de DTE del SII."""
    root = ET.fromstring(xml_bytes)
    # El XML del SII suele traer namespace; se ignora buscando por sufijo de tag
    items = []
    for i, det in enumerate([el for el in root.iter() if el.tag.split('}')[-1] == 'Detalle']):
        def campo(nombre):
            el = next((c for c in det if c.tag.split('}')[-1] == nombre), None)
            return el.text if el is not None else None

        items.append({
            "id": f"item-{i}",
            "descripcion": campo("NmbItem") or "",
            "cantidad": float(campo("QtyItem") or 1),
            "precioUnitario": float(campo("PrcItem") or 0),
            "monto": float(campo("MontoItem") or 0),
            "codigo": "",
            "cuentaContable": "",
        })
    return items


@app.route("/api/dte/folio/<folio>")
def api_dte_folio(folio):
    try:
        xml_bytes = buscar_xml_por_folio(folio)
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 500
    except imaplib.IMAP4.error as e:
        return jsonify({"error": f"No se pudo conectar al correo: {e}"}), 502

    if xml_bytes is None:
        return jsonify({"error": f"No se encontró el XML del folio {folio} en la casilla DTE"}), 404

    try:
        items = parsear_items_dte(xml_bytes)
    except ET.ParseError as e:
        return jsonify({"error": f"El XML encontrado no se pudo leer: {e}"}), 500

    return jsonify({"folio": folio, "items": items})


# ---------------------------------------------------------------
# Cuenta contable - lookup por código
# TODO: esto asume que el mapeo código -> cuenta contable vive en Manager.
# Ajustar consultar_cuenta_contable() para que apunte a la fuente real
# (tabla SQL de Manager, como ya hacen las consultas en BackupManager,
# o un endpoint de Manager si expone el plan de cuentas via api2).
# ---------------------------------------------------------------
def consultar_cuenta_contable(codigo):
    """Placeholder: reemplazar por la consulta real al mapeo código->cuenta.
    Devuelve None si no encuentra el código."""
    # Ejemplo de como se vería con pyodbc contra Manager (mismo patrón que
    # BackupManager), una vez confirmada la tabla/columnas reales:
    #
    # import pyodbc
    # conn = pyodbc.connect(MANAGER_SQL_CONNECTION_STRING)
    # cur = conn.cursor()
    # cur.execute("SELECT CuentaContable FROM TablaMapeoCodigos WHERE Codigo = ?", codigo)
    # row = cur.fetchone()
    # return row[0] if row else None
    return None


@app.route("/api/cuenta-contable/<codigo>")
def api_cuenta_contable(codigo):
    cuenta = consultar_cuenta_contable(codigo)
    if cuenta is None:
        return jsonify({"encontrado": False, "cuenta": None}), 404
    return jsonify({"encontrado": True, "cuenta": cuenta})


# ---------------------------------------------------------------
# Boufin - confirmación de transferencias recibidas (Banco Santander)
# La sesión de Boufin dura 1h; se cachea en memoria para no re-loguear
# en cada consulta. NOTA: los nombres de endpoints/campos exactos deben
# confirmarse contra la documentación técnica de Boufin antes de producción.
# ---------------------------------------------------------------
_boufin_sesion = {"token": None, "expira": 0}


def boufin_login():
    import time
    if _boufin_sesion["token"] and _boufin_sesion["expira"] > time.time():
        return _boufin_sesion["token"]

    if not BOUFIN_API_KEY:
        raise RuntimeError("Falta BOUFIN_API_KEY en .env")

    resp = requests.post(
        f"{BOUFIN_HOST}/api/v1/auth/login",
        headers={"Content-Type": "application/json"},
        json={"apiKey": BOUFIN_API_KEY},
        timeout=20,
    )
    resp.raise_for_status()
    data = resp.json()
    token = data.get("sessionToken")
    if not token:
        raise RuntimeError("Boufin no devolvió sessionToken")

    _boufin_sesion["token"] = token
    _boufin_sesion["expira"] = time.time() + 55 * 60  # renueva 5 min antes de expirar
    return token


def boufin_tarea(action, payload):
    token = boufin_login()
    resp = requests.post(
        f"{BOUFIN_HOST}/api/v1/tasks",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"action": action, **payload},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()


def boufin_credenciales_banco():
    if not (SANTANDER_RUT_HOMEBANKING and SANTANDER_CLAVE_HOMEBANKING):
        raise RuntimeError("Falta SANTANDER_RUT_HOMEBANKING / SANTANDER_CLAVE_HOMEBANKING en .env")
    return {"rut": SANTANDER_RUT_HOMEBANKING, "clave": SANTANDER_CLAVE_HOMEBANKING}


def boufin_consultar_transferencias():
    data = boufin_tarea("banco-santander:transfer", boufin_credenciales_banco())
    # Parseo defensivo: ajustar la(s) llave(s) reales una vez confirmadas contra Boufin
    candidatos = [data.get("transferencias"), data.get("movimientos"), data.get("data")]
    arr = next((c for c in candidatos if isinstance(c, list)), [])
    return [{
        "id": m.get("id") or i,
        "fecha": m.get("fecha") or m.get("date"),
        "monto": float(m.get("monto") or m.get("amount") or 0),
        "glosa": m.get("glosa") or m.get("detail") or "",
        "origen": m.get("origen") or m.get("sender") or "",
    } for i, m in enumerate(arr)]


def boufin_consultar_saldo():
    data = boufin_tarea("banco-santander:balance", boufin_credenciales_banco())
    return float(data.get("saldo") or data.get("balance") or 0)


@app.route("/api/transferencias")
def api_transferencias():
    try:
        saldo = boufin_consultar_saldo()
        transferencias = boufin_consultar_transferencias()
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 500
    except requests.HTTPError as e:
        return jsonify({"error": f"Boufin respondió con error: {e}"}), 502
    except requests.Timeout:
        return jsonify({"error": "Boufin no respondió a tiempo (timeout)"}), 504

    return jsonify({"saldo": saldo, "transferencias": transferencias})


# ---------------------------------------------------------------
# Manager ERP (api2) - carga de facturas
# ---------------------------------------------------------------
def mapear_a_manager(doc, tipo):
    base = {
        "issueDate": doc.get("fecha"),
        "reference": str(doc.get("folio")),
        "description": doc.get("tipoDoc"),
        "Lines": [{
            "lineDescription": f"{doc.get('tipoDoc')} {doc.get('folio')}",
            "UnitPrice": {"value": doc.get("neto"), "currency": ""},
            "qty": 1,
        }],
    }
    if tipo == "compra":
        base["supplier"] = doc.get("razonSocial")
    else:
        base["customer"] = doc.get("razonSocial")
    return base


@app.route("/api/manager/upload", methods=["POST"])
def api_manager_upload():
    if not (MANAGER_DOMAIN and MANAGER_BUSINESS_ID and MANAGER_APIKEY):
        return jsonify({"error": "Conexión a Manager no configurada en .env"}), 500

    body = request.get_json(force=True)
    tipo = body.get("tipo")  # 'compra' | 'venta'
    documentos = body.get("documentos", [])
    form_path = "purchase-invoice-form" if tipo == "compra" else "sales-invoice-form"
    url = f"{MANAGER_DOMAIN.rstrip('/')}/api2/{MANAGER_BUSINESS_ID}/{form_path}"

    resultados = []
    for doc in documentos:
        try:
            resp = requests.post(
                url,
                headers={"X-Api-Key": MANAGER_APIKEY, "Content-Type": "application/json"},
                json=mapear_a_manager(doc, tipo),
                timeout=30,
            )
            resultados.append({"id": doc.get("id"), "ok": resp.ok, "status": resp.status_code})
        except requests.RequestException as e:
            resultados.append({"id": doc.get("id"), "ok": False, "error": str(e)})

    return jsonify({"resultados": resultados})


@app.route("/api/manager/status")
def api_manager_status():
    configurado = bool(MANAGER_DOMAIN and MANAGER_BUSINESS_ID and MANAGER_APIKEY)
    return jsonify({"configurado": configurado})


def mapear_detalle_a_manager(folio, proveedor, fecha, items):
    """Arma el payload de Manager con el detalle real de items (uno por
    linea), cada uno con su cuenta contable asignada por finanzas."""
    return {
        "issueDate": fecha,
        "reference": str(folio),
        "supplier": proveedor,
        "Lines": [{
            "lineDescription": it.get("descripcion"),
            "qty": it.get("cantidad", 1),
            "UnitPrice": {"value": it.get("precioUnitario"), "currency": ""},
            "code": it.get("codigo"),
            "account": it.get("cuentaContable"),
        } for it in items],
    }


@app.route("/api/manager/upload-detalle", methods=["POST"])
def api_manager_upload_detalle():
    if not (MANAGER_DOMAIN and MANAGER_BUSINESS_ID and MANAGER_APIKEY):
        return jsonify({"error": "Conexión a Manager no configurada en .env"}), 500

    body = request.get_json(force=True)
    folio = body.get("folio")
    proveedor = body.get("proveedor")
    fecha = body.get("fecha")
    items = body.get("items", [])

    sin_codigo = [it for it in items if not it.get("codigo") or not it.get("cuentaContable")]
    if sin_codigo:
        return jsonify({
            "error": f"{len(sin_codigo)} ítem(s) sin código o cuenta contable asignada",
        }), 400

    url = f"{MANAGER_DOMAIN.rstrip('/')}/api2/{MANAGER_BUSINESS_ID}/purchase-invoice-form"
    try:
        resp = requests.post(
            url,
            headers={"X-Api-Key": MANAGER_APIKEY, "Content-Type": "application/json"},
            json=mapear_detalle_a_manager(folio, proveedor, fecha, items),
            timeout=30,
        )
        return jsonify({"ok": resp.ok, "status": resp.status_code}), (200 if resp.ok else 502)
    except requests.RequestException as e:
        return jsonify({"ok": False, "error": str(e)}), 502


# ---------------------------------------------------------------
# Servir el frontend estático
# ---------------------------------------------------------------
@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


preparar_certificado()

if __name__ == "__main__":
    try:
        validar_config()
    except RuntimeError as e:
        print(f"\n⚠️  Configuración incompleta: {e}")
        print("Copia .env.example a .env y completa tus credenciales.\n")
    port = int(os.environ.get("PORT", 5000))  # Render/Railway asignan PORT automáticamente
    debug = os.environ.get("FLASK_DEBUG", "1") == "1"
    app.run(host="0.0.0.0", port=port, debug=debug)
