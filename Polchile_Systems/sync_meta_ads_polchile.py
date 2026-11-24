"""Carga el gasto de Meta Ads (Facebook / Instagram) de Polchile en Supabase (polchile_crm.inversion_ads).

Lee la Marketing API de Meta (insights por campaña y por día de las cuentas publicitarias de
META_ADS_CUENTAS) y manda las filas al RPC polchile_crm.cargar_inversion_ads con plataforma 'meta',
el mismo que usa sync_ads_polchile.py para Google. El RPC reemplaza las fechas cubiertas y conserva
el resto de la historia (SQL en Polchile_Systems/inversion_ads.sql). Lo lee
polchile_crm.resumen_dashboard para la inversión, el costo por lead y el retorno de Meta en la
pestaña CRM del Cockpit Comercial. Instalación: Polchile_Systems/INVERSION_ADS.md (sección Meta Ads).

Meta ajusta el gasto y las conversiones de los últimos días (atribución de hasta 28 días), por eso
cada corrida reescribe una ventana completa (--dias, 30 por omisión).

Las cuentas de Meta pueden estar en USD: el costo se pasa a CLP con el dólar observado del día
(mindicador.cl, el del Banco Central). La tabla guarda CLP sin IVA.

No usar a la vez con la pestaña "meta" de la hoja de Google: los dos cargan la plataforma 'meta' y
cada carga reemplaza las fechas de la otra.

Variables de entorno: META_ADS_TOKEN (token de un usuario del sistema del portfolio comercial con
permiso ads_read sobre las cuentas), META_ADS_CUENTAS (ids de las cuentas separados por coma, con o
sin "act_"), SUPABASE_SERVICE_KEY. Para probar en local se pueden poner en un .env junto a este
archivo (no se sube a git):
  python Polchile_Systems/sync_meta_ads_polchile.py --simular --dias 90
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta

_ENV = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(_ENV):
    for _l in open(_ENV, encoding="utf-8"):
        _k, _, _v = _l.strip().partition("=")
        if _k and not _k.startswith("#"):
            os.environ.setdefault(_k.strip(), _v.strip().strip('"'))

SUPABASE_URL = "https://ffxopvzxyeacpbtxuagu.supabase.co"
GRAPH = "https://graph.facebook.com/" + os.environ.get("META_API_VERSION", "v23.0")
DIAS = 30
LOTE = 5000                           # filas por llamada; se parte solo entre fechas distintas
# Acciones que cuentan como conversión de Meta (no son leads del CRM, igual que en Google):
# formularios de clientes potenciales y conversaciones de WhatsApp / Messenger iniciadas.
CONVERSIONES = ("lead", "onsite_conversion.messaging_conversation_started_7d")


def cuentas():
    v = [c.strip() for c in os.environ.get("META_ADS_CUENTAS", "").split(",") if c.strip()]
    if not v:
        raise SystemExit("Falta META_ADS_CUENTAS (ids de las cuentas publicitarias de Meta, separados por coma)")
    return [c if c.startswith("act_") else "act_" + c for c in v]


def token():
    v = os.environ.get("META_ADS_TOKEN", "").strip()
    if not v:
        raise SystemExit("Falta META_ADS_TOKEN (token de usuario del sistema con ads_read)")
    return v


def graph(url):
    """GET a la Graph API con 3 intentos ante límite de uso o error 5xx."""
    for intento in range(3):
        try:
            with urllib.request.urlopen(url, timeout=120) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            cuerpo = e.read().decode("utf-8", "replace")
            try:
                err = json.loads(cuerpo).get("error", {})
            except ValueError:
                err = {}
            # 4/17/80004 = límite de llamadas; se espera y se reintenta
            if (e.code >= 500 or err.get("code") in (4, 17, 80004)) and intento < 2:
                time.sleep(30)
                continue
            raise SystemExit(f"Meta rechazó la consulta (HTTP {e.code}): {err.get('message') or cuerpo[:500]}")


def insights(cuenta, desde, hasta):
    """Gasto diario por campaña de una cuenta; devuelve (moneda, filas crudas)."""
    tk = token()
    info = graph(f"{GRAPH}/{cuenta}?" + urllib.parse.urlencode({"fields": "currency,name", "access_token": tk}))
    url = f"{GRAPH}/{cuenta}/insights?" + urllib.parse.urlencode({
        "level": "campaign", "time_increment": 1,
        "time_range": json.dumps({"since": desde.isoformat(), "until": hasta.isoformat()}),
        "fields": "campaign_id,campaign_name,spend,impressions,clicks,actions",
        "limit": 500, "access_token": tk,
    })
    filas = []
    while url:
        r = graph(url)
        filas += r.get("data", [])
        url = r.get("paging", {}).get("next")
    print(f"{cuenta} ({info.get('name')}, {info.get('currency')}): {len(filas)} filas")
    return info.get("currency", "CLP"), filas


def dolar_por_dia(desde, hasta):
    """Dólar observado de cada día del rango; fines de semana y feriados usan el último valor publicado."""
    def leer(ruta):
        for intento in range(2):
            try:
                req = urllib.request.Request(f"https://mindicador.cl/api/{ruta}", headers={"User-Agent": "curl/8.0"})
                with urllib.request.urlopen(req, timeout=60) as r:
                    return {p["fecha"][:10]: float(p["valor"]) for p in json.loads(r.read().decode()).get("serie", [])}
            except OSError:                 # incluye timeouts y cortes de conexión
                if intento == 0:
                    time.sleep(10)
        return None

    # /api/dolar trae los últimos ~30 valores; /api/dolar/<año> es más lento y solo se pide cuando
    # la ventana es más larga (primera carga con --dias 400). mindicador.cl a veces no contesta: en
    # ese caso se usa el cambio de hoy (open.er-api.com) para toda la ventana, con aviso en el log.
    serie = leer("dolar")
    if serie and min(serie) > (desde - timedelta(days=7)).isoformat():
        for anio in range(desde.year - (1 if desde.month == 1 else 0), hasta.year + 1):
            s = leer(f"dolar/{anio}")
            if s is None:
                serie = None
                break
            serie.update(s)
    if not serie:
        with urllib.request.urlopen("https://open.er-api.com/v6/latest/USD", timeout=60) as r:
            hoy = float(json.loads(r.read().decode())["rates"]["CLP"])
        print(f"  aviso: mindicador.cl no respondió; se usa el dólar de hoy ({hoy:,.2f}) para todo el rango")
        serie = {(desde - timedelta(days=1)).isoformat(): hoy}
    if not serie:
        raise SystemExit("mindicador.cl no devolvió el dólar observado")
    fechas = sorted(serie)
    tasas, ultimo, i = {}, None, 0
    d = date.fromisoformat(fechas[0])
    while d <= hasta:
        while i < len(fechas) and fechas[i] <= d.isoformat():
            ultimo = serie[fechas[i]]
            i += 1
        if d >= desde:
            tasas[d.isoformat()] = ultimo
        d += timedelta(days=1)
    return tasas


def a_filas(crudas, moneda, tasas):
    filas = []
    for x in crudas:
        f = x["date_start"]
        acc = {a["action_type"]: float(a["value"]) for a in x.get("actions", [])}
        costo = float(x.get("spend") or 0)
        if moneda != "CLP":
            if moneda != "USD":
                raise SystemExit(f"Moneda {moneda} sin conversión a CLP (solo CLP y USD)")
            if tasas.get(f) is None:
                raise SystemExit(f"Sin dólar observado para el {f}")
            costo *= tasas[f]
        filas.append({
            "fecha": f,
            "campana_id": x.get("campaign_id", ""),
            "campana": x.get("campaign_name"),
            "costo": round(costo),
            "impresiones": int(x.get("impressions") or 0),
            "clics": int(x.get("clicks") or 0),
            "conversiones": sum(acc.get(t, 0) for t in CONVERSIONES),
        })
    return filas


def lotes(filas):
    """Parte en lotes de hasta LOTE filas sin separar una misma fecha (el RPC reemplaza por rango)."""
    filas = sorted(filas, key=lambda f: f["fecha"])
    actual = []
    for f in filas:
        if len(actual) >= LOTE and actual[-1]["fecha"] != f["fecha"]:
            yield actual
            actual = []
        actual.append(f)
    if actual:
        yield actual


def rpc(funcion, cuerpo):
    key = os.environ["SUPABASE_SERVICE_KEY"]
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/rpc/{funcion}", data=json.dumps(cuerpo).encode("utf-8"),
        headers={"apikey": key, "Authorization": "Bearer " + key, "Content-Type": "application/json",
                 "Content-Profile": "polchile_crm"},
        method="POST")
    for intento in range(3):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                texto = r.read().decode()
                return json.loads(texto) if texto else None
        except urllib.error.HTTPError as e:
            if e.code >= 500 and intento < 2:
                time.sleep(10)
                continue
            raise SystemExit(f"Supabase rechazó {funcion} (HTTP {e.code}): {e.read().decode('utf-8', 'replace')[:500]}")


def main():
    simular = "--simular" in sys.argv
    dias = int(sys.argv[sys.argv.index("--dias") + 1]) if "--dias" in sys.argv else DIAS
    hasta = date.today() - timedelta(days=1)
    desde = hasta - timedelta(days=dias - 1)
    print(f"Meta Ads {desde} a {hasta}")
    filas, tasas = [], None
    for cuenta in cuentas():
        moneda, crudas = insights(cuenta, desde, hasta)
        if moneda != "CLP" and crudas and tasas is None:
            tasas = dolar_por_dia(desde, hasta)
        filas += a_filas(crudas, moneda, tasas or {})
    # Días sin gasto: Meta no devuelve fila y el RPC no los toca.
    filas = [f for f in filas if f["costo"] or f["clics"] or f["impresiones"]]
    if not filas:
        print("meta: sin gasto en la ventana, no se toca Supabase")
        return
    costo = sum(f["costo"] for f in filas)
    fechas = sorted(f["fecha"] for f in filas)
    print(f"meta: {len(filas)} filas, {fechas[0]} a {fechas[-1]}, costo CLP {costo:,.0f}")
    if simular:
        return
    for lote in lotes(filas):
        r = rpc("cargar_inversion_ads", {"p_plataforma": "meta", "p_filas": lote})
        print(f"  cargado: {r}")
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write(f"### Inversión Meta Ads Polchile cargada\n\n- {len(filas)} filas ({fechas[0]} a {fechas[-1]}), costo CLP {costo:,.0f}\n")


def anotar_error(mensaje):
    if not os.environ.get("GITHUB_ACTIONS"):
        return
    print(f"::error::{mensaje}")
    resumen = os.environ.get("GITHUB_STEP_SUMMARY")
    if resumen:
        with open(resumen, "a", encoding="utf-8") as f:
            f.write(f"### Inversión Meta Ads Polchile: falló\n\n```\n{mensaje}\n```\n")


if __name__ == "__main__":
    try:
        main()
    except SystemExit as e:
        if e.code not in (None, 0):
            anotar_error(str(e.code))
        raise
    except Exception as e:
        anotar_error(f"{type(e).__name__}: {e}")
        raise
