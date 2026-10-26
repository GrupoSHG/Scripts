"""Precios de referencia de materiales desde las órdenes de compra de Mercado Público (prueba).

Etapa de factibilidad: toma un día de órdenes de compra (ordenesdecompra.json?fecha=), filtra por
nombre las que parecen de materiales de construcción, pide el detalle de a lo más N (1 solicitud
cada una) y mide qué tan usables son los precios: ítems con unidad, "lotes" (cantidad 1 sin unidad
o en unidad global), moneda, y la mediana por producto y unidad.

Del detalle se guarda solo una lista blanca: el detalle trae nombre, cargo, teléfono y correo de los
contactos del comprador y del proveedor. Tampoco se guarda el nombre ni el RUT del proveedor, porque
puede ser una persona natural.
"""
import logging
import re
import statistics
from collections import Counter, defaultdict

from .filtro import normalizar

log = logging.getLogger("licitaciones.precios_oc")

RECURSO = "ordenesdecompra.json"
ESTADOS_EXCLUIDOS = {9}  # 9 = cancelada según la documentación; se confirma con el texto del detalle

INCLUIR = [
    "materiales de construccion", "material de construccion", "materiales construccion", "ferreteria",
    "cemento", "hormigon", "mortero", "fierro", "acero", "perfil", "plancha", "madera", "pino", "osb",
    "terciado", "yeso carton", "volcanita", "pintura", "esmalte", "tuberia", "caneria", "pvc", "ceramica",
    "porcelanato", "aislapol", "poliestireno", "panel", "zinc", "cubierta", "ladrillo", "arido", "arena",
    "grava", "ripio", "malla", "clavo", "tornillo", "perno", "cable electrico", "conductor electrico",
    "sanitario", "griferia", "impermeabiliz", "membrana", "aislante", "puerta", "ventana", "vidrio",
]
EXCLUIR = ["servicio", "arriendo", "alimentacion", "medicamento", "insumos medicos", "capacitacion",
           "pasaje", "combustible", "consultoria", "mantencion de vehiculo", "aseo"]
# El campo Unidad viene siempre vacío (verificado el 22/10/2026 en 258 ítems): la unidad y la presentación
# están en el texto de la especificación. PrecioNeto es por unidad y sin IVA (Total = Cantidad x PrecioNeto
# en 133 de 133 ítems con total).
_GLOBAL = re.compile(r"\b(global|gl|glb|lote|servicio|instalacion|mano de obra|ejecucion|reparacion|habilitacion)\b")
_UNIDAD = re.compile(r"\b(unidad(?:es)?|un|und|saco|bolsa|caja|rollo|m2|m3|ml|kg|kilo|litro|lt|galon|tineta|barra|"
                     r"plancha|metro|mts?|par|juego|set|tubo|paquete)\b")

_INCLUIR = [re.compile(r"\b" + re.escape(normalizar(p))) for p in INCLUIR]
_EXCLUIR = [re.compile(r"\b" + re.escape(normalizar(p))) for p in EXCLUIR]


def es_de_materiales(nombre):
    t = normalizar(nombre)
    return not any(rx.search(t) for rx in _EXCLUIR) and any(rx.search(t) for rx in _INCLUIR)


