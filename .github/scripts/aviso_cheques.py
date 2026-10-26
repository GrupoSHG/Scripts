"""Aviso por correo de cheques por cobrar (Dashboard Finanzas → Cheques).

Lo corre .github/workflows/aviso-cheques.yml de lunes a viernes a las 08:05 (lo dispara
automatizacion.programa() en Supabase). Lee los cheques en cartera de
shg_dashboards.cheques_por_cobrar y, si hay alguno que se cobra HOY (o con fecha ya
cumplida y aún sin depositar) o el PRÓXIMO DÍA HÁBIL (el viernes cubre sábado, domingo y
lunes), envía un correo con esos cheques y la lista de los siguientes por cobrar.
Si no hay nada que avisar, no envía.

Variables de entorno:
  SUPABASE_SERVICE_KEY   clave de servicio (lectura de la tabla)
  MAIL_USER, MAIL_PASS   cuenta Gmail que envía y su contraseña de aplicación
  MAIL_TO                destinatarios separados por coma
  FORZAR                 "true": envía aunque no haya cheques hoy ni mañana (prueba)

Repo público: el log solo muestra cantidades, nunca clientes ni montos.
"""
import json
import os
import smtplib
import ssl
import sys
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta
from email.message import EmailMessage
from html import escape
from zoneinfo import ZoneInfo

SUPABASE_URL = "https://ffxopvzxyeacpbtxuagu.supabase.co"
URL_CHEQUES = "https://gruposhg-finanzas.netlify.app/cheques.html"
EMPRESAS = {"polchile": "Polchile", "m5": "M5 Industrial", "cys": "CyS"}
MAX_SIGUIENTES = 15


def leer_cheques():
    """Cheques en cartera, ordenados por fecha de cobro."""
    key = os.environ["SUPABASE_SERVICE_KEY"]
    campos = "empresa,cliente,rut_cliente,banco,numero_cheque,monto,fecha_cobro,facturas,observacion"
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/cheques_por_cobrar?estado=eq.en_cartera&select={campos}"
        "&order=fecha_cobro.asc,id.asc",
        headers={"apikey": key, "Authorization": "Bearer " + key, "Accept-Profile": "shg_dashboards"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise SystemExit(f"Supabase respondió HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:300]}")


def proximo_habil(d):
    d += timedelta(days=1)
    while d.isoweekday() > 5:
        d += timedelta(days=1)
    return d


def clasificar(cheques, hoy):
    """(hoy, próximo hábil, siguientes): hoy incluye los de fecha cumplida aún en cartera."""
    limite = proximo_habil(hoy)
    de_hoy, de_manana, siguientes = [], [], []
    for c in cheques:
        f = date.fromisoformat(c["fecha_cobro"])
        if f <= hoy:
            de_hoy.append(c)
        elif f <= limite:
            de_manana.append(c)
        else:
            siguientes.append(c)
    return de_hoy, de_manana, siguientes, limite


def pesos(n):
    return "$" + f"{round(float(n or 0)):,}".replace(",", ".")


def fecha_cl(iso):
    d = date.fromisoformat(iso)
    dias = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]
    return f"{dias[d.weekday()]} {d:%d-%m-%Y}"


def tabla(cheques, hoy, con_atraso=False):
    filas = []
    for c in cheques:
        f = date.fromisoformat(c["fecha_cobro"])
        nota = ""
        if con_atraso and f < hoy:
            dias = (hoy - f).days
            nota = (f'<br><span style="color:#b23a3a;font-size:11px">fecha cumplida hace {dias} '
                    f'día{"s" if dias != 1 else ""}, sin depositar</span>')
        detalle = " · ".join(x for x in [
            escape(c.get("banco") or ""), ("N° " + escape(c["numero_cheque"])) if c.get("numero_cheque") else "",
            ("Fact. " + escape(c["facturas"])) if c.get("facturas") else ""] if x)
        filas.append(
            '<tr>'
            f'<td style="padding:7px 10px;border-bottom:1px solid #eef2f6;white-space:nowrap">{fecha_cl(c["fecha_cobro"])}{nota}</td>'
            f'<td style="padding:7px 10px;border-bottom:1px solid #eef2f6">{escape(c["cliente"])}'
            f'<br><span style="color:#64748b;font-size:11px">{detalle or "&nbsp;"}</span></td>'
            f'<td style="padding:7px 10px;border-bottom:1px solid #eef2f6;color:#64748b;font-size:12px">'
            f'{escape(EMPRESAS.get(c["empresa"], c["empresa"]))}</td>'
            f'<td style="padding:7px 10px;border-bottom:1px solid #eef2f6;text-align:right;font-weight:700;white-space:nowrap">{pesos(c["monto"])}</td>'
            '</tr>')
    total = sum(float(c["monto"]) for c in cheques)
    return ('<table style="width:100%;border-collapse:collapse;font-size:13px;margin:6px 0 4px">'
            + "".join(filas)
            + f'<tr><td colspan="3" style="padding:7px 10px;text-align:right;color:#64748b">Total</td>'
              f'<td style="padding:7px 10px;text-align:right;font-weight:700;white-space:nowrap">{pesos(total)}</td></tr>'
            + '</table>')


def seccion(titulo, color, cuerpo):
    return (f'<div style="margin:18px 0 0"><div style="font-size:14px;font-weight:700;color:{color};'
            f'border-bottom:2px solid {color};padding-bottom:4px">{titulo}</div>{cuerpo}</div>')


