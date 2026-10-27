"""Avisos por correo del flujo de documentos de la App CyS.

Lo corre .github/workflows/aviso-cys.yml, que dispara automatizacion.programa() en
Supabase solo cuando hay avisos pendientes. Lee app_cys.avisos_pendientes (un aviso por
cambio de estado de un documento, con sus destinatarios ya resueltos por rol):

  por_revisar  → supervisores de la app (el documento se leyó y espera su check)
  por_aprobar  → admin de la app (tiene el check del supervisor; falta la aprobación final)
  rechazado    → el otro rol (supervisor si rechazó el admin, admin si rechazó el supervisor)

Envía UN correo por destinatario con todos sus documentos y marca cada aviso con
app_cys.marcar_avisos_correo (enviado, o un intento más con el error).

Variables de entorno:
  SUPABASE_SERVICE_KEY   clave de servicio (lee la vista y marca los avisos)
  MAIL_USER, MAIL_PASS   cuenta Gmail que envía y su contraseña de aplicación

Repo público: el log solo muestra cantidades, nunca proveedores, montos ni correos.
"""
import json
import os
import smtplib
import ssl
import sys
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import datetime
from email.message import EmailMessage
from html import escape
from zoneinfo import ZoneInfo

SUPABASE_URL = "https://ffxopvzxyeacpbtxuagu.supabase.co"
URL_APP = "https://gruposhg-app-cys.netlify.app"
MEDIOS = {"caja_chica": "Caja chica", "caja_general": "Caja chica CyS", "tarjeta_empresa": "Tarjeta empresa",
          "transferencia": "Transferencia", "otro": "Otro"}
SECCIONES = [
    ("por_revisar", "Por revisar", "#B45309", "Se leyeron y esperan tu check en Gastos → Por revisar."),
    ("por_aprobar", "Por aprobar", "#2C5233", "Tienen el check del supervisor y esperan tu aprobación final en Gastos → Por aprobar."),
    ("rechazado", "Rechazados", "#B91C1C", "No cuentan como gasto."),
]


def _supabase(ruta, metodo="GET", cuerpo=None):
    key = os.environ["SUPABASE_SERVICE_KEY"]
    datos = json.dumps(cuerpo).encode("utf-8") if cuerpo is not None else None
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/{ruta}", data=datos, method=metodo,
        headers={"apikey": key, "Authorization": "Bearer " + key, "Accept-Profile": "app_cys",
                 "Content-Profile": "app_cys", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode("utf-8") or "null")
    except urllib.error.HTTPError as e:
        raise SystemExit(f"Supabase respondió HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:300]}")


def leer_avisos():
    return _supabase("avisos_pendientes?select=*&order=creado_en.asc,id.asc")


def marcar(ids, ok, error=None):
    if ids:
        _supabase("rpc/marcar_avisos_correo", "POST", {"p_ids": sorted(ids), "p_ok": ok, "p_error": error})


def agrupar(avisos):
    """{destinatario: [avisos]} y los avisos sin destinatario."""
    por_correo, sin_destino = defaultdict(list), []
    for a in avisos:
        destinos = [d for d in (a.get("destinatarios") or []) if d]
        if not destinos:
            sin_destino.append(a)
        for d in destinos:
            por_correo[d].append(a)
    return dict(por_correo), sin_destino


def pesos(n):
    return "—" if n is None else "$" + f"{round(float(n)):,}".replace(",", ".")


def fecha_cl(iso):
    if not iso:
        return "—"
    try:
        return datetime.strptime(str(iso)[:10], "%Y-%m-%d").strftime("%d-%m-%Y")
    except ValueError:
        return str(iso)


def _detalle(a):
    if a["evento"] == "por_revisar":
        extra = f"subido por {a.get('subido_por_email') or '—'}"
        if a.get("motivos"):
            extra += " · revisar: " + "; ".join(a["motivos"][:2])
        return extra
    if a["evento"] == "por_aprobar":
        medio = MEDIOS.get(a.get("medio_pago"), a.get("medio_pago") or "sin medio de pago")
        return f"check de {a.get('actor_email') or '—'} · {a.get('categoria') or '—'} · {medio}"
    motivo = "; ".join(a.get("motivos") or []) or "sin motivo"
    return f"rechazado por {a.get('actor_email') or '—'} · {motivo}"