def sanitizar(oc):
    """Solo datos de la compra y del producto; nada de contactos ni del proveedor."""
    comp = oc.get("Comprador") or {}
    prov = oc.get("Proveedor") or {}
    fechas = oc.get("Fechas") or {}
    return {
        "codigo": oc.get("Codigo"), "nombre": oc.get("Nombre"), "codigo_estado": oc.get("CodigoEstado"),
        "estado": oc.get("Estado"), "codigo_licitacion": oc.get("CodigoLicitacion") or None, "tipo": oc.get("Tipo"),
        "moneda": oc.get("TipoMoneda"), "fecha_envio": fechas.get("FechaEnvio"),
        "organismo": comp.get("NombreOrganismo"), "region": comp.get("RegionUnidad"),
        "comuna": comp.get("ComunaUnidad"), "region_proveedor": prov.get("Region"),
        "items": [{"correlativo": i.get("Correlativo"), "codigo_categoria": i.get("CodigoCategoria"), "categoria": i.get("Categoria"),
                   "codigo_producto": i.get("CodigoProducto"), "producto": i.get("Producto"),
                   "especificacion_comprador": i.get("EspecificacionComprador"),
                   "especificacion_proveedor": i.get("EspecificacionProveedor"),
                   "cantidad": i.get("Cantidad"), "unidad": i.get("Unidad"), "moneda": i.get("Moneda"),
                   "precio_neto": i.get("PrecioNeto"), "total": i.get("Total")}
                  for i in (oc.get("Items") or {}).get("Listado") or []],
    }


def texto(item):
    return normalizar(f"{item.get('especificacion_comprador') or ''} {item.get('producto') or ''}")


def unidad_en_texto(item):
    m = _UNIDAD.search(texto(item))
    return m.group(1) if m else None


def calidad(item):
    """'sin_precio', 'otra_moneda', 'global' (servicio o lote), 'con_unidad' (dice la unidad en el texto)
    o 'sin_unidad' (precio por unidad, pero la unidad hay que deducirla)."""
    if not item.get("precio_neto") or not item.get("cantidad") or item["precio_neto"] <= 0 or item["cantidad"] <= 0:
        return "sin_precio"
    if (item.get("moneda") or "CLP").upper() != "CLP":
        return "otra_moneda"
    if _GLOBAL.search(texto(item)):
        return "global"
    return "con_unidad" if unidad_en_texto(item) else "sin_unidad"


def resumir(ocs):
    """Calidad de los ítems y, para los que dicen su unidad, mediana por producto y unidad. Es solo una
    vista preliminar: el nombre de producto de Mercado Público suele estar mal clasificado."""
    conteo = Counter()
    grupos = defaultdict(list)
    for oc in ocs:
        for it in oc["items"]:
            c = calidad(it)
            conteo[c] += 1
            if c == "con_unidad":
                grupos[(it["producto"], unidad_en_texto(it))].append(float(it["precio_neto"]))
    productos = sorted(
        ({"producto": k[0], "unidad": k[1], "n": len(v), "mediana": statistics.median(v),
          "minimo": min(v), "maximo": max(v)} for k, v in grupos.items()),
        key=lambda x: (-x["n"], x["producto"] or ""))
    return {"items": sum(conteo.values()), "calidad": dict(conteo), "productos": productos}


def probar(mp, fecha, max_detalles, omitir=frozenset()):
    """Listado del día, filtro por nombre y detalle de a lo más `max_detalles` órdenes (sin las de `omitir`)."""
    listado = mp._get(RECURSO, {"fecha": fecha}).get("Listado") or []
    candidatas = [o for o in listado if o.get("CodigoEstado") not in ESTADOS_EXCLUIDOS and o.get("Codigo") not in omitir
                  and es_de_materiales(o.get("Nombre"))]
    log.info("OC del %s: %d · pasan el filtro de materiales: %d · se piden %d", fecha, len(listado),
             len(candidatas), min(len(candidatas), max_detalles))
    ocs, estados = [], Counter()
    for o in candidatas[:max_detalles]:
        det = (mp._get(RECURSO, {"codigo": o["Codigo"]}).get("Listado") or [None])[0]
        if det:
            oc = sanitizar(det)
            estados[(oc["codigo_estado"], oc["estado"])] += 1
            ocs.append(oc)
    return {"fecha": fecha, "listado": len(listado), "candidatas": len(candidatas), "detalles": len(ocs),
            "estados_vistos": {f"{k[0]} {k[1]}": n for k, n in estados.items()},
            "solicitudes": mp.hechas, "respuestas_http": {str(k): v for k, v in mp.respuestas.items()},
            "resumen": resumir(ocs), "ocs": ocs}