def armar_correo(cheques, hoy, forzar=False):
    """(asunto, html, texto) o None si no hay nada que avisar."""
    de_hoy, de_manana, siguientes, limite = clasificar(cheques, hoy)
    if not de_hoy and not de_manana and not forzar:
        return None
    partes = []
    if de_hoy:
        partes.append(f"hoy {len(de_hoy)} ({pesos(sum(float(c['monto']) for c in de_hoy))})")
    if de_manana:
        cuando = "mañana" if limite == hoy + timedelta(days=1) else f"el {fecha_cl(limite.isoformat())}"
        partes.append(f"{cuando} {len(de_manana)} ({pesos(sum(float(c['monto']) for c in de_manana))})")
    asunto = "Cheques por cobrar: " + (" · ".join(partes) if partes else "sin cobros hoy ni mañana")

    nombre_limite = "mañana" if limite == hoy + timedelta(days=1) else \
        f"hasta el {fecha_cl(limite.isoformat())} (próximo día hábil)"
    cuerpo = ""
    if de_hoy:
        cuerpo += seccion(f"Se cobran hoy — depositar ({len(de_hoy)})", "#b45309", tabla(de_hoy, hoy, con_atraso=True))
    if de_manana:
        cuerpo += seccion(f"Se cobran {nombre_limite} ({len(de_manana)})", "#0b4c8c", tabla(de_manana, hoy))
    if siguientes:
        extra = (f'<div style="font-size:12px;color:#64748b">… y {len(siguientes) - MAX_SIGUIENTES} más en la página.</div>'
                 if len(siguientes) > MAX_SIGUIENTES else "")
        cuerpo += seccion(f"Siguientes cheques por cobrar ({len(siguientes)})", "#334155",
                          tabla(siguientes[:MAX_SIGUIENTES], hoy) + extra)
    if not cheques:
        cuerpo += '<p style="font-size:13px;color:#64748b">No hay cheques en cartera.</p>'
    total = sum(float(c["monto"]) for c in cheques)
    html = f"""
<div style="font-family:Arial,sans-serif;max-width:640px;color:#0f172a">
  <div style="background:#073760;color:#fff;padding:16px 20px;border-radius:12px 12px 0 0">
    <div style="font-size:18px;font-weight:700">Cheques por cobrar</div>
    <div style="font-size:13px;opacity:.85">{fecha_cl(hoy.isoformat())} · En cartera: {len(cheques)} cheques por {pesos(total)}</div>
  </div>
  <div style="border:1px solid #e2e8f0;border-top:0;padding:4px 20px 18px;border-radius:0 0 12px 12px">
    {cuerpo}
    <p style="margin:20px 0 0"><a href="{URL_CHEQUES}" style="display:inline-block;background:#0b4c8c;color:#fff;
      text-decoration:none;padding:10px 18px;border-radius:8px;font-weight:700;font-size:13px">Abrir cheques en el dashboard</a></p>
    <p style="margin:12px 0 0;font-size:11px;color:#94a3b8">Al depositar o cobrar un cheque, márcalo en el dashboard para que no vuelva a aparecer en este aviso.</p>
  </div>
</div>"""
    lineas = [asunto, ""]
    for titulo, lista in (("Se cobran hoy", de_hoy), ("Se cobran " + nombre_limite, de_manana),
                          ("Siguientes", siguientes[:MAX_SIGUIENTES])):
        if lista:
            lineas.append(titulo + ":")
            lineas += [f"  {c['fecha_cobro']}  {c['cliente']}  N° {c.get('numero_cheque') or '-'}  {pesos(c['monto'])}"
                       for c in lista]
            lineas.append("")
    lineas.append(URL_CHEQUES)
    return asunto, html, "\n".join(lineas)


def enviar(asunto, html, texto):
    user, pw = os.environ.get("MAIL_USER"), os.environ.get("MAIL_PASS")
    if not user or not pw:
        raise SystemExit("Faltan MAIL_USER / MAIL_PASS para enviar el aviso.")
    para = [x.strip() for x in (os.environ.get("MAIL_TO") or "").split(",") if x.strip()]
    if not para:
        raise SystemExit("Falta MAIL_TO.")
    msg = EmailMessage()
    msg["Subject"] = asunto
    msg["From"] = f"Finanzas Grupo SHG <{user}>"
    msg["To"] = ", ".join(para)
    msg.set_content(texto)
    msg.add_alternative(html, subtype="html")
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ssl.create_default_context()) as s:
        s.login(user, pw)
        s.send_message(msg)
    return len(para)


def main():
    hoy = datetime.now(ZoneInfo("America/Santiago")).date()
    forzar = os.environ.get("FORZAR") == "true"
    cheques = leer_cheques()
    correo = armar_correo(cheques, hoy, forzar)
    de_hoy, de_manana, siguientes, _ = clasificar(cheques, hoy)
    print(f"{hoy}: {len(cheques)} en cartera; hoy {len(de_hoy)}, próximo hábil {len(de_manana)}, siguientes {len(siguientes)}")
    if correo is None:
        print("Sin cheques que cobrar hoy ni el próximo día hábil: no se envía.")
        return 0
    n = enviar(*correo)
    print(f"Aviso enviado a {n} destinatario(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
