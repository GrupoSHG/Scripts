"""Detalle de una licitación: lista blanca de campos y registro resumido.

El detalle de la API trae nombres, correos y teléfonos de funcionarios (NombreResponsablePago,
EmailResponsableContrato, Comprador.NombreUsuario, ...). Se guarda SOLO lo de la lista blanca,
así un campo nuevo con datos personales queda fuera por defecto. Los nombres de los campos
descartados se registran (sin sus valores) para ir revisando la lista.
"""
from datetime import datetime

URL_FICHA = "https://www.mercadopublico.cl/Procurement/Modules/RFB/DetailsAcquisition.aspx?idlicitacion={}"

CAMPOS = {
    "CodigoExterno", "Nombre", "CodigoEstado", "Estado", "Descripcion", "FechaCierre", "Tipo", "CodigoTipo",
    "TipoConvocatoria", "Moneda", "MontoEstimado", "VisibilidadMonto", "Modalidad", "TipoPago", "Etapas",
    "EstadoEtapas", "TomaRazon", "EstadoPublicidadOfertas", "JustificacionPublicidad", "Contrato", "Obras",
    "CantidadReclamos", "DiasCierreLicitacion", "Informada", "Estimacion", "FuenteFinanciamiento",
    "VisibilidadMonto", "TiempoDuracionContrato", "UnidadTiempoDuracionContrato", "TipoDuracionContrato",
    "UnidadTiempoContratoLicitacion", "JustificacionMontoEstimado", "ObservacionContract", "ExtensionPlazo",
    "EsBaseTipo", "EsRenovable", "ValorTiempoRenovacion", "PeriodoTiempoRenovacion", "ProhibicionContratacion",
    "SubContratacion", "UnidadTiempoEvaluacion", "DireccionVisita", "DireccionEntrega", "Fechas",
    "Tiempo", "UnidadTiempo", "CodigoBIP",
    # Adjudicación de la licitación (tipo, fecha, número de oferentes, acta). La de cada ítem
    # (Items.Listado[].Adjudicacion) trae RUT y nombre del proveedor y queda fuera.
    "Adjudicacion",
}
CAMPOS_COMPRADOR = {
    "CodigoOrganismo", "NombreOrganismo", "RutUnidad", "CodigoUnidad", "NombreUnidad", "DireccionUnidad",
    "ComunaUnidad", "RegionUnidad",
}
CAMPOS_ITEM = {
    "Correlativo", "CodigoProducto", "CodigoCategoria", "Categoria", "NombreProducto", "Descripcion",
    "UnidadMedida", "Cantidad",
}


def sanitizar(det):
    """(detalle solo con campos permitidos, nombres de campos descartados)."""
    limpio = {k: v for k, v in det.items() if k in CAMPOS}
    descartados = sorted(k for k in det if k not in CAMPOS and k not in ("Comprador", "Items"))
    comprador = det.get("Comprador") or {}
    limpio["Comprador"] = {k: v for k, v in comprador.items() if k in CAMPOS_COMPRADOR}
    descartados += sorted(f"Comprador.{k}" for k in comprador if k not in CAMPOS_COMPRADOR)
    items = (det.get("Items") or {}).get("Listado") or []
    limpio["Items"] = {"Cantidad": len(items),
                       "Listado": [{k: v for k, v in i.items() if k in CAMPOS_ITEM} for i in items]}
    descartados += sorted({f"Items.Listado[].{k}" for i in items for k in i if k not in CAMPOS_ITEM})
    return limpio, descartados


def fecha_chile(valor, zona):
    """Las fechas de la API vienen en hora local de Chile sin zona; 1900-01-01/02 = vacío."""
    if not valor or str(valor).startswith("1900"):
        return None
    try:
        return datetime.fromisoformat(str(valor)[:19]).replace(tzinfo=zona).isoformat()
    except ValueError:
        return None


def registro(det_limpio, coincidencias, prioritario, zona):
    from .filtro import monto_publicado_clp
    comp = det_limpio.get("Comprador") or {}
    fechas = det_limpio.get("Fechas") or {}
    codigo = det_limpio["CodigoExterno"]
    return {
        "codigo_externo": codigo,
        "nombre": (det_limpio.get("Nombre") or "").strip(),
        "organismo": (comp.get("NombreOrganismo") or "").strip() or None,
        "region": (comp.get("RegionUnidad") or "").strip() or None,
        "comuna": (comp.get("ComunaUnidad") or "").strip() or None,
        "codigo_estado": det_limpio.get("CodigoEstado"),
        "estado": det_limpio.get("Estado"),
        "tipo": det_limpio.get("Tipo"),
        "fecha_publicacion": fecha_chile(fechas.get("FechaPublicacion"), zona),
        "fecha_cierre": fecha_chile(fechas.get("FechaCierre") or det_limpio.get("FechaCierre"), zona),
        "monto_estimado_clp": monto_publicado_clp(det_limpio),
        "url_ficha": URL_FICHA.format(codigo),
        "coincidencias": coincidencias,
        "organismo_prioritario": prioritario,
        "detalle": det_limpio,
    }


def estructura(valor, prefijo="", nivel=0, max_nivel=3):
    """Líneas 'ruta: tipo' del JSON, para ver qué entrega la API sin imprimir valores."""
    lineas = []
    if isinstance(valor, dict):
        for k, v in valor.items():
            ruta = f"{prefijo}.{k}" if prefijo else k
            lineas.append(f"{'  ' * nivel}{ruta}: {_tipo(v)}")
            if nivel < max_nivel and isinstance(v, (dict, list)):
                lineas += estructura(v, ruta, nivel + 1, max_nivel)
    elif isinstance(valor, list) and valor:
        lineas += estructura(valor[0], prefijo + "[]", nivel, max_nivel)
    return lineas


def _tipo(v):
    if isinstance(v, dict):
        return f"objeto ({len(v)} campos)"
    if isinstance(v, list):
        return f"lista ({len(v)})"
    if v in (None, "", 0):
        return f"{type(v).__name__} vacío"
    return type(v).__name__
