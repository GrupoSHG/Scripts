"""Obras adjudicadas en Mercado Público -> Supabase polchile_crm.adjudicadas_mp (oportunidades para Polchile).

Las constructoras que acaban de ganar una obra pública tienen que comprar materiales: son posibles clientes de
paneles, cubiertas y planchas. La pestaña "Adjudicadas MP" del Cockpit Comercial
(GrupoSHG_Systems/cockpit-comercial-web/tabs/tab-adjudicadas.js) muestra los últimos 14 días.

Cada noche (lo dispara Supabase, workflow adjudicadas-mp-polchile.yml):
1. Listado de adjudicadas de hoy y de los 13 días anteriores (`fecha=ddmmaaaa&estado=adjudicada`, una solicitud
   por día; el 27/10/2026 fueron 363). Solo trae código, nombre, estado y cierre.
2. Filtro por nombre (obras, sin diseños, consultorías ni compras de insumos) y se omiten las ya guardadas.
3. Detalle de las que pasan, de la más reciente a la más antigua y con tope por corrida: rubro UNSPSC de los
   ítems y quién ganó cada ítem y por cuánto. Se guardan también las que el rubro descarta (es_obra = false)
   para no volver a pedirlas; la pestaña no las muestra.
4. Upsert por codigo_externo.

interes = 'alto' si el nombre menciona algo que Polchile vende o donde se usa (techumbre, cubierta, panel,
galpón, cámara frigorífica, modular...); si no, 'obra'.

Del detalle se guarda solo una lista blanca (trae nombres, correos y teléfonos de funcionarios). El RUT y la
razón social del adjudicado se guardan solo si es empresa (RUT desde 50.000.000): una persona natural queda como
"Persona natural", con su monto. El repo es público: el log solo lleva cifras y nunca la URL (lleva el ticket).

Mercado Público (ver M5_Systems/licitaciones-m5/NOTAS_API.md): 10.000 solicitudes diarias por ticket, compartido
con el job de licitaciones de M5; descargas masivas solo de 22:00 a 07:00, fuera de esa ventana se piden a lo
más 50 detalles salvo --forzar. Ticket inválido = HTTP 203; 403 corta; 429/5xx se reintentan.

Variables de entorno: MP_TICKET, SUPABASE_SERVICE_KEY. Para probar en local, en un .env junto a este archivo:
  python Polchile_Systems/sync_adjudicadas_mp.py --dias 2 --max 20 --simular
SQL (a mano): Polchile_Systems/adjudicadas_mp.sql.
"""
import argparse
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

_ENV = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(_ENV):
    for _l in open(_ENV, encoding="utf-8"):
        _k, _, _v = _l.strip().partition("=")
        if _k and not _k.startswith("#"):
            os.environ.setdefault(_k.strip(), _v.strip().strip('"'))

SUPABASE_URL = "https://ffxopvzxyeacpbtxuagu.supabase.co"
ESQUEMA, TABLA = "polchile_crm", "adjudicadas_mp"
API = "https://api.mercadopublico.cl/servicios/v1/publico/licitaciones.json"
URL_FICHA = "https://www.mercadopublico.cl/Procurement/Modules/RFB/DetailsAcquisition.aspx?idlicitacion={}"
ZONA = ZoneInfo("America/Santiago")
ADJUDICADA = 8
PAUSA_S = 3            # con 1,5 s la API devolvió 429 en 12 de 33 solicitudes (NOTAS_API.md)
REINTENTOS = 4
VENTANA = (22, 7)      # horas de Chile en que ChileCompra acepta descargas masivas
MAX_FUERA_VENTANA = 50
LOTE = 200

