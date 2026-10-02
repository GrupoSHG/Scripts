"""Monitoreo de los sistemas Polchile.

Chequea cada sistema (sitios Netlify/Firebase, backends Apps Script, Supabase),
guarda el estado en estado.json y envía un correo cuando un sistema se cae,
cuando sigue caído (recordatorio cada RECORDATORIO_HORAS) y cuando se recupera.

Variables de entorno:
  MAIL_USER, MAIL_PASS   cuenta Gmail y contraseña de aplicación (obligatorias para enviar)
  MAIL_TO                destinatario(s), separados por coma
  ESTADO_PATH            archivo de estado (default: estado.json)
  FORZAR=true            envía el correo con el estado completo aunque no haya cambios
"""
import datetime
import json
import os
import smtplib
import ssl
import sys
import time
import urllib.error
import urllib.request
from email.message import EmailMessage
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Santiago")
TIMEOUT = 60
INTENTOS = 3
ESPERA_REINTENTO = 20
RECORDATORIO_HORAS = 6

APPS_SCRIPT = "https://script.google.com/macros/s/{}/exec?action={}"
SUPABASE_URL = "https://ffxopvzxyeacpbtxuagu.supabase.co"
# Llave publicable (la misma que usan los frontends; no es secreta).
SUPABASE_KEY = "sb_publishable_7UxU-do4iR5rP7Fnx8kQiw_XqDLMaHc"

CHEQUEOS = [
    {"nombre": "Command Center", "tipo": "web", "url": "https://melodic-dasik-d903ff.netlify.app/"},
    {"nombre": "Cockpit Comercial (web)", "tipo": "web", "url": "https://cockpit-comericial-web.netlify.app/"},
    {"nombre": "Dashboard Producción (web)", "tipo": "web", "url": "https://polchile-produccion.netlify.app/"},
    {"nombre": "Dashboard Finanzas (web)", "tipo": "web", "url": "https://dashboard-finanzasweb.netlify.app/"},
    {"nombre": "Calendario Despachos (web)", "tipo": "web", "url": "https://calendario-despachos.netlify.app/"},
    {"nombre": "Hojalatería El Abuelo (Firebase)", "tipo": "web", "url": "https://hojalateria-el-abuelo.web.app/"},
    {"nombre": "Trazabilidad NV (web)", "tipo": "web", "url": "https://trazabilidad-nv-polchile.netlify.app/"},
    {"nombre": "M5 Pipeline y Proyectos (web)", "tipo": "web", "url": "https://m5-proyectos-polchile.netlify.app/"},
    {"nombre": "App CyS (web)", "tipo": "web", "url": "https://appcys.netlify.app/", "min_bytes": 400},
    {"nombre": "Intranet Polchile (web)", "tipo": "web", "url": "https://intranetpolchile.netlify.app/"},
    {"nombre": "Stock por Familias (web)", "tipo": "web", "url": "https://productosstock.netlify.app/"},
    {"nombre": "Cubicador de Ramplas (web)", "tipo": "web", "url": "https://lucky-piroshki-0c9c53.netlify.app/"},
    {"nombre": "Apps Script Finanzas", "tipo": "appscript",
     "url": APPS_SCRIPT.format("AKfycby0pnIUuRy8bjn108mc9ly4eET4Aa8_B0qD4qZrkqJZAGOtKmvYIOmq-M_mv3Fjuc0Y", "getDatos")},
    {"nombre": "Apps Script Producción", "tipo": "appscript",
     "url": APPS_SCRIPT.format("AKfycbxA_Iy0Zr4YOl6LFsN1oEq74Cb-0MVM0pS4Gs-3-X5GLtikCY1fKK4Y77ecjeU6pwd6", "getM2Ayer")},
    {"nombre": "Apps Script Cockpit (Manager ERP)", "tipo": "appscript",
     "url": APPS_SCRIPT.format("AKfycbzdTfqrkCRPTMa0HBcDrDHjxuYBZTSe7G3nGB5EfK_FvElA6jmgsF7-ShQFc-4ntclb", "getResumenPolchile")},
    {"nombre": "Apps Script Calendario", "tipo": "appscript",
     "url": APPS_SCRIPT.format("AKfycbzqtyzqc9YdCWMZMJd8FRGonBkyAve3Er4WB9MEJxRncEsYuyVSudu_yLzdUWfz2HiR_A", "getDashboardData")},
    {"nombre": "Supabase (app_cys)", "tipo": "supabase",
     "url": SUPABASE_URL + "/rest/v1/centros_costo?select=id&limit=1"},
    # El robot manager-descargas corre lun-vie cada hora de 9 a 18: avisa si la última
    # carga completa (Ventas Full + Notas de Venta) tiene más de MAX_HORAS_CARGA en horario laboral.
    {"nombre": "Robot descargas Manager", "tipo": "frescura",
     "url": SUPABASE_URL + "/rest/v1/rpc/ultima_carga_manager"},
]
MAX_HORAS_CARGA = 2


