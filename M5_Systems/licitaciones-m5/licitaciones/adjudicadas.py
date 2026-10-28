"""Licitaciones de obras adjudicadas en los últimos días (pestaña "Adjudicadas MP" del Cockpit Comercial).

Cada noche, dentro del comando diario (o con `python -m licitaciones adjudicadas`):

1. Listado de adjudicadas de hoy y de los `dias` anteriores (`fecha=ddmmaaaa&estado=adjudicada`, una
   solicitud por día; el 27/10/2026 fueron 363). Solo trae código, nombre, estado y cierre.
2. Filtro por nombre (obras y construcción, sin diseños ni consultorías) y se omiten las ya guardadas.
3. Detalle de las que pasan, de la más reciente a la más antigua y con tope por noche: rubro UNSPSC de
   los ítems, quién ganó cada ítem y por cuánto. Se guardan también las que el detalle descarta
   (`es_obra = false`) para no volver a pedirlas; la pestaña no las muestra.
4. Upsert en m5.licitaciones_adjudicadas con el rol licitaciones_m5.

Del detalle se guarda solo una lista blanca. El RUT y la razón social del adjudicado se guardan solo si
es una empresa (RUT desde 50.000.000): una persona natural queda como "Persona natural", con su monto.
"""
import logging
from datetime import datetime, timedelta

from .detalle import URL_FICHA, fecha_chile
from .filtro import _patrones, normalizar

log = logging.getLogger("licitaciones.adjudicadas")

TABLA = "licitaciones_adjudicadas"
ESTADO_ADJUDICADA = 8

# Solo palabras que por sí solas indican una obra: "reparación", "mejoramiento", "escuela" o "bodega" dejaban
# pasar ecógrafos, insumos dentales y equipamiento (101 de 596 en la prueba del 28/10/2026).
INCLUIR = [
    "obra", "construccion", "edificacion", "galpon", "techumbre", "techo", "cubierta", "ampliacion",
    "habilitacion", "remodelacion", "normalizacion", "conservacion", "panel", "camara frigorifica",
    "camaras frigorificas", "frigorifico", "modular", "prefabricad", "cierre perimetral", "estructura metalica",
    "aislacion", "aislamiento termico", "sede social", "multicancha", "infraestructura", "radier",
]
EXCLUIR = [
    "diseno", "consultoria", "asesoria", "inspeccion tecnica", "estudio", "auditoria", "capacitacion",
    "arriendo", "alimentacion", "medicamento", "insumos", "equipamiento", "vestuario", "vehiculo", "combustible",
    "software", "licencia", "seguro", "aseo", "vigilancia", "transporte de pasajeros", "banqueteria",
]
# UNSPSC de construcción: 72 servicios de edificación, construcción y mantenimiento; 30 componentes y
# materiales de estructuras y edificación; 95 terrenos, edificios y estructuras.
PREFIJOS_RUBRO = ("72", "30", "95")
RUT_EMPRESA_DESDE = 50_000_000

_INCLUIR = _patrones(INCLUIR)
_EXCLUIR = _patrones(EXCLUIR)


def por_nombre(nombre):
    """Palabras clave que calzan con el nombre del listado ([] si no pasa)."""
    t = normalizar(nombre)
    if any(rx.search(t) for _, rx in _EXCLUIR):
        return []
    return [p for p, rx in _INCLUIR if rx.search(t)]


def es_empresa(rut):
    cuerpo = "".join(c for c in str(rut or "").split("-")[0] if c.isdigit())
    return bool(cuerpo) and int(cuerpo) >= RUT_EMPRESA_DESDE


def adjudicatarios(items):
    """Ganadores agrupados por RUT, con el monto adjudicado (cantidad x monto unitario) y los ítems."""
    grupos = {}
    for it in items:
        adj = it.get("Adjudicacion") or {}
        rut = (adj.get("RutProveedor") or "").strip()
        if not rut:
            continue
        monto = float(adj.get("Cantidad") or 0) * float(adj.get("MontoUnitario") or 0)
        empresa = es_empresa(rut)
        g = grupos.setdefault(rut, {"rut": rut if empresa else None,
                                    "nombre": (adj.get("NombreProveedor") or "").strip() if empresa else "Persona natural",
                                    "monto": 0.0, "items": 0})
        g["monto"] += monto
        g["items"] += 1
    return sorted(grupos.values(), key=lambda g: -g["monto"])