# Solo palabras que por sí solas indican una obra: "reparación", "mejoramiento", "escuela" o "bodega" dejaban
# pasar ecógrafos, insumos dentales y equipamiento (101 de 596 en la prueba del 28/10/2026; con esta lista, 63 de 714).
INCLUIR = [
    "obra", "construccion", "edificacion", "galpon", "techumbre", "techo", "techado", "cubierta", "cobertizo",
    "tinglado", "ampliacion", "habilitacion", "remodelacion", "normalizacion", "conservacion", "panel",
    "revestimiento", "fachada", "camara frigorifica", "camaras frigorificas", "frigorifico", "camara de frio",
    "modular", "prefabricad", "cierre perimetral", "estructura metalica", "aislacion", "aislamiento termico",
    "sede social", "multicancha", "infraestructura", "radier", "hangar",
]
EXCLUIR = [
    "diseno", "consultoria", "asesoria", "inspeccion tecnica", "estudio", "auditoria", "capacitacion",
    "arriendo", "alimentacion", "medicamento", "insumos", "equipamiento", "vestuario", "vehiculo", "combustible",
    "software", "licencia", "seguro", "aseo", "vigilancia", "transporte de pasajeros", "banqueteria",
]
# Lo que Polchile vende o donde se usa directamente: marca la obra como interés alto.
INTERES_ALTO = [
    "galpon", "techumbre", "techo", "techado", "cubierta", "cobertizo", "tinglado", "panel", "revestimiento",
    "fachada", "camara frigorifica", "camaras frigorificas", "frigorifico", "camara de frio", "modular",
    "prefabricad", "aislacion", "aislamiento termico", "hangar", "bodega", "sede social", "multicancha",
]
# UNSPSC de construcción: 72 servicios de edificación, construcción y mantenimiento; 30 componentes y materiales de
# estructuras y edificación; 95 terrenos, edificios y estructuras.
PREFIJOS_RUBRO = ("72", "30", "95")
RUT_EMPRESA_DESDE = 50_000_000


def normalizar(texto):
    """Minúsculas, sin tildes y sin puntuación: "Galpón" -> "galpon"."""
    texto = unicodedata.normalize("NFKD", str(texto or "").lower())
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9ñ]+", " ", texto)).strip()


def _patrones(lista):
    # Desde el inicio de palabra: "techo" también encuentra "techos".
    return [(p, re.compile(r"\b" + re.escape(normalizar(p)))) for p in lista]


_INCLUIR, _EXCLUIR, _ALTO = _patrones(INCLUIR), _patrones(EXCLUIR), _patrones(INTERES_ALTO)


def por_nombre(nombre):
    """Palabras clave que calzan con el nombre del listado ([] si no pasa)."""
    t = normalizar(nombre)
    if any(rx.search(t) for _, rx in _EXCLUIR):
        return []
    return [p for p, rx in _INCLUIR if rx.search(t)]


def interes(nombre):
    t = normalizar(nombre)
    return "alto" if any(rx.search(t) for _, rx in _ALTO) else "obra"


def es_empresa(rut):
    cuerpo = "".join(c for c in str(rut or "").split("-")[0] if c.isdigit())
    return bool(cuerpo) and int(cuerpo) >= RUT_EMPRESA_DESDE


def fecha_chile(valor):
    """Las fechas de la API vienen en hora local de Chile sin zona; 1900-01-01/02 = vacío."""
    if not valor or str(valor).startswith("1900"):
        return None
    try:
        return datetime.fromisoformat(str(valor)[:19]).replace(tzinfo=ZONA).isoformat()
    except ValueError:
        return None


def adjudicatarios(items):
    """Ganadores agrupados por RUT, con el monto adjudicado (cantidad x monto unitario) y los ítems."""
    grupos = {}
    for it in items:
        adj = it.get("Adjudicacion") or {}
        rut = (adj.get("RutProveedor") or "").strip()
        if not rut:
            continue
        empresa = es_empresa(rut)
        g = grupos.setdefault(rut, {"rut": rut if empresa else None,
                                    "nombre": (adj.get("NombreProveedor") or "").strip() if empresa else "Persona natural",
                                    "monto": 0.0, "items": 0})
        g["monto"] += float(adj.get("Cantidad") or 0) * float(adj.get("MontoUnitario") or 0)
        g["items"] += 1
    return [{**g, "monto": round(g["monto"], 2)} for g in sorted(grupos.values(), key=lambda g: -g["monto"])]


