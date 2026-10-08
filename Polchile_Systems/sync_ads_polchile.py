"""Carga la inversión publicitaria de Polchile en Supabase (polchile_crm.inversion_ads).

Lee la hoja de Google que escribe el script de Google Ads (Polchile_Systems/google_ads_script.js):
  - pestaña "google": gasto diario por campaña, la reescribe el script cada día;
  - pestaña "meta" (opcional): mismas columnas, se llena a mano con el gasto de Meta Ads.
Cada pestaña se manda completa al RPC polchile_crm.cargar_inversion_ads, que reemplaza las fechas
cubiertas y conserva el resto de la historia (SQL en Polchile_Systems/inversion_ads.sql).
Lo lee polchile_crm.resumen_dashboard para la inversión, el costo por lead y el retorno del Cockpit
y del dashboard CRM Comercial. Instalación: Polchile_Systems/INVERSION_ADS.md.

Columnas esperadas (fila 1 = encabezado, el orden no importa, mayúsculas da igual):
  fecha | campana_id | campana | costo | impresiones | clics | conversiones
Solo fecha y costo son obligatorias. La fecha puede ser texto (yyyy-mm-dd, dd-mm-yyyy, dd/mm/yyyy)
o una celda de fecha de la hoja.

Variables de entorno: GOOGLE_CREDENTIALS_JSON (cuenta de servicio del pipeline, con permiso de
lectura sobre la hoja), SUPABASE_SERVICE_KEY, ADS_POLCHILE_HOJA (id de la hoja).
Para probar en local se pueden poner en un .env junto a este archivo (no se sube a git):
  python Polchile_Systems/sync_ads_polchile.py --simular
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta

from google.oauth2 import service_account
from googleapiclient.discovery import build

_ENV = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(_ENV):
    for _l in open(_ENV, encoding="utf-8"):
        _k, _, _v = _l.strip().partition("=")
        if _k and not _k.startswith("#"):
            os.environ.setdefault(_k.strip(), _v.strip().strip('"'))

SUPABASE_URL = "https://ffxopvzxyeacpbtxuagu.supabase.co"
PLATAFORMAS = ("google", "meta")      # nombre de la pestaña = plataforma
COLUMNAS = ("fecha", "campana_id", "campana", "costo", "impresiones", "clics", "conversiones")
LOTE = 5000                           # filas por llamada; se parte solo entre fechas distintas


def hoja_id():
    v = os.environ.get("ADS_POLCHILE_HOJA", "").strip()
    if not v:
        raise SystemExit("Falta ADS_POLCHILE_HOJA (id de la hoja de Google con la inversión)")
    return v


def conectar():
    creds = service_account.Credentials.from_service_account_info(
        json.loads(os.environ["GOOGLE_CREDENTIALS_JSON"]),
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
    return build("sheets", "v4", credentials=creds, cache_discovery=False)


def pestanas(sheets, sid):
    meta = sheets.spreadsheets().get(spreadsheetId=sid, fields="sheets.properties.title").execute()
    return [s["properties"]["title"] for s in meta.get("sheets", [])]


def leer(sheets, sid, pestana):
    r = sheets.spreadsheets().values().get(
        spreadsheetId=sid, range=f"'{pestana}'!A:Z",
        valueRenderOption="UNFORMATTED_VALUE", dateTimeRenderOption="SERIAL_NUMBER").execute()
    return r.get("values", [])


def a_fecha(v):
    """Celda de fecha (número de serie de Sheets) o texto en los formatos habituales."""
    if v in (None, ""):
        return None
    if isinstance(v, (int, float)):
        return date(1899, 12, 30) + timedelta(days=int(v))
    s = str(v).strip()
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(s[:10], fmt).date()
        except ValueError:
            pass
    raise ValueError(f"fecha no reconocida: {v!r}")


def a_numero(v):
    if v in (None, ""):
        return 0
    if isinstance(v, (int, float)):
        return v
    s = str(v).strip().replace("$", "").replace(" ", "")
    if "," in s and "." in s:          # 1.234.567,89 -> 1234567.89
        s = s.replace(".", "").replace(",", ".")
    elif s.count(".") > 1:             # 1.234.567
        s = s.replace(".", "")
    elif "," in s:                     # 1234567,89 o 1,5
        s = s.replace(",", ".")
    return float(s)


# Nombres alternativos de columna: los que escribe el complemento "Google Ads" de Hojas de cálculo
# (informe por campaña segmentado por día, en español o inglés) y variantes a mano.
ALIAS = {
    "fecha": ("fecha", "dia", "day", "date", "fecha del dia"),
    "campana_id": ("campana_id", "campaign id", "id de campana", "id de la campana", "campaign_id"),
    "campana": ("campana", "campaign", "nombre de la campana", "campaign name", "nombre de campana"),
    "costo": ("costo", "cost", "coste", "gasto", "spend", "amount spent", "importe gastado"),
    "impresiones": ("impresiones", "impressions", "impr.", "impr"),
    "clics": ("clics", "clicks", "click", "clic"),
    "conversiones": ("conversiones", "conversions", "conv.", "conv", "resultados", "results"),
}


def normalizar(c):
    s = str(c).strip().lower().replace("ñ", "n")
    return s.translate(str.maketrans("áéíóú", "aeiou"))


def encabezado(valores):
    """Primera fila que trae fecha y costo (el complemento de Google Ads deja el título del informe arriba)."""
    for i, fila in enumerate(valores[:10]):
        enc = [normalizar(c) for c in fila]
        idx = {}
        for col, nombres in ALIAS.items():
            for j, c in enumerate(enc):
                if c in nombres:
                    idx[col] = j
                    break
        if "fecha" in idx and "costo" in idx:
            return i, idx
    return None, {}


def filas_de(valores, pestana):
    """Convierte la pestaña (lista de listas) en filas para el RPC. Avisa y salta las filas malas."""
    if not valores:
        return []
    inicio, idx = encabezado(valores)
    if inicio is None:
        raise SystemExit(f'La pestaña "{pestana}" no tiene una fila de encabezado con fecha y costo (primera fila: {valores[0]})')
    filas, malas = [], 0
    for n, fila in enumerate(valores[inicio + 1:], start=inicio + 2):
        if fila and normalizar(fila[0]).startswith(("total", "grand total")):
            continue                            # filas de totales del complemento o de la exportación de Google Ads
        celda = lambda c: fila[idx[c]] if c in idx and idx[c] < len(fila) else None
        try:
            f = a_fecha(celda("fecha"))
            if f is None:
                continue                        # fila vacía al final de la hoja
            filas.append({
                "fecha": f.isoformat(),
                "campana_id": str(celda("campana_id") or "").strip(),
                "campana": str(celda("campana") or "").strip() or None,
                "costo": a_numero(celda("costo")),
                "impresiones": int(a_numero(celda("impresiones"))),
                "clics": int(a_numero(celda("clics"))),
                "conversiones": a_numero(celda("conversiones")),
            })
        except (ValueError, TypeError) as e:
            malas += 1
            print(f'  aviso: pestaña "{pestana}" fila {n} ignorada ({e})')
    if malas:
        print(f'  {malas} filas ignoradas en "{pestana}"')
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
    sid = hoja_id()
    sheets = conectar()
    existentes = pestanas(sheets, sid)
    print(f"Hoja {sid}: pestañas {existentes}")
    resumen = []
    for plataforma in PLATAFORMAS:
        if plataforma not in existentes:
            if plataforma == "google":
                raise SystemExit('La hoja no tiene la pestaña "google": ¿ya corrió el script de Google Ads?')
            continue
        filas = filas_de(leer(sheets, sid, plataforma), plataforma)
        costo = sum(f["costo"] for f in filas)
        if not filas:
            print(f"{plataforma}: sin filas, no se toca Supabase")
            continue
        fechas = sorted(f["fecha"] for f in filas)
        print(f"{plataforma}: {len(filas)} filas, {fechas[0]} a {fechas[-1]}, costo {costo:,.0f}")
        if simular:
            continue
        for lote in lotes(filas):
            r = rpc("cargar_inversion_ads", {"p_plataforma": plataforma, "p_filas": lote})
            print(f"  cargado: {r}")
        resumen.append(f"{plataforma}: {len(filas)} filas ({fechas[0]} a {fechas[-1]}), costo {costo:,.0f}")
    if resumen and os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write("### Inversión Ads Polchile cargada\n\n" + "\n".join(f"- {r}" for r in resumen) + "\n")


def anotar_error(mensaje):
    if not os.environ.get("GITHUB_ACTIONS"):
        return
    print(f"::error::{mensaje}")
    resumen = os.environ.get("GITHUB_STEP_SUMMARY")
    if resumen:
        with open(resumen, "a", encoding="utf-8") as f:
            f.write(f"### Inversión Ads Polchile: falló\n\n```\n{mensaje}\n```\n")


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
