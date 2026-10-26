"""Normalización con Claude de los ítems de órdenes de compra, para precios de referencia.

El nombre de producto de Mercado Público suele estar mal clasificado y la unidad viene solo en el texto
(ver NOTAS_API.md). Claude lee cada ítem y devuelve, con esquema fijo: si es material de construcción,
el material genérico, la especificación, la presentación, cuánto contenido trae y en qué unidad base.
Claude NUNCA entrega precios: el código calcula el precio por presentación (PrecioNeto) y por unidad
base (PrecioNeto / contenido). Si algo no se puede saber, va null.

Usa el mismo cliente, tope de gasto diario y modelo que la evaluación de licitaciones (evaluacion.py).
"""
import json
import logging
import statistics
from collections import defaultdict
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .config import enmascarar
from .errores import ErrorClaude

log = logging.getLogger("licitaciones.normalizacion")

UNIDADES_BASE = ["unidad", "kg", "m", "m2", "m3", "litro"]
# Unidades tal como aparecen en el texto -> (unidad base, factor). La conversión la hace el código,
# no Claude: en la prueba del 26/10/2026 el modelo tomó "300 ML" como 300 litros y "370 GR" como 370 kg.
CONVERSION = {"unidad": ("unidad", 1), "kg": ("kg", 1), "g": ("kg", 0.001), "ton": ("kg", 1000),
              "m": ("m", 1), "cm": ("m", 0.01), "mm": ("m", 0.001), "m2": ("m2", 1), "m3": ("m3", 1),
              "litro": ("litro", 1), "ml": ("litro", 0.001), "cc": ("litro", 0.001), "galon": ("litro", 3.785)}
_NULO = {"type": "null"}
_TEXTO = {"anyOf": [{"type": "string"}, _NULO]}

ESQUEMA = {
    "type": "object",
    "properties": {"items": {"type": "array", "items": {
        "type": "object",
        "properties": {
            "indice": {"type": "integer"},
            "es_material_construccion": {"type": "boolean"},
            "material": _TEXTO,
            "especificacion": _TEXTO,
            "presentacion": _TEXTO,
            "contenido": {"anyOf": [{"type": "number"}, _NULO]},
            "unidad_contenido": {"anyOf": [{"type": "string", "enum": list(CONVERSION)}, _NULO]},
            "confianza": {"type": "string", "enum": ["alta", "media", "baja"]},
        },
        "required": ["indice", "es_material_construccion", "material", "especificacion", "presentacion",
                     "contenido", "unidad_contenido", "confianza"],
        "additionalProperties": False,
    }}},
    "required": ["items"],
    "additionalProperties": False,
}