def fila(det, claves, ahora):
    """Fila de polchile_crm.adjudicadas_mp desde el detalle de la API (solo campos permitidos)."""
    comp = det.get("Comprador") or {}
    fechas = det.get("Fechas") or {}
    adj = det.get("Adjudicacion") or {}
    items = (det.get("Items") or {}).get("Listado") or []
    categorias = sorted({str(i.get("CodigoCategoria")) for i in items if i.get("CodigoCategoria")})
    ganadores = adjudicatarios(items)
    principal = ganadores[0] if ganadores else {}
    codigo, nombre = det["CodigoExterno"], (det.get("Nombre") or "").strip()
    return {
        "codigo_externo": codigo,
        "nombre": nombre,
        "organismo": (comp.get("NombreOrganismo") or "").strip() or None,
        "region": (comp.get("RegionUnidad") or "").strip() or None,
        "comuna": (comp.get("ComunaUnidad") or "").strip() or None,
        "tipo": det.get("Tipo"),
        "moneda": det.get("Moneda"),
        "monto_estimado": det.get("MontoEstimado") if det.get("VisibilidadMonto") == 1 else None,
        "monto_adjudicado": round(sum(g["monto"] for g in ganadores), 2) if ganadores else None,
        "fecha_adjudicacion": fecha_chile(fechas.get("FechaAdjudicacion") or adj.get("Fecha")),
        "numero_oferentes": adj.get("NumeroOferentes"),
        "url_acta": adj.get("UrlActa"),
        "url_ficha": URL_FICHA.format(codigo),
        "adjudicatarios": ganadores,
        "proveedor_principal": principal.get("nombre"),
        "rut_principal": principal.get("rut"),
        "categorias": categorias,
        "palabras_clave": claves,
        "interes": interes(nombre),
        # El rubro de los ítems manda: el nombre solo preselecciona ("mejoramiento de circuito de incendio").
        "es_obra": any(c.startswith(PREFIJOS_RUBRO) for c in categorias),
        "actualizado": ahora,
    }


# --- Mercado Público -------------------------------------------------------------

class ErrorMP(Exception):
    pass


class MercadoPublico:
    def __init__(self, ticket):
        self.ticket = ticket
        self.solicitudes = 0
        self.respuestas = {}

    def _sumar(self, clave):
        self.respuestas[str(clave)] = self.respuestas.get(str(clave), 0) + 1

    def get(self, **params):
        url = API + "?" + urllib.parse.urlencode({**params, "ticket": self.ticket})
        for intento in range(REINTENTOS + 1):
            self.solicitudes += 1
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Polchile-Adjudicadas/1.0"})
                with urllib.request.urlopen(req, timeout=60) as r:
                    codigo, cuerpo = r.status, r.read()
            except urllib.error.HTTPError as e:
                codigo, cuerpo = e.code, b""
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                codigo, cuerpo = type(e).__name__, b""
            self._sumar(codigo)
            if codigo == 200:
                try:
                    datos = json.loads(cuerpo.decode("utf-8-sig"))
                except ValueError:
                    datos = {}
                if "Listado" in datos:
                    time.sleep(PAUSA_S)
                    return datos["Listado"] or []
                if datos.get("Codigo") != 10500:   # 10500 = peticiones simultáneas: se reintenta
                    raise ErrorMP(f"la API respondió Codigo {datos.get('Codigo')} para {sorted(params)}")
            elif codigo in (203, 401):
                raise ErrorMP(f"HTTP {codigo}: ticket rechazado, revisar el secret MP_TICKET")
            elif codigo == 403:
                raise ErrorMP("HTTP 403: la API rechazó la solicitud (posible bloqueo de IP); no se reintenta")
            elif isinstance(codigo, int) and codigo != 429 and codigo < 500:
                raise ErrorMP(f"HTTP {codigo} para {sorted(params)}")
            if intento < REINTENTOS:
                time.sleep(min(60, 2 * 2 ** intento))
        raise ErrorMP(f"{codigo} tras {REINTENTOS + 1} intentos para {sorted(params)}")


# --- Supabase ------------------------------------------------------------------

def supabase(metodo, params, cuerpo=None, extra=None):
    key = os.environ["SUPABASE_SERVICE_KEY"]
    url = f"{SUPABASE_URL}/rest/v1/{TABLA}?" + urllib.parse.urlencode(params)
    h = {"apikey": key, "Authorization": "Bearer " + key, "Accept-Profile": ESQUEMA, "Content-Profile": ESQUEMA,
         "Content-Type": "application/json", **(extra or {})}
    data = json.dumps(cuerpo).encode() if cuerpo is not None else None
    for intento in (1, 2):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, data=data, headers=h, method=metodo), timeout=60) as r:
                texto = r.read().decode() or "null"
                return json.loads(texto)
        except urllib.error.HTTPError as e:
            raise SystemExit(f"Supabase {metodo} HTTP {e.code}: {e.read().decode()[:300]}"
                             + (" (¿falta aplicar Polchile_Systems/adjudicadas_mp.sql?)" if e.code == 404 else ""))
        except urllib.error.URLError:
            if intento == 2:
                raise