def fila(det, claves, zona, ahora):
    """Fila de m5.licitaciones_adjudicadas desde el detalle de la API (solo campos permitidos)."""
    comp = det.get("Comprador") or {}
    fechas = det.get("Fechas") or {}
    adj = det.get("Adjudicacion") or {}
    items = (det.get("Items") or {}).get("Listado") or []
    categorias = sorted({str(i.get("CodigoCategoria")) for i in items if i.get("CodigoCategoria")})
    rubro = any(c.startswith(PREFIJOS_RUBRO) for c in categorias)
    ganadores = adjudicatarios(items)
    principal = ganadores[0] if ganadores else {}
    codigo = det["CodigoExterno"]
    return {
        "codigo_externo": codigo,
        "nombre": (det.get("Nombre") or "").strip(),
        "organismo": (comp.get("NombreOrganismo") or "").strip() or None,
        "region": (comp.get("RegionUnidad") or "").strip() or None,
        "comuna": (comp.get("ComunaUnidad") or "").strip() or None,
        "tipo": det.get("Tipo"),
        "moneda": det.get("Moneda"),
        "monto_estimado": det.get("MontoEstimado") if det.get("VisibilidadMonto") == 1 else None,
        "monto_adjudicado": round(sum(g["monto"] for g in ganadores), 2) if ganadores else None,
        "fecha_adjudicacion": fecha_chile(fechas.get("FechaAdjudicacion") or adj.get("Fecha"), zona),
        "numero_oferentes": adj.get("NumeroOferentes"),
        "url_acta": adj.get("UrlActa"),
        "url_ficha": URL_FICHA.format(codigo),
        "adjudicatarios": [{**g, "monto": round(g["monto"], 2)} for g in ganadores],
        "proveedor_principal": principal.get("nombre"),
        "rut_principal": principal.get("rut"),
        "categorias": categorias,
        "palabras_clave": claves,
        # El rubro de los ítems manda: el nombre solo preselecciona ("mejoramiento de circuito de incendio").
        "es_obra": rubro,
        "actualizado": ahora,
    }


def guardadas(sb, dias=30):
    """Códigos ya guardados en los últimos `dias` (para no volver a pedir su detalle)."""
    from datetime import timezone
    desde = (datetime.now(timezone.utc) - timedelta(days=dias)).isoformat(timespec="seconds")
    codigos, inicio = set(), 0
    while True:
        r = sb._pedir("GET", params=[("select", "codigo_externo"), ("cargado_en", f"gte.{desde}"),
                                     ("order", "codigo_externo")],
                      headers={"Range-Unit": "items", "Range": f"{inicio}-{inicio + 999}"})
        datos = r.json()
        codigos.update(x["codigo_externo"] for x in datos)
        if len(datos) < 1000:
            return codigos
        inicio += 1000


def ejecutar(ajustes, sb, mp=None, dias=None, max_detalles=None, forzar=False):
    """Listados de los últimos días, filtro, detalle y guardado. Devuelve un resumen solo con cifras
    (el log de Actions es público)."""
    from .descarga import dentro_de_ventana
    from .errores import ErrorAPI
    from .mp_api import MercadoPublico
    cfg = ajustes.get("adjudicadas") or {}
    if not cfg.get("activo", False):
        return {"activo": False}
    mp = mp or MercadoPublico(ajustes)
    zona = mp.contador.zona
    ahora = datetime.now(zona)
    dias = int(dias if dias is not None else cfg.get("dias", 14))
    maximo = int(max_detalles if max_detalles is not None else cfg.get("max_detalles_noche", 200))
    if not forzar and not dentro_de_ventana(ajustes, ahora):
        # ChileCompra pide las descargas masivas de noche.
        maximo = min(maximo, int(ajustes["horario"]["max_detalles_fuera_de_horario"]))

    omitir = guardadas(sb)
    listado, candidatas, vistas = 0, [], set()
    for n in range(dias):  # de hoy hacia atrás: con el tope, primero lo más reciente
        for lic in mp.listado(fecha=f"{ahora - timedelta(days=n):%d%m%Y}", estado="adjudicada"):
            listado += 1
            cod = lic.get("CodigoExterno")
            if lic.get("CodigoEstado") != ESTADO_ADJUDICADA or not cod or cod in omitir or cod in vistas:
                continue
            vistas.add(cod)
            claves = por_nombre(lic.get("Nombre"))
            if claves:
                candidatas.append((cod, claves))

    filas, errores = [], 0
    marca = ahora.isoformat(timespec="seconds")
    for cod, claves in candidatas[:maximo]:
        try:
            det = mp.detalle(cod)
        except ErrorAPI as e:
            if e.fatal:
                raise
            errores += 1
            continue
        if det and det.get("CodigoEstado") == ESTADO_ADJUDICADA:
            filas.append(fila(det, claves, zona, marca))
    subidas = sb.upsert(filas) if filas else 0
    resumen = {"dias": dias, "listado": listado, "ya_guardadas": len(omitir), "pasan_nombre": len(candidatas),
               "detalles": len(filas), "errores_detalle": errores, "obras": sum(f["es_obra"] for f in filas),
               "pendientes": max(0, len(candidatas) - maximo), "subidas": subidas, "solicitudes": mp.hechas}
    log.info("Adjudicadas (%d días): %d en los listados, %d ya guardadas, %d pasan el nombre, %d detalles "
             "(%d obras), %d errores, %d quedan para otra noche", dias, listado, len(omitir), len(candidatas),
             len(filas), resumen["obras"], errores, resumen["pendientes"])
    return resumen