class Normalizado(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    indice: int = Field(ge=0)
    es_material_construccion: bool
    material: Optional[str] = Field(max_length=80)
    especificacion: Optional[str] = Field(max_length=120)
    presentacion: Optional[str] = Field(max_length=40)
    contenido: Optional[float] = Field(gt=0)
    unidad_contenido: Optional[Literal["unidad", "kg", "g", "ton", "m", "cm", "mm", "m2", "m3", "litro", "ml", "cc",
                                       "galon"]]

    def base(self):
        """(contenido en unidad base, unidad base) o (None, None)."""
        if not self.contenido or not self.unidad_contenido:
            return None, None
        unidad, factor = CONVERSION[self.unidad_contenido]
        return round(self.contenido * factor, 6), unidad
    confianza: Literal["alta", "media", "baja"]


INSTRUCCIONES = """Normalizas ítems de órdenes de compra públicas de Chile para armar una lista de precios de materiales de construcción. Respondes solo con el JSON del esquema, un objeto por ítem con su "indice".

Para cada ítem:
- es_material_construccion: true si es un material, insumo o herramienta que usaría una constructora (cemento, áridos, acero, madera, planchas, perfiles, pinturas, ferretería, gasfitería, electricidad, aislación, cubiertas). false si no (insumos médicos, oficina, aseo, alimentos) o si es un servicio, mano de obra o un "global".
- material: nombre genérico corto en minúsculas y en singular, sin marca ni medidas (ej. "cemento", "plancha yeso cartón", "perfil acero galvanizado", "pintura esmalte al agua", "arena", "clavo"). Usa siempre el mismo nombre para el mismo material. null si no se entiende.
- especificacion: medidas, espesor, calibre, color o calidad relevantes para el precio (ej. "15 mm 1,2 x 2,4 m", "25 kg", "1/2 pulgada"). null si no hay.
- presentacion: cómo se compra (ej. "saco", "plancha", "rollo", "barra", "galón", "tineta", "caja", "bolsa", "unidad", "m3"). null si no se sabe.
- contenido y unidad_contenido: cuánto material trae UNA presentación, COPIADO TAL COMO ESTÁ ESCRITO, sin convertir unidades (la conversión la hace el sistema). unidad_contenido es una de: unidad, kg, g, ton, m, cm, mm, m2, m3, litro, ml, cc, galon. Ej.: "SIKAFLEX 300ML" -> 300 y "ml"; "SILICONA 370GR" -> 370 y "g"; "saco 25 kg" -> 25 y "kg"; "rollo 100 m" -> 100 y "m"; "galón" -> 1 y "galon"; "caja 100 clavos" -> 100 y "unidad"; una plancha o un candado -> 1 y "unidad". Si el texto no dice el tamaño y no es una pieza única, null en ambos. No adivines tamaños.
- confianza: "alta" si el texto es claro; "media" si dedujiste algo razonable; "baja" si es ambiguo.

No entregas precios ni cantidades compradas: eso lo calcula el sistema. Nunca inventes medidas que no estén en el texto."""


def datos_item(indice, it):
    return {"indice": indice, "producto_mercado_publico": it.get("producto"), "categoria": it.get("categoria"),
            "especificacion_comprador": (it.get("especificacion_comprador") or "")[:400] or None,
            "especificacion_proveedor": (it.get("especificacion_proveedor") or "")[:400] or None}


def validar_lote(texto, esperados):
    """(lista de Normalizado, None) o (None, error). Exige exactamente un objeto por índice esperado."""
    try:
        datos = json.loads(texto)
        lista = [Normalizado.model_validate(x) for x in datos["items"]]
    except (TypeError, ValueError, KeyError, ValidationError) as e:
        return None, f"respuesta inválida: {str(e)[:200]}"
    if sorted(n.indice for n in lista) != sorted(esperados):
        return None, "los índices no coinciden con los ítems enviados"
    return lista, None


def normalizar_lote(cliente, lote, ajustes, presupuesto):
    """lote: [(indice, item)]. Devuelve ({indice: Normalizado}, costo_usd). Un reintento si no valida."""
    import anthropic
    ev = ajustes["evaluacion"]
    entrada = json.dumps([datos_item(i, it) for i, it in lote], ensure_ascii=False)
    esperados = [i for i, _ in lote]
    max_tokens = 400 + 220 * len(lote)
    costo, error = 0.0, None
    for _ in (1, 2):
        contenido = "Ítems (JSON):\n" + entrada + (f"\n\nTu respuesta anterior fue inválida: {error}." if error else "")
        presupuesto.verificar(presupuesto.peor_caso(len(INSTRUCCIONES) + len(contenido), max_tokens))
        try:
            r = cliente.messages.create(
                model=ev["modelo"], max_tokens=max_tokens, system=[{"type": "text", "text": INSTRUCCIONES,
                                                                     "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": contenido}],
                output_config={"effort": ev["esfuerzo"], "format": {"type": "json_schema", "schema": ESQUEMA}})
        except anthropic.APIError as e:
            raise ErrorClaude(f"API de Claude ({type(e).__name__}) al normalizar: {enmascarar(str(e))[:300]}") from None
        usd = presupuesto.costo(r.usage)
        presupuesto.registrar(usd)
        costo += usd
        if r.stop_reason in ("refusal", "max_tokens"):
            error = f"stop_reason {r.stop_reason}"
            continue
        texto = next((b.text for b in r.content if getattr(b, "type", None) == "text"), None)
        lista, error = validar_lote(texto, esperados)
        if lista:
            return {n.indice: n for n in lista}, costo
    log.warning("Lote de %d ítems sin normalizar: %s", len(lote), error)
    return {}, costo


def precios(item, n):
    """Precio por presentación (de la OC) y por unidad base (calculado). None si no corresponde."""
    precio = float(item["precio_neto"])
    contenido, _ = n.base()
    return precio, (round(precio / contenido, 2) if contenido else None)


def ejecutar(ajustes, ocs, cliente=None, presupuesto=None, tamano_lote=25):
    """Normaliza los ítems con precio en CLP de una lista de OC saneadas. Devuelve (filas, resumen)."""
    from zoneinfo import ZoneInfo
    from .evaluacion import Presupuesto, cliente_claude
    from .precios_oc import calidad

    presupuesto = presupuesto or Presupuesto(ajustes, ZoneInfo(ajustes["horario"]["zona"]))
    items = [(oc, it) for oc in ocs for it in oc["items"] if calidad(it) in ("con_unidad", "sin_unidad")]
    cliente = cliente or (cliente_claude(ajustes) if items else None)
    filas, costo, sin_normalizar = [], 0.0, 0
    for desde in range(0, len(items), tamano_lote):
        lote = [(desde + j, it) for j, (_, it) in enumerate(items[desde:desde + tamano_lote])]
        resultado, usd = normalizar_lote(cliente, lote, ajustes, presupuesto)
        costo += usd
        for indice, it in lote:
            oc = items[indice][0]
            n = resultado.get(indice)
            if n is None:
                sin_normalizar += 1
                continue
            precio, por_base = precios(it, n)
            filas.append({
                "oc": oc["codigo"], "correlativo": it.get("correlativo") or (oc["items"].index(it) + 1), "fecha_envio": oc.get("fecha_envio"), "region": oc.get("region"),
                "producto_mercado_publico": it.get("producto"), "codigo_categoria": it.get("codigo_categoria"),
                "especificacion_comprador": it.get("especificacion_comprador"), "cantidad": it.get("cantidad"),
                "precio_presentacion": precio, "precio_unidad_base": por_base, **n.model_dump(exclude={"indice"}),
                "contenido_base": n.base()[0], "unidad_base": n.base()[1]})
    resumen = {"items_con_precio": len(items), "normalizados": len(filas), "sin_normalizar": sin_normalizar,
               "materiales_construccion": sum(f["es_material_construccion"] for f in filas),
               "con_precio_unidad_base": sum(f["es_material_construccion"] and f["precio_unidad_base"] is not None
                                             for f in filas),
               "costo_usd": round(costo, 6)}
    return filas, resumen


def agrupar(filas):
    """Mediana por material + especificación + presentación (solo materiales de construcción)."""
    grupos = defaultdict(list)
    for f in filas:
        if f["es_material_construccion"] and f["material"] and f["presentacion"]:
            grupos[(f["material"], f["especificacion"] or "", f["presentacion"])].append(f)
    salida = []
    for (material, esp, pres), fs in grupos.items():
        base = [f["precio_unidad_base"] for f in fs if f["precio_unidad_base"] is not None]
        salida.append({"material": material, "especificacion": esp or None, "presentacion": pres, "n": len(fs),
                       "mediana_presentacion": statistics.median(f["precio_presentacion"] for f in fs),
                       "unidad_base": next((f["unidad_base"] for f in fs if f["unidad_base"]), None),
                       "mediana_unidad_base": statistics.median(base) if base else None})
    return sorted(salida, key=lambda x: (-x["n"], x["material"]))
