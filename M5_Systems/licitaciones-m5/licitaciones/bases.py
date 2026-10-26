"""Bases de licitaciones: lectura con Claude de los PDF que M5 sube en licitaciones.html.

Por cada PDF pendiente en m5.licitaciones_bases: lo descarga del bucket privado licitaciones-bases,
Claude extrae la lista de materiales con esquema fijo (ítem, material genérico, especificación,
cantidad y unidad tal como están escritas, página) y el código convierte a unidad base. Los materiales
quedan en m5.licitaciones_materiales y la vista m5.licitaciones_materiales_costo los cruza con los
precios de referencia (precios_oc). Claude no ve ni entrega precios.

Los PDF son documentos públicos de Mercado Público, pero lo extraído es interés comercial de M5: solo
se guarda en Supabase y el log lleva cifras agregadas (el repo y sus logs son públicos).
"""
import base64
import json
import logging
from datetime import datetime, timezone
from typing import Literal, Optional
from urllib.parse import quote

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .config import enmascarar, secreto
from .errores import ErrorClaude, TopeGasto
from .normalizacion import CONVERSION

log = logging.getLogger("licitaciones.bases")

BUCKET = "licitaciones-bases"
TABLA_BASES = "licitaciones_bases"
TABLA_MATERIALES = "licitaciones_materiales"
_NULO = {"type": "null"}

ESQUEMA = {
    "type": "object",
    "properties": {"materiales": {"type": "array", "items": {
        "type": "object",
        "properties": {
            "item": {"type": "string"},
            "material": {"anyOf": [{"type": "string"}, _NULO]},
            "especificacion": {"anyOf": [{"type": "string"}, _NULO]},
            "cantidad": {"anyOf": [{"type": "number"}, _NULO]},
            "unidad": {"anyOf": [{"type": "string", "enum": list(CONVERSION)}, _NULO]},
            "pagina": {"anyOf": [{"type": "integer"}, _NULO]},
            "confianza": {"type": "string", "enum": ["alta", "media", "baja"]},
        },
        "required": ["item", "material", "especificacion", "cantidad", "unidad", "pagina", "confianza"],
        "additionalProperties": False,
    }}},
    "required": ["materiales"],
    "additionalProperties": False,
}


