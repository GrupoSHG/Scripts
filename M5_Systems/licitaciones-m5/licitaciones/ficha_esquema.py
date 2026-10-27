"""Esquema de la ficha de postulación que Claude extrae de las bases (fichas.py).

Claude solo copia texto: cada dato trae el texto tal como está en las bases, el documento y la página
donde aparece y una cita textual corta. Montos, porcentajes, plazos y fechas límite los calcula el código
a partir de ese texto y de las fechas de la API. Un dato que no está en las bases queda null.

A la API se le pide una lista PLANA de datos (`ESQUEMA_EXTRACCION`): {campo, texto, detalle, documento,
pagina, cita}, con `campo` = ruta del dato en la ficha. Un esquema anidado con todos los campos opcionales
fue rechazado por la salida estructurada (más de 16 parámetros con unión, y después "compiled grammar is too
large"; dry-run real del 27/10/2026). `desde_api` rearma la forma anidada que valida `ExtraccionBases`, y
`verificar_citas` comprueba que cada cita aparezca en el texto de su página.
"""
import re
import unicodedata
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

# Campo -> qué es. Los de un solo valor toman la primera aparición; los de LISTAS admiten varias.
CAMPOS = {
    "tipo_de_obra": "tipo de obra en pocas palabras",
    "presupuesto_oficial": "presupuesto o monto disponible, con moneda, tal como está escrito",
    "fechas.consultas": "plazo para hacer consultas",
    "fechas.visita_terreno": "fecha y hora de la visita a terreno",
    "fechas.cierre": "fecha de cierre de ofertas",
    "fechas.adjudicacion": "fecha o plazo de adjudicación",
    "admisibilidad.documentos_obligatorios": "un documento o anexo obligatorio de la oferta (uno por dato)",
    "admisibilidad.registro_proveedores": "exigencia de inscripción en el Registro de Proveedores",
    "admisibilidad.otros_registros": "otro registro exigido (MOP, MINVU, SEC, municipal...) con su categoría (uno por dato)",
    "admisibilidad.experiencia_minima": "experiencia mínima exigida",
    "admisibilidad.capacidad_economica": "capital, patrimonio, índices o capacidad económica exigida",
    "admisibilidad.visita_terreno_obligatoria": "si la visita a terreno es obligatoria",
    "garantias.seriedad_oferta.monto_o_porcentaje": "monto o porcentaje de la garantía de seriedad de la oferta",
    "garantias.seriedad_oferta.vigencia": "vigencia exigida a la garantía de seriedad",
    "garantias.seriedad_oferta.formatos": "instrumentos aceptados para la garantía de seriedad",
    "garantias.fiel_cumplimiento.monto_o_porcentaje": "monto o porcentaje de la garantía de fiel cumplimiento",
    "garantias.fiel_cumplimiento.vigencia": "vigencia exigida a la garantía de fiel cumplimiento",
    "garantias.fiel_cumplimiento.formatos": "instrumentos aceptados para la garantía de fiel cumplimiento",
    "criterios_evaluacion": "un criterio de evaluación; en detalle su ponderación tal como está escrita (uno por dato)",
    "contrato.plazo_ejecucion": "plazo de ejecución",
    "contrato.multas": "multas por atraso u otros incumplimientos",
    "contrato.retenciones": "retenciones de los estados de pago",
    "contrato.forma_pago": "forma de pago (estados de pago, anticipo, plazos)",
    "contrato.reajustes": "reajuste del precio, o que no hay reajuste",
    "riesgos": "un riesgo o cláusula inusual para el contratista, en una frase (uno por dato)",
}
LISTAS = {"admisibilidad.documentos_obligatorios", "admisibilidad.otros_registros", "criterios_evaluacion", "riesgos"}

ESQUEMA_EXTRACCION = {
    "type": "object",
    "properties": {"datos": {"type": "array", "items": {
        "type": "object",
        "properties": {
            "campo": {"type": "string", "enum": list(CAMPOS)},
            "texto": {"type": "string", "description": "contenido tal como está escrito, sin cambiar cifras"},
            "detalle": {"type": "string", "description": "solo en criterios_evaluacion: la ponderación; si no, vacío"},
            "documento": {"type": "integer", "description": "número del documento ([DOCUMENTO N])"},
            "pagina": {"type": "integer", "description": "página dentro de ese documento ([PÁGINA N])"},
            "cita": {"type": "string", "description": "frase copiada textual del documento, máximo 200 caracteres"},
        },
        "required": ["campo", "texto", "detalle", "documento", "pagina", "cita"],
        "additionalProperties": False,
    }}},
    "required": ["datos"],
    "additionalProperties": False,
}

ESQUEMA_RECOMENDACION = {
    "type": "object",
    "properties": {
        "decision": {"type": "string", "enum": ["postular", "revisar", "descartar"]},
        "razones": {"type": "array", "items": {"type": "string"}, "description": "exactamente 3, una línea cada una"},
    },
    "required": ["decision", "razones"],
    "additionalProperties": False,
}