def guardadas(dias=30):
    """Códigos ya guardados en los últimos `dias` (para no volver a pedir su detalle)."""
    desde = (datetime.now(timezone.utc) - timedelta(days=dias)).isoformat(timespec="seconds")
    codigos, inicio = set(), 0
    while True:
        datos = supabase("GET", {"select": "codigo_externo", "cargado_en": f"gte.{desde}", "order": "codigo_externo",
                                 "offset": inicio, "limit": 1000})
        codigos.update(x["codigo_externo"] for x in datos)
        if len(datos) < 1000:
            return codigos
        inicio += 1000


def subir(filas):
    for i in range(0, len(filas), LOTE):
        supabase("POST", {"on_conflict": "codigo_externo"}, filas[i:i + LOTE],
                 {"Prefer": "resolution=merge-duplicates,return=minimal"})
    return len(filas)


# --- Corrida -------------------------------------------------------------------

def dentro_de_ventana(ahora):
    return ahora.hour >= VENTANA[0] or ahora.hour < VENTANA[1]


def main(argv=None):
    ap = argparse.ArgumentParser(description="Obras adjudicadas en Mercado Público -> polchile_crm.adjudicadas_mp")
    ap.add_argument("--dias", type=int, default=14, help="días hacia atrás, hoy incluido (14)")
    ap.add_argument("--max", type=int, default=200, help="detalles por corrida (200; 50 fuera de 22:00-07:00)")
    ap.add_argument("--forzar", action="store_true", help="permitir más de 50 detalles fuera de 22:00-07:00")
    ap.add_argument("--simular", action="store_true", help="no lee ni escribe Supabase; muestra las filas")
    a = ap.parse_args(argv)
    ticket = os.environ.get("MP_TICKET", "").strip()
    if not ticket:
        raise SystemExit("Falta MP_TICKET")
    ahora = datetime.now(ZONA)
    maximo = a.max if a.forzar or dentro_de_ventana(ahora) else min(a.max, MAX_FUERA_VENTANA)
    mp = MercadoPublico(ticket)
    try:
        omitir = set() if a.simular else guardadas()
        listado, candidatas, vistas = 0, [], set()
        for n in range(a.dias):  # de hoy hacia atrás: con el tope, primero lo más reciente
            for lic in mp.get(fecha=f"{ahora - timedelta(days=n):%d%m%Y}", estado="adjudicada"):
                listado += 1
                cod = lic.get("CodigoExterno")
                if lic.get("CodigoEstado") != ADJUDICADA or not cod or cod in omitir or cod in vistas:
                    continue
                vistas.add(cod)
                claves = por_nombre(lic.get("Nombre"))
                if claves:
                    candidatas.append((cod, claves))
        filas, errores, marca = [], 0, ahora.isoformat(timespec="seconds")
        for cod, claves in candidatas[:maximo]:
            try:
                det = (mp.get(codigo=cod) or [None])[0]
            except ErrorMP as e:
                if "403" in str(e) or "ticket" in str(e):
                    raise
                errores += 1
                continue
            if det and det.get("CodigoEstado") == ADJUDICADA:
                filas.append(fila(det, claves, marca))
    except ErrorMP as e:
        raise SystemExit(f"Mercado Público: {e}")
    subidas = 0 if a.simular else (subir(filas) if filas else 0)
    resumen = {"dias": a.dias, "listado": listado, "ya_guardadas": len(omitir), "pasan_nombre": len(candidatas),
               "detalles": len(filas), "obras": sum(f["es_obra"] for f in filas),
               "interes_alto": sum(f["es_obra"] and f["interes"] == "alto" for f in filas), "errores_detalle": errores,
               "pendientes": max(0, len(candidatas) - maximo), "subidas": subidas, "solicitudes": mp.solicitudes,
               "respuestas_http": mp.respuestas}
    print(json.dumps(resumen, ensure_ascii=False))
    if a.simular:  # solo en local: muestra lo que se subiría (en Actions el log es público)
        for f in filas:
            print(("ALTO" if f["es_obra"] and f["interes"] == "alto" else "obra" if f["es_obra"] else "----"),
                  f["codigo_externo"], f["nombre"][:60], "|", f["proveedor_principal"], f["moneda"], f["monto_adjudicado"])
    if errores > 10:
        raise SystemExit(f"{errores} detalles fallidos")


if __name__ == "__main__":
    sys.exit(main())