class Material(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    item: str = Field(min_length=1, max_length=300)
    material: Optional[str] = Field(max_length=80)
    especificacion: Optional[str] = Field(max_length=160)
    cantidad: Optional[float] = Field(gt=0)
    unidad: Optional[Literal["unidad", "kg", "g", "ton", "m", "cm", "mm", "m2", "m3", "litro", "ml", "cc",
                             "galon"]]
    pagina: Optional[int] = Field(ge=1)
    confianza: Literal["alta", "media", "baja"]

    def base(self):
        if self.cantidad is None or self.unidad is None:
            return None, None
        unidad, factor = CONVERSION[self.unidad]
        return round(self.cantidad * factor, 6), unidad


def instrucciones(conocidos):
    lista = ", ".join(sorted(conocidos)[:400]) or "(todavía no hay)"
    return f"""Lees las bases de una licitación pública de obras en Chile (bases técnicas, especificaciones técnicas, itemizado o presupuesto oficial) y extraes la lista de MATERIALES que la obra necesita, para estimar su costo. Respondes solo con el JSON del esquema.

Por cada material:
- item: la línea o partida tal como aparece en el documento (texto breve).
- material: nombre genérico corto, en minúsculas y singular, sin marca. Si corresponde a uno de esta lista de materiales con precio de referencia, usa EXACTAMENTE ese nombre: {lista}. Si no corresponde a ninguno, escribe un nombre genérico nuevo.
- especificacion: medidas, espesor, calibre, resistencia o calidad (ej. "H-25", "15 mm", "e=0,5 mm"). null si no hay.
- cantidad y unidad: tal como están en el itemizado o cubicación, SIN convertir. unidad es una de: unidad, kg, g, ton, m, cm, mm, m2, m3, litro, ml, cc, galon. En itemizados, "ml" o "m.l." son METROS LINEALES: usa "m". "un", "c/u", "nº" -> "unidad". Si el documento no da cantidad, o la unidad es "gl"/"global", deja cantidad y unidad en null.
- pagina: página del PDF donde está. null si no se sabe.
- confianza: "alta" si la cantidad y la unidad están explícitas; "media" si interpretaste algo; "baja" si es dudoso.

Incluye los materiales de las partidas de obra (hormigón, acero, moldajes, tabiques, revestimientos, cubiertas, pinturas, instalaciones). No incluyas mano de obra, permisos, gastos generales, aseo, ni ítems puramente de servicio. No repitas el mismo material de la misma partida. No entregas precios. Nunca inventes cantidades: si no están, null."""


def validar(texto):
    """(lista de Material, None) o (None, error)."""
    try:
        datos = json.loads(texto)
        return [Material.model_validate(x) for x in datos["materiales"]], None
    except (TypeError, ValueError, KeyError, ValidationError) as e:
        return None, f"respuesta inválida: {str(e)[:200]}"


# --- Supabase y almacenamiento -----------------------------------------------------

def pendientes(sb, limite):
    r = sb._pedir("GET", params=[("select", "id,codigo_externo,ruta,nombre_archivo,bytes"), ("estado", "eq.pendiente"),
                                 ("order", "subido_en.asc"), ("limit", str(limite))])
    return r.json()


def marcar(sb, base_id, **campos):
    sb._pedir("PATCH", params={"id": f"eq.{base_id}"}, json=campos, headers={"Prefer": "return=minimal"})


def descargar(sb, ruta):
    """Descarga el PDF del bucket privado con la misma clave de permisos mínimos (solo lectura del bucket)."""
    import requests
    from .supabase_mp import ErrorSupabase
    url = f"{secreto('SUPABASE_URL').rstrip('/')}/storage/v1/object/authenticated/{BUCKET}/{quote(ruta)}"
    try:
        r = sb.sesion.get(url, timeout=120)
    except (requests.ConnectionError, requests.Timeout) as e:
        raise ErrorSupabase(f"Storage: {type(e).__name__}") from None
    if r.status_code != 200:
        raise ErrorSupabase(f"Storage HTTP {r.status_code} al descargar un PDF: {enmascarar(r.text[:200])}")
    return r.content


def materiales_conocidos(sb_precios):
    r = sb_precios._pedir("GET", params=[("select", "material")])
    return {x["material"] for x in r.json() if x.get("material")}


def guardar_materiales(sb_materiales, base, materiales):
    """Reemplaza los materiales de ese PDF (reprocesar no duplica)."""
    sb_materiales._pedir("DELETE", params={"base_id": f"eq.{base['id']}"}, headers={"Prefer": "return=minimal"})
    filas = []
    for m in materiales:
        cantidad_base, unidad_base = m.base()
        filas.append({"base_id": base["id"], "codigo_externo": base["codigo_externo"], "item": m.item,
                      "material": m.material, "especificacion": m.especificacion, "cantidad": m.cantidad,
                      "unidad": m.unidad, "cantidad_base": cantidad_base, "unidad_base": unidad_base,
                      "pagina": m.pagina, "confianza": m.confianza})
    # Inserción simple: el rol del proceso puede insertar y borrar materiales, pero no actualizarlos.
    for i in range(0, len(filas), 200):
        sb_materiales._pedir("POST", json=filas[i:i + 200], headers={"Prefer": "return=minimal"})
    return len(filas)


# --- Claude ----------------------------------------------------------------------------

def extraer(cliente, pdf, conocidos, cfg, presupuesto):
    """(materiales, tokens_entrada, costo_usd). Lanza ValueError si el PDF supera el tope por documento o
    si la respuesta no valida dos veces; ErrorClaude / TopeGasto se propagan."""
    import anthropic
    system = instrucciones(conocidos)
    documento = {"type": "document", "source": {"type": "base64", "media_type": "application/pdf",
                                                "data": base64.standard_b64encode(pdf).decode()}}
    max_tokens = int(cfg["max_tokens"])
    try:
        conteo = cliente.messages.count_tokens(model=cfg["modelo"], system=system, messages=[
            {"role": "user", "content": [documento, {"type": "text", "text": "Extrae los materiales."}]}])
        tokens = int(conteo.input_tokens)
    except anthropic.APIError as e:
        raise ErrorClaude(f"API de Claude ({type(e).__name__}) al contar tokens: {enmascarar(str(e))[:300]}") from None
    peor = presupuesto.peor_caso_tokens(tokens, max_tokens)
    if peor > float(cfg["tope_por_documento_usd"]):
        raise ValueError(f"el PDF es muy largo para leerlo completo ({tokens:,} tokens; hasta US$ {peor:.2f}, "
                         f"tope por documento US$ {float(cfg['tope_por_documento_usd']):.2f})".replace(",", "."))
    presupuesto.verificar(peor)
    costo, error = 0.0, None
    for _ in (1, 2):
        texto_usuario = "Extrae los materiales." + (f" Tu respuesta anterior fue inválida: {error}." if error else "")
        try:
            with cliente.messages.stream(
                    model=cfg["modelo"], max_tokens=max_tokens, system=system,
                    messages=[{"role": "user", "content": [documento, {"type": "text", "text": texto_usuario}]}],
                    output_config={"effort": cfg["esfuerzo"], "format": {"type": "json_schema", "schema": ESQUEMA}},
            ) as flujo:
                r = flujo.get_final_message()
        except anthropic.APIError as e:
            raise ErrorClaude(f"API de Claude ({type(e).__name__}) al leer bases: {enmascarar(str(e))[:300]}") from None
        usd = presupuesto.costo(r.usage)
        presupuesto.registrar(usd)
        costo += usd
        if r.stop_reason in ("refusal", "max_tokens"):
            error = f"stop_reason {r.stop_reason}"
            if r.stop_reason == "refusal":
                break
            continue
        texto = next((b.text for b in r.content if getattr(b, "type", None) == "text"), None)
        materiales, error = validar(texto)
        if materiales is not None:
            return materiales, tokens, costo
        presupuesto.verificar(peor)
    raise ValueError(f"no se pudo leer la respuesta de Claude ({error})")


# --- Corrida -------------------------------------------------------------------------------

def procesar(ajustes, maximo=None, cliente=None, sb_bases=None, sb_materiales=None, sb_precios=None):
    """Procesa los PDF pendientes. Devuelve un resumen solo con cifras (el log de Actions es público)."""
    from zoneinfo import ZoneInfo
    from .evaluacion import Presupuesto, cliente_claude
    from .supabase_mp import Supabase

    cfg = ajustes["bases"]
    sb_bases = sb_bases or Supabase(ajustes, tabla=TABLA_BASES)
    sb_materiales = sb_materiales or Supabase(ajustes, tabla=TABLA_MATERIALES)
    sb_precios = sb_precios or Supabase(ajustes, tabla="precios_material_base")
    lista = pendientes(sb_bases, int(maximo or cfg["max_por_corrida"]))
    resumen = {"pendientes": len(lista), "listos": 0, "con_error": 0, "materiales": 0, "costo_usd": 0.0}
    if not lista:
        log.info("Bases: no hay PDF pendientes")
        return resumen
    # Presupuesto con los precios del modelo de bases; el gasto del día es el mismo archivo que la evaluación.
    aj_bases = {**ajustes, "evaluacion": {**ajustes["evaluacion"], "modelo": cfg["modelo"]}}
    presupuesto = Presupuesto(aj_bases, ZoneInfo(ajustes["horario"]["zona"]))
    cliente = cliente or cliente_claude(aj_bases)
    conocidos = materiales_conocidos(sb_precios)
    for base in lista:
        marcar(sb_bases, base["id"], estado="procesando", error=None)
        try:
            if (base.get("bytes") or 0) > float(cfg["max_mb"]) * 1024 * 1024:
                raise ValueError(f"el PDF pesa más de {cfg['max_mb']} MB")
            pdf = descargar(sb_bases, base["ruta"])
            materiales, tokens, costo = extraer(cliente, pdf, conocidos, cfg, presupuesto)
            n = guardar_materiales(sb_materiales, base, materiales)
            marcar(sb_bases, base["id"], estado="listo", procesado_en=datetime.now(timezone.utc).isoformat(),
                   tokens_entrada=tokens, costo_usd=round(costo, 6))
            resumen["listos"] += 1
            resumen["materiales"] += n
            resumen["costo_usd"] = round(resumen["costo_usd"] + costo, 6)
        except TopeGasto:
            marcar(sb_bases, base["id"], estado="pendiente")  # se reintenta otro día
            raise
        except ValueError as e:
            marcar(sb_bases, base["id"], estado="error", error=str(e)[:300],
                   procesado_en=datetime.now(timezone.utc).isoformat())
            resumen["con_error"] += 1
        except Exception:
            marcar(sb_bases, base["id"], estado="error", error="error inesperado; ver el log del workflow",
                   procesado_en=datetime.now(timezone.utc).isoformat())
            raise
    log.info("Bases: %d pendientes, %d listas, %d con error, %d materiales, US$ %.4f", resumen["pendientes"],
             resumen["listos"], resumen["con_error"], resumen["materiales"], resumen["costo_usd"])
    return resumen