def armar_correo(avisos):
    """(asunto, html, texto) para un destinatario con sus avisos."""
    cuenta = {k: sum(1 for a in avisos if a["evento"] == k) for k, *_ in SECCIONES}
    partes = []
    if cuenta["por_revisar"]:
        partes.append(f"{cuenta['por_revisar']} por revisar")
    if cuenta["por_aprobar"]:
        partes.append(f"{cuenta['por_aprobar']} por aprobar")
    if cuenta["rechazado"]:
        partes.append(f"{cuenta['rechazado']} rechazado{'s' if cuenta['rechazado'] != 1 else ''}")
    asunto = "App CyS: " + ", ".join(partes)

    bloques, lineas = [], [asunto, ""]
    for clave, titulo, color, ayuda in SECCIONES:
        filas = [a for a in avisos if a["evento"] == clave]
        if not filas:
            continue
        total = sum(float(a.get("total") or 0) for a in filas)
        cuerpo = "".join(
            "<tr>"
            f"<td style='padding:6px 8px;border-top:1px solid #EEF1EF'>{escape(a.get('obra') or '—')}</td>"
            f"<td style='padding:6px 8px;border-top:1px solid #EEF1EF'><b>{escape(a.get('razon_social') or 'Proveedor sin leer')}</b><br>"
            f"<span style='color:#6B7F71;font-size:12px'>{escape((a.get('tipo_documento') or '—') + (' N° ' + a['folio'] if a.get('folio') else ''))}"
            f" · {fecha_cl(a.get('fecha_documento'))}<br>{escape(_detalle(a))}</span></td>"
            f"<td style='padding:6px 8px;border-top:1px solid #EEF1EF;text-align:right;white-space:nowrap'><b>{pesos(a.get('total'))}</b></td>"
            "</tr>" for a in filas)
        bloques.append(
            f"<h3 style='margin:20px 0 4px;color:{color}'>{titulo} ({len(filas)}) · {pesos(total)}</h3>"
            f"<p style='margin:0 0 6px;color:#6B7F71;font-size:13px'>{ayuda}</p>"
            f"<table style='border-collapse:collapse;width:100%;font-size:14px'>{cuerpo}</table>")
        lineas.append(f"{titulo} ({len(filas)}) · {pesos(total)}")
        for a in filas:
            lineas.append(f"  - {a.get('obra') or '—'} · {a.get('razon_social') or 'Proveedor sin leer'} · "
                          f"{pesos(a.get('total'))} · {_detalle(a)}")
        lineas.append("")

    html = f"""<div style="font-family:Arial,sans-serif;color:#1F3D26;max-width:640px">
<h2 style="margin:0 0 4px">App CyS · {escape(', '.join(partes))}</h2>
{''.join(bloques)}
<p style="margin:24px 0 0"><a href="{URL_APP}" style="background:#2C5233;color:#fff;padding:10px 16px;border-radius:8px;text-decoration:none">Abrir la App CyS</a></p>
<p style="color:#6B7F71;font-size:12px;margin-top:16px">Aviso automático de la App CyS según tu rol en la app.</p>
</div>"""
    lineas.append(URL_APP)
    return asunto, html, "\n".join(lineas)


def enviar(para, asunto, html, texto, conexion):
    msg = EmailMessage()
    msg["Subject"] = asunto
    msg["From"] = f"App CyS <{os.environ['MAIL_USER']}>"
    msg["To"] = para
    msg.set_content(texto)
    msg.add_alternative(html, subtype="html")
    conexion.send_message(msg)


def main():
    user, pw = os.environ.get("MAIL_USER"), os.environ.get("MAIL_PASS")
    if not user or not pw:
        raise SystemExit("Faltan MAIL_USER / MAIL_PASS.")
    avisos = leer_avisos()
    por_correo, sin_destino = agrupar(avisos)
    ahora = datetime.now(ZoneInfo("America/Santiago")).strftime("%Y-%m-%d %H:%M")
    print(f"{ahora}: {len(avisos)} aviso(s) pendiente(s), {len(por_correo)} destinatario(s), {len(sin_destino)} sin destinatario")
    if sin_destino:  # nadie con ese rol en la app: se cierran para no reintentar
        marcar({a["id"] for a in sin_destino}, True)
    if not por_correo:
        return 0

    fallidos = set()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ssl.create_default_context()) as s:
        s.login(user, pw)
        for para, lista in por_correo.items():
            try:
                enviar(para, *armar_correo(lista), s)
            except smtplib.SMTPException as e:
                fallidos.add(para)
                print(f"Un correo falló ({type(e).__name__}).")
    ok_ids = {a["id"] for d, lista in por_correo.items() if d not in fallidos for a in lista}
    error_ids = {a["id"] for d in fallidos for a in por_correo[d]}
    ok_ids -= error_ids
    marcar(ok_ids, True)
    marcar(error_ids, False, "falló el envío a algún destinatario")
    print(f"Correos enviados: {len(por_correo) - len(fallidos)}; fallidos: {len(fallidos)}; avisos cerrados: {len(ok_ids)}")
    return 1 if fallidos else 0


if __name__ == "__main__":
    sys.exit(main())
