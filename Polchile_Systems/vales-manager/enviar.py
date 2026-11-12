"""Sube los vales de Manager a Drive y los manda por correo (12/11/2026).

Lee ./salida/resumen.json y los .xls que dejó vales.js:
  * Drive: subcarpeta "Vales para Manager" de la carpeta del pipeline (misma
    cuenta de servicio GOOGLE_CREDENTIALS_JSON que el pipeline y el respaldo).
  * Correo (MAIL_USER / MAIL_PASS, destinatarios en MAIL_TO): los archivos
    adjuntos y, por OP, el producto ingresado y los componentes que salen.
    modo hora → asunto "Vales para Manager · <hora>"; modo dia → "Producción
    del día sin subir a Manager" (solo si quedan vales sin marcar importados).
El repo es público: el log solo muestra cantidades, nunca códigos ni OP.
"""
import json
import os
import smtplib
import ssl
import sys
from email.message import EmailMessage
from html import escape
from pathlib import Path

SALIDA = Path(__file__).parent / "salida"
CARPETA_PIPELINE = "1AQgW1Mrr4MbBNi7yXA8kPNpjZBoo9Ntq"   # misma que respaldo_supabase_drive.py
SUBCARPETA = "Vales para Manager"
MIME_CARPETA = "application/vnd.google-apps.folder"
URL_AVANCE = "https://gruposhg-produccion.netlify.app/avance.html"


def fmt(n, d=2):
    s = f"{n:,.{d}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return s.rstrip("0").rstrip(",") if "," in s else s


def subir_drive(archivos):
    cred = os.environ.get("GOOGLE_CREDENTIALS_JSON")
    if not cred:
        print("Sin GOOGLE_CREDENTIALS_JSON: no se sube a Drive.")
        return None
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    creds = service_account.Credentials.from_service_account_info(
        json.loads(cred), scopes=["https://www.googleapis.com/auth/drive"])
    drive = build("drive", "v3", credentials=creds)
    q = (f"name='{SUBCARPETA}' and '{CARPETA_PIPELINE}' in parents "
         f"and mimeType='{MIME_CARPETA}' and trashed=false")
    r = drive.files().list(q=q, fields="files(id, webViewLink)", supportsAllDrives=True,
                           includeItemsFromAllDrives=True).execute()
    if r["files"]:
        carpeta, link = r["files"][0]["id"], r["files"][0].get("webViewLink")
    else:
        f = drive.files().create(body={"name": SUBCARPETA, "mimeType": MIME_CARPETA, "parents": [CARPETA_PIPELINE]},
                                 fields="id, webViewLink", supportsAllDrives=True).execute()
        carpeta, link = f["id"], f.get("webViewLink")
    for a in archivos:
        media = MediaFileUpload(str(SALIDA / a), mimetype="application/vnd.ms-excel", resumable=False)
        drive.files().create(body={"name": a, "parents": [carpeta]}, media_body=media, fields="id",
                             supportsAllDrives=True).execute()
    print(f"Subidos a Drive: {len(archivos)} archivo(s).")
    return link


def armar_correo(res, link):
    dia = res["modo"] == "dia"
    if dia:
        asunto = f"Producción del día sin subir a Manager · {res['fecha']}"
        intro = ("Estos vales de hoy todavía no se marcan como importados en Manager. "
                 "Adjunto los archivos con la producción completa del día de cada OP.")
    else:
        h = res.get("hora", "")
        asunto = f"Vales para Manager · {res['fecha']} {h[:2]}:{h[2:]}"
        intro = "Vales armados con el avance de planta de la última hora, listos para importar en Manager."
    html = [f"<p>{escape(intro)}</p>",
            f"<p><b>{res['ingresos']}</b> vale(s) de ingreso y <b>{res['salidas']}</b> de salida.</p>"]
    texto = [intro, f"{res['ingresos']} vale(s) de ingreso y {res['salidas']} de salida.", ""]
    for o in res["ops"]:
        html.append(f"<h3 style='margin:14px 0 4px'>OP {o['op']}{' · NV ' + str(o['nv']) if o.get('nv') else ''}</h3>")
        texto.append(f"OP {o['op']}" + (f" · NV {o['nv']}" if o.get("nv") else ""))
        for grupo, titulo in (("ingresos", "Ingreso"), ("salidas", "Salida")):
            for v in o[grupo]:
                html.append(f"<div><b>{titulo} N° {v['numero']}</b> · {escape(v.get('glosa') or '')}</div><ul style='margin:2px 0 6px'>")
                texto.append(f"  {titulo} N° {v['numero']}")
                for l in v["lineas"]:
                    lote = f" · lote {l['lote']}" if l.get("lote") else ""
                    html.append(f"<li>{escape(l['codigo'])} {escape(l.get('nombre') or '')}: "
                                f"<b>{fmt(l['cantidad'])}</b> {escape(l.get('unidad') or '')}{escape(lote)}</li>")
                    texto.append(f"    {l['codigo']}: {fmt(l['cantidad'])} {l.get('unidad') or ''}{lote}")
                html.append("</ul>")
    pie = "Después de importarlos en Manager, márcalos como importados en Avance por subir: " + URL_AVANCE
    html.append(f"<p>{escape(pie.split(': ')[0])}: <a href='{URL_AVANCE}'>Avance por subir</a>.</p>")
    texto.append("")
    texto.append(pie)
    if link:
        html.append(f"<p>Carpeta de Drive: <a href='{link}'>{SUBCARPETA}</a></p>")
        texto.append(f"Carpeta de Drive: {link}")
    return asunto, "\n".join(html), "\n".join(texto)


def enviar(asunto, html, texto, archivos):
    user, pw = os.environ.get("MAIL_USER"), os.environ.get("MAIL_PASS")
    para = [x.strip() for x in (os.environ.get("MAIL_TO") or "").split(",") if x.strip()]
    if not user or not pw or not para:
        print("Faltan MAIL_USER / MAIL_PASS / MAIL_TO: no se envía correo.")
        return 0
    msg = EmailMessage()
    msg["Subject"] = asunto
    msg["From"] = f"Producción Polchile <{user}>"
    msg["To"] = ", ".join(para)
    msg.set_content(texto)
    msg.add_alternative(html, subtype="html")
    for a in archivos:
        msg.add_attachment((SALIDA / a).read_bytes(), maintype="application", subtype="vnd.ms-excel", filename=a)
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ssl.create_default_context()) as s:
        s.login(user, pw)
        s.send_message(msg)
    return len(para)


def main():
    ruta = SALIDA / "resumen.json"
    if not ruta.exists():
        print("No hay resumen: nada que enviar.")
        return 0
    res = json.loads(ruta.read_text(encoding="utf-8"))
    if not res.get("vales"):
        print("Sin vales: no se sube ni se envía nada.")
        return 0
    archivos = res.get("archivos") or []
    link = subir_drive(archivos)
    n = enviar(*armar_correo(res, link), archivos)
    print(f"Correo enviado a {n} destinatario(s) con {len(archivos)} archivo(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