def vacia():
    """Extracción con todo en null / listas vacías (la forma de `ExtraccionBases`)."""
    e = {}
    for campo in CAMPOS:
        *ruta, hoja = campo.split(".")
        nodo = e
        for p in ruta:
            nodo = nodo.setdefault(p, {})
        nodo[hoja] = [] if campo in LISTAS else None
    return e


def desde_api(respuesta):
    """{"datos": [...]} de la API -> extracción anidada. Un campo desconocido se deja tal cual para que la
    validación lo rechace; de un campo de un solo valor vale la primera aparición."""
    e = vacia()
    for d in respuesta["datos"]:
        campo = d.get("campo")
        if campo not in CAMPOS:
            e.setdefault("_desconocidos", []).append(campo)
            continue
        valor = {k: d.get(k) for k in ("texto", "documento", "pagina", "cita")}
        if campo == "criterios_evaluacion":
            valor = {"criterio": d.get("texto"), "ponderacion": (d.get("detalle") or "").strip() or None,
                     **{k: d.get(k) for k in ("documento", "pagina", "cita")}}
        *ruta, hoja = campo.split(".")
        nodo = e
        for p in ruta:
            nodo = nodo[p]
        if campo in LISTAS:
            nodo[hoja].append(valor)
        elif nodo[hoja] is None:
            nodo[hoja] = valor
    return e


# --- Validación local ---------------------------------------------------------------

class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Dato(_Base):
    texto: str = Field(min_length=1, max_length=600)
    documento: int = Field(ge=1)
    pagina: int = Field(ge=1)
    cita: str = Field(min_length=3, max_length=300)


class Criterio(_Base):
    criterio: str = Field(min_length=1, max_length=300)
    ponderacion: Optional[str] = Field(max_length=60)
    documento: int = Field(ge=1)
    pagina: int = Field(ge=1)
    cita: str = Field(min_length=3, max_length=300)


class Garantia(_Base):
    monto_o_porcentaje: Optional[Dato]
    vigencia: Optional[Dato]
    formatos: Optional[Dato]


class Fechas(_Base):
    consultas: Optional[Dato]
    visita_terreno: Optional[Dato]
    cierre: Optional[Dato]
    adjudicacion: Optional[Dato]


class Admisibilidad(_Base):
    documentos_obligatorios: list[Dato]
    registro_proveedores: Optional[Dato]
    otros_registros: list[Dato]
    experiencia_minima: Optional[Dato]
    capacidad_economica: Optional[Dato]
    visita_terreno_obligatoria: Optional[Dato]


class Garantias(_Base):
    seriedad_oferta: Garantia
    fiel_cumplimiento: Garantia


class Contrato(_Base):
    plazo_ejecucion: Optional[Dato]
    multas: Optional[Dato]
    retenciones: Optional[Dato]
    forma_pago: Optional[Dato]
    reajustes: Optional[Dato]


class ExtraccionBases(_Base):
    tipo_de_obra: Optional[Dato]
    presupuesto_oficial: Optional[Dato]
    fechas: Fechas
    admisibilidad: Admisibilidad
    garantias: Garantias
    criterios_evaluacion: list[Criterio]
    contrato: Contrato
    riesgos: list[Dato]


class Recomendacion(_Base):
    decision: Literal["postular", "revisar", "descartar"]
    razones: list[str] = Field(min_length=3, max_length=3)


# --- Citas ------------------------------------------------------------------------------

def normalizar(texto):
    """Minúsculas, sin tildes, sin guiones de corte de línea y con un solo espacio: la extracción de texto
    del PDF parte palabras y líneas distinto de como las copia el modelo."""
    texto = unicodedata.normalize("NFKD", texto or "")
    texto = "".join(c for c in texto if not unicodedata.combining(c)).lower()
    texto = re.sub(r"-\s*\n\s*", "", texto)
    texto = re.sub(r"[\"'“”‘’«»]", "", texto)
    return re.sub(r"\s+", " ", texto).strip()


def recorrer(nodo, ruta=""):
    """(ruta, dict) de cada dato con cita dentro de una extracción (dict ya validado)."""
    if isinstance(nodo, dict):
        if "cita" in nodo and "pagina" in nodo:
            yield ruta, nodo
            return
        for k, v in nodo.items():
            yield from recorrer(v, f"{ruta}.{k}" if ruta else k)
    elif isinstance(nodo, list):
        for i, v in enumerate(nodo):
            yield from recorrer(v, f"{ruta}[{i}]")


def verificar_citas(extraccion, paginas):
    """Rutas de los datos cuya cita no aparece en su página. `paginas`: {(documento, pagina): texto}.
    Se acepta que la cita cruce el salto a la página anterior o a la siguiente."""
    normalizadas = {k: normalizar(v) for k, v in paginas.items()}
    malas = []
    for ruta, d in recorrer(extraccion):
        cita = normalizar(d["cita"]).rstrip(".…").strip()
        doc, pag = d["documento"], d["pagina"]
        t = lambda p: normalizadas.get((doc, p), "")
        if not cita or not any(cita in x for x in (t(pag), f"{t(pag - 1)} {t(pag)}", f"{t(pag)} {t(pag + 1)}")):
            malas.append(ruta)
    return malas