def pedir(url, headers=None, data=None):
    req = urllib.request.Request(url, data=data, headers={"User-Agent": "polchile-monitoreo", **(headers or {})})
    inicio = time.monotonic()
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        cuerpo = r.read().decode("utf-8", errors="replace")
        return r.status, cuerpo, time.monotonic() - inicio


def chequear_frescura(c):
    ahora = datetime.datetime.now(TZ)
    headers = {"apikey": SUPABASE_KEY, "Authorization": "Bearer " + SUPABASE_KEY,
               "Content-Profile": "shg_dashboards", "Content-Type": "application/json"}
    try:
        _, cuerpo, _ = pedir(c["url"], headers, data=b"{}")
        ultima = json.loads(cuerpo)
    except Exception as e:
        return False, f"no se pudo consultar la última carga ({type(e).__name__}: {e})"
    if not ultima:
        return False, "nunca se ha registrado una carga"
    ultima = datetime.datetime.fromisoformat(ultima).astimezone(TZ)
    horas = (ahora - ultima).total_seconds() / 3600
    detalle = f"última carga {ultima:%d-%m %H:%M} (hace {horas:.1f} h)"
    # Solo se exige frescura cuando el robot debió haber corrido: lun-vie desde las 10 hasta las 19.
    en_horario = ahora.isoweekday() <= 5 and 10 <= ahora.hour <= 19
    if en_horario and horas > MAX_HORAS_CARGA:
        return False, detalle + f"; debería cargar cada hora (revisar la corrida 'Manager – descargas cada hora' en Actions)"
    return True, detalle


def chequear_una_vez(c):
    """Devuelve (ok, detalle)."""
    if c["tipo"] == "frescura":
        return chequear_frescura(c)
    headers = None
    if c["tipo"] == "supabase":
        headers = {"apikey": SUPABASE_KEY, "Authorization": "Bearer " + SUPABASE_KEY, "Accept-Profile": "app_cys"}
    try:
        status, cuerpo, seg = pedir(c["url"], headers)
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}"
    except Exception as e:  # timeout, DNS, conexión rechazada
        return False, f"sin respuesta ({type(e).__name__}: {e})"

    if status != 200:
        return False, f"HTTP {status}"
    if c["tipo"] == "web":
        if len(cuerpo) < c.get("min_bytes", 200):
            return False, "página vacía"
    else:
        try:
            datos = json.loads(cuerpo)
        except ValueError:
            # Apps Script devuelve una página HTML cuando el script falla o pide login.
            return False, "la respuesta no es JSON (¿script con error o sin acceso público?)"
        if isinstance(datos, dict) and datos.get("error"):
            return False, f"error del backend: {str(datos['error'])[:200]}"
    return True, f"OK en {seg:.1f}s"


def chequear(c):
    for intento in range(1, INTENTOS + 1):
        ok, detalle = chequear_una_vez(c)
        if ok or intento == INTENTOS:
            return ok, detalle
        time.sleep(ESPERA_REINTENTO)


def cargar_estado(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def enviar_correo(asunto, html, texto):
    user, pw = os.environ.get("MAIL_USER"), os.environ.get("MAIL_PASS")
    if not user or not pw:
        raise SystemExit("Faltan MAIL_USER / MAIL_PASS para enviar el aviso.")
    para = os.environ.get("MAIL_TO") or "atorres@polchile.cl"
    msg = EmailMessage()
    msg["Subject"] = asunto
    msg["From"] = f"Monitoreo Polchile <{user}>"
    msg["To"] = para
    msg.set_content(texto)
    msg.add_alternative(html, subtype="html")
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ssl.create_default_context()) as s:
        s.login(user, pw)
        s.send_message(msg)
    print(f"Correo enviado a {para}: {asunto}")


def fmt_hora(iso):
    return datetime.datetime.fromisoformat(iso).astimezone(TZ).strftime("%d-%m %H:%M")


def tabla_html(resultados, estado):
    filas = ""
    for r in resultados:
        color = "#16a34a" if r["ok"] else "#dc2626"
        desde = "" if r["ok"] else f" · caído desde {fmt_hora(estado[r['nombre']]['desde'])}"
        filas += (f'<tr><td style="padding:6px 10px;border-bottom:1px solid #eee">{r["nombre"]}</td>'
                  f'<td style="padding:6px 10px;border-bottom:1px solid #eee;color:{color};font-weight:700">'
                  f'{"OK" if r["ok"] else "CAÍDO"}</td>'
                  f'<td style="padding:6px 10px;border-bottom:1px solid #eee;color:#555">{r["detalle"]}{desde}</td></tr>')
    return f'<table style="border-collapse:collapse;font-size:13px;width:100%">{filas}</table>'