# --- Supabase (m5.precios_oc_items) -----------------------------------------------

TABLA = "precios_oc_items"
COLUMNAS = ("oc", "correlativo", "fecha_envio", "region", "producto_mercado_publico", "codigo_categoria",
            "especificacion_comprador", "cantidad", "precio_presentacion", "es_material_construccion", "material",
            "especificacion", "presentacion", "contenido", "unidad_contenido", "contenido_base", "unidad_base",
            "precio_unidad_base", "confianza")


def fila_tabla(f, modelo):
    """Fila de m5.precios_oc_items. Las fechas de la API vienen en hora de Chile sin zona."""
    fila = {c: f.get(c) for c in COLUMNAS}
    if fila["fecha_envio"] and len(fila["fecha_envio"]) == 19:
        fila["fecha_envio"] = fila["fecha_envio"] + "-03:00"
    fila["modelo"] = modelo
    return fila


def ocs_guardadas(sb, dias=15):
    """Códigos de OC ya guardados en los últimos `dias` (para no volver a pedir su detalle)."""
    from datetime import datetime, timedelta, timezone
    desde = (datetime.now(timezone.utc) - timedelta(days=dias)).isoformat(timespec="seconds")
    r = sb._pedir("GET", params=[("select", "oc"), ("fecha_envio", f"gte.{desde}")],
                  headers={"Range-Unit": "items", "Range": "0-99999"})
    return {x["oc"] for x in r.json()}


def guardar(sb, filas, modelo):
    """Upsert por (oc, correlativo) de los ítems normalizados (también los que no son de construcción,
    para no volver a pedirlos; la vista de referencia los excluye)."""
    return sb.upsert([fila_tabla(f, modelo) for f in filas], conflicto="oc,correlativo")


def nocturno(ajustes, sb, mp=None, max_ocs=None):
    """Paso del comando diario: OC del día anterior, normalización y guardado. Devuelve un resumen
    solo con cifras (el log de Actions es público)."""
    from datetime import datetime, timedelta
    from . import normalizacion
    from .mp_api import MercadoPublico
    cfg = ajustes.get("precios_oc") or {}
    if not cfg.get("activo", False):
        return {"activo": False}
    mp = mp or MercadoPublico(ajustes)
    fecha = f"{datetime.now(mp.contador.zona) - timedelta(days=int(cfg.get('dias_atras', 1))):%d%m%Y}"
    omitir = ocs_guardadas(sb)
    maximo = int(cfg.get("max_ocs_noche", 300))
    from .descarga import dentro_de_ventana
    if not dentro_de_ventana(ajustes, datetime.now(mp.contador.zona)):
        # ChileCompra pide las descargas masivas de noche: de día, a lo más lo mismo que las licitaciones.
        maximo = min(maximo, int(ajustes["horario"]["max_detalles_fuera_de_horario"]))
    if max_ocs is not None:
        maximo = min(maximo, max_ocs)
    res = probar(mp, fecha, maximo, omitir=omitir)
    filas, resumen = normalizacion.ejecutar(ajustes, res["ocs"], tamano_lote=int(cfg.get("tamano_lote", 25)))
    subidas = guardar(sb, filas, ajustes["evaluacion"]["modelo"]) if filas else 0
    log.info("Precios OC %s: %d órdenes en el listado, %d de materiales, %d ya guardadas, %d detalles, "
             "%d ítems normalizados, %d con precio por unidad base, US$ %.4f, %d filas subidas", fecha,
             res["listado"], res["candidatas"], len(omitir), res["detalles"],
             resumen["normalizados"], resumen["con_precio_unidad_base"], resumen["costo_usd"], subidas)
    return {"fecha": fecha, "listado": res["listado"], "candidatas": res["candidatas"], "detalles": res["detalles"],
            "solicitudes": res["solicitudes"], **resumen, "subidas": subidas}