def lista_html(titulo, color, items):
    if not items:
        return ""
    lis = "".join(f"<li><b>{r['nombre']}</b>: {r['detalle']}</li>" for r in items)
    return f'<p style="margin:14px 0 4px;font-weight:700;color:{color}">{titulo}</p><ul style="margin:0">{lis}</ul>'


def main():
    estado_path = os.environ.get("ESTADO_PATH", "estado.json")
    estado = cargar_estado(estado_path)
    ahora = datetime.datetime.now(datetime.timezone.utc)
    ahora_iso = ahora.isoformat()

    resultados, caidos_nuevos, siguen_caidos, recuperados = [], [], [], []
    for c in CHEQUEOS:
        ok, detalle = chequear(c)
        r = {"nombre": c["nombre"], "url": c["url"], "ok": ok, "detalle": detalle}
        resultados.append(r)
        previo = estado.get(c["nombre"], {"ok": True})
        print(f"{'OK    ' if ok else 'CAÍDO '} {c['nombre']}: {detalle}")

        if ok:
            if not previo["ok"]:
                recuperados.append(r)
            estado[c["nombre"]] = {"ok": True}
        elif previo["ok"]:
            caidos_nuevos.append(r)
            estado[c["nombre"]] = {"ok": False, "desde": ahora_iso, "ultimo_aviso": ahora_iso}
        else:
            ultimo = datetime.datetime.fromisoformat(previo.get("ultimo_aviso", previo["desde"]))
            if ahora - ultimo >= datetime.timedelta(hours=RECORDATORIO_HORAS):
                siguen_caidos.append(r)
                previo["ultimo_aviso"] = ahora_iso
            estado[c["nombre"]] = previo

    # Sistemas que ya no se chequean no deben quedar como caídos para siempre.
    nombres = {c["nombre"] for c in CHEQUEOS}
    estado = {k: v for k, v in estado.items() if k in nombres}
    with open(estado_path, "w", encoding="utf-8") as f:
        json.dump(estado, f, ensure_ascii=False, indent=2)

    caidos_total = [r for r in resultados if not r["ok"]]
    resumen = os.environ.get("GITHUB_STEP_SUMMARY")
    if resumen:
        with open(resumen, "a", encoding="utf-8") as f:
            f.write("| Sistema | Estado | Detalle |\n|---|---|---|\n")
            for r in resultados:
                f.write(f"| {r['nombre']} | {'✅' if r['ok'] else '❌'} | {r['detalle']} |\n")

    forzar = os.environ.get("FORZAR") == "true"
    if not (caidos_nuevos or siguen_caidos or recuperados or forzar):
        print("Sin cambios, no se envía correo.")
        return

    if caidos_nuevos:
        asunto = "🔴 Caído: " + ", ".join(r["nombre"] for r in caidos_nuevos)
    elif siguen_caidos:
        asunto = "🔴 Siguen caídos: " + ", ".join(r["nombre"] for r in siguen_caidos)
    elif recuperados:
        asunto = "🟢 Recuperado: " + ", ".join(r["nombre"] for r in recuperados)
    else:
        asunto = f"Monitoreo Polchile: {len(resultados) - len(caidos_total)}/{len(resultados)} OK (prueba)"

    hora = ahora.astimezone(TZ).strftime("%d-%m-%Y %H:%M")
    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:640px;color:#242722">
      <div style="background:#1f3d52;color:#fff;padding:16px 20px;border-radius:12px 12px 0 0">
        <div style="font-size:18px;font-weight:700">Monitoreo de sistemas Polchile</div>
        <div style="font-size:13px;opacity:.85">{hora} · {len(resultados) - len(caidos_total)} de {len(resultados)} OK</div>
      </div>
      <div style="border:1px solid #e2e0d8;border-top:0;padding:8px 20px 18px;border-radius:0 0 12px 12px">
        {lista_html("Se cayeron", "#dc2626", caidos_nuevos)}
        {lista_html(f"Siguen caídos (recordatorio cada {RECORDATORIO_HORAS} h)", "#dc2626", siguen_caidos)}
        {lista_html("Se recuperaron", "#16a34a", recuperados)}
        <p style="margin:16px 0 6px;font-weight:700">Estado de todos los sistemas</p>
        {tabla_html(resultados, estado)}
      </div>
    </div>"""
    texto = asunto + "\n\n" + "\n".join(
        f"{'OK    ' if r['ok'] else 'CAÍDO '} {r['nombre']}: {r['detalle']}" for r in resultados)
    enviar_correo(asunto, html, texto)


if __name__ == "__main__":
    sys.exit(main())
