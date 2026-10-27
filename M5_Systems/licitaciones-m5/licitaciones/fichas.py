"""Fichas de postulación: análisis con Claude de las bases de las licitaciones con puntaje alto.

Candidatas: publicadas en m5.licitaciones_mp con puntaje >= fichas.puntaje_minimo, que no estén para
descartar y cuyo cierre no haya pasado. La API de Mercado Público no entrega las bases (NOTAS_API.md), así
que los PDF son los que M5 sube en licitaciones.html (bucket privado licitaciones-bases, los mismos que lee
bases.py). Sin PDF la ficha queda "adjuntos_pendientes" con el enlace a la ficha oficial; con PDF nuevo se
vuelve a generar.

Reglas:
- Claude solo extrae texto (ficha_esquema.py): cada dato con documento, página y cita textual, que se
  verifica contra el texto de esa página; un dato cuya cita no aparece se saca de la ficha y queda listado
  para revisión. Fechas límite, días hábiles, porcentajes y montos de garantías los calcula este módulo.
- Se envía el texto extraído con pypdf (no el PDF): un PDF sin texto se marca "escaneado" (sin OCR).
  Solo se aceptan archivos que empiezan como PDF; nada se abre ni se ejecuta con otro programa.
- Bases largas: se dividen en partes por páginas y las extracciones se combinan.
- Esquema inválido dos veces o citas que no calzan: la ficha queda "revision_manual".
- Tope de gasto por corrida además del diario de evaluacion.py: al llegar, se detiene y lo que falta queda
  para la corrida siguiente. Un error en una licitación no detiene las demás.

Lo extraído es interés comercial de M5: va a Supabase (m5.licitaciones_fichas) y a salida/fichas/<código>/
en el runner; el log y el artefacto de Actions (repo público) llevan solo cifras.
"""
import io
import json
import logging
import re
import time
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import yaml
from pydantic import ValidationError

from . import ficha_esquema as fe
from .config import SALIDA, enmascarar
from .errores import ErrorAPI, ErrorClaude, LimiteSolicitudes, TopeGasto

log = logging.getLogger("licitaciones.fichas")

TABLA = "licitaciones_fichas"
CARPETA = SALIDA / "fichas"
AVISO = "Extraído automáticamente: confirmar con las bases originales"


class TopeCorrida(TopeGasto):
    """La siguiente llamada superaría el tope de gasto de esta corrida de fichas."""


# --- Candidatas ---------------------------------------------------------------------------

def _en(codigos):
    return "in.(" + ",".join(f'"{c}"' for c in codigos) + ")"


def candidatas(cfg, sb_lic, sb_bases, sb_fichas, ahora):
    """[(licitación, [PDF])] que necesitan ficha: sin ficha o con PDF distintos a los de la última.
    Primero las que tienen PDF (las que gastan Claude), por cierre más cercano."""
    campos = ("codigo_externo,nombre,organismo,region,comuna,tipo,fecha_publicacion,fecha_cierre,monto_estimado,"
              "url_ficha,puntaje,recomendacion,tipo_de_obra")
    lics = sb_lic._pedir("GET", params=[
        ("select", campos), ("codigo_estado", "eq.5"), ("puntaje", f"gte.{int(cfg['puntaje_minimo'])}"),
        ("recomendacion", "neq.descartar"), ("fecha_cierre", f"gt.{ahora.isoformat(timespec='seconds')}"),
        ("order", "fecha_cierre")]).json()
    if not lics:
        return []
    codigos = [l["codigo_externo"] for l in lics]
    pdfs = {}
    for b in sb_bases._pedir("GET", params=[("select", "id,codigo_externo,ruta,nombre_archivo,bytes"),
                                            ("codigo_externo", _en(codigos)), ("order", "id")]).json():
        pdfs.setdefault(b["codigo_externo"], []).append(b)
    previas = {f["codigo_externo"]: f for f in sb_fichas._pedir("GET", params=[
        ("select", "codigo_externo,estado,bases_ids"), ("codigo_externo", _en(codigos))]).json()}
    con_pdf, sin_pdf = [], []
    for l in lics:
        docs = pdfs.get(l["codigo_externo"], [])
        previa = previas.get(l["codigo_externo"])
        if previa and sorted(previa.get("bases_ids") or []) == sorted(d["id"] for d in docs) and previa["estado"] != "error":
            continue
        (con_pdf if docs else sin_pdf).append((l, docs))
    return con_pdf[:int(cfg["max_por_corrida"])] + sin_pdf[:int(cfg["max_pendientes_por_corrida"])]


# --- PDF ------------------------------------------------------------------------------------

def leer_pdf(contenido):
    """Texto de cada página. ValueError si no es un PDF o está protegido."""
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError
    if b"%PDF-" not in contenido[:1024]:
        raise ValueError("el archivo no es un PDF")
    try:
        lector = PdfReader(io.BytesIO(contenido), strict=False)
        if lector.is_encrypted and not lector.decrypt(""):
            raise ValueError("el PDF está protegido con contraseña")
        paginas = []
        for p in lector.pages:
            try:
                paginas.append(p.extract_text() or "")
            except Exception:  # una página dañada no invalida el resto
                paginas.append("")
        return paginas
    except (PdfReadError, OSError, KeyError, TypeError) as e:
        raise ValueError(f"no se pudo leer el PDF ({type(e).__name__})") from None


def documento(n, nombre, paginas, cfg):
    """Resumen de un documento leído: páginas, cuáles no tienen texto y si parece escaneado."""
    minimo = int(cfg["min_caracteres_por_pagina"])
    sin_texto = [i for i, t in enumerate(paginas, 1) if len(t.strip()) < minimo]
    escaneado = not paginas or len(sin_texto) / len(paginas) > 0.8
    return {"n": n, "nombre": nombre, "paginas": len(paginas), "paginas_sin_texto": sin_texto,
            "escaneado": escaneado, "error": None}


def partes(docs, textos, max_caracteres):
    """Divide el texto (con marcas de documento y página) en partes de a lo más `max_caracteres`."""
    salida, actual, doc_actual = [], "", None
    for d in docs:
        if d["escaneado"] or d["error"]:
            continue
        encabezado = f"[DOCUMENTO {d['n']}: {d['nombre']}]\n"
        for i, t in enumerate(textos[d["n"]], 1):
            bloque = f"[PÁGINA {i}]\n{t.strip()}\n\n"
            if actual and len(actual) + len(encabezado) + len(bloque) > max_caracteres:
                salida.append(actual)
                actual, doc_actual = "", None
            if doc_actual != d["n"]:   # cada parte nueva y cada documento nuevo llevan su encabezado
                actual += encabezado
                doc_actual = d["n"]
            actual += bloque[:max_caracteres]
    if actual:
        salida.append(actual)
    return salida


# --- Claude -----------------------------------------------------------------------------------

INSTRUCCIONES_EXTRACCION = """Lees las bases de una licitación pública de obras en Chile (bases administrativas, técnicas y anexos) para armar la ficha de postulación de M5 Industrial, constructora. Respondes solo con el JSON del esquema.

El texto viene marcado con [DOCUMENTO N: nombre] y [PÁGINA N]. Entregas una lista "datos": un elemento por cada dato encontrado, con su campo.

Reglas:
- Cada dato lleva el documento y la página donde aparece y una cita: una frase copiada EXACTAMENTE del texto (sin corregir ortografía ni cambiar palabras), de 5 a 30 palabras, que respalde el dato. El sistema verifica que la cita esté en esa página: si no está, el dato se descarta.
- texto: el contenido tal como está escrito, resumido sin cambiar cifras. Copia montos, porcentajes, plazos y fechas exactamente como aparecen ("5% del valor total de la oferta", "UF 150", "120 días corridos"). No conviertas unidades, no calcules, no sumes.
- admisibilidad.documentos_obligatorios: revisa la sección de antecedentes de la oferta (administrativos, técnicos y económicos) e incluye CADA anexo o documento que se debe presentar, uno por dato (Anexo 1, Anexo 2, ...). Si un anexo es facultativo o solo para UTP, dilo en el texto.
- detalle: vacío, salvo en criterios_evaluacion, donde va la ponderación tal como está escrita ("60%").
- Si un dato no aparece en este texto, simplemente no lo incluyas. Nunca lo deduzcas de la práctica habitual ni de otras licitaciones.
- riesgos: cláusulas inusuales u onerosas para el contratista (multas altas, plazos muy cortos, garantías sobre lo habitual, pago solo contra recepción, sin reajuste en obras largas, experiencia muy específica, causales amplias de término anticipado...). Máximo 8.
- Puede que recibas solo una parte de las bases: extrae lo que esté en esta parte.

Campos (los marcados "uno por dato" pueden repetirse; los demás, una sola vez):
""" + "\n".join(f"- {c}: {d}" for c, d in fe.CAMPOS.items())

INSTRUCCIONES_RECOMENDACION = """Eres analista de licitaciones de M5 Industrial, constructora del Grupo SHG (Chile). Recibes la ficha de una licitación extraída de sus bases, con cifras calculadas por el sistema (días hábiles al cierre, montos de garantías), y el perfil de la empresa. Respondes solo con el JSON del esquema.

- decision: "postular" si calza con el perfil y no hay nada importante en contra; "revisar" si faltan datos críticos (garantías, plazos, requisitos) o hay dudas; "descartar" si está fuera del perfil o los requisitos no se pueden cumplir.
- razones: exactamente 3, una línea cada una, máximo 160 caracteres, basadas solo en la ficha y el perfil.
- No inventes cifras ni requisitos que no estén en la ficha."""


class Gasto:
    """Presupuesto diario de evaluacion.py (precios del modelo) más el tope de esta corrida, que comparten
    todos los modelos a través de `corrida` ({"usd": ...}). En --dry-run no escribe el gasto del día."""

    def __init__(self, ajustes, modelo, tope_corrida, corrida, guardar=True, zona=None):
        from .evaluacion import Presupuesto
        aj = {**ajustes, "evaluacion": {**ajustes["evaluacion"], "modelo": modelo}}
        self.presupuesto = Presupuesto(aj, zona or ZoneInfo(ajustes["horario"]["zona"]))
        self.tope_corrida = float(tope_corrida)
        self.corrida = corrida
        self.guardar = guardar

    def verificar(self, peor):
        if self.corrida["usd"] + peor > self.tope_corrida:
            raise TopeCorrida(f"Tope de gasto de la corrida de fichas: US$ {self.tope_corrida:.2f} (gastado "
                              f"US$ {self.corrida['usd']:.4f}; la siguiente llamada podría costar US$ {peor:.4f}).")
        self.presupuesto.verificar(peor)

    def registrar(self, usage):
        usd = self.presupuesto.costo(usage)
        self.corrida["usd"] += usd
        if self.guardar:
            self.presupuesto.registrar(usd)
        return usd


def _llamar(cliente, cfg, modelo, gasto, system, contenido, esquema, cuenta):
    """Una llamada con verificación previa del peor caso. Devuelve (texto o None, stop_reason)."""
    import anthropic
    max_tokens = int(cfg["max_tokens"])
    try:
        tokens = int(cliente.messages.count_tokens(model=modelo, system=system,
                                                   messages=[{"role": "user", "content": contenido}]).input_tokens)
        gasto.verificar(gasto.presupuesto.peor_caso_tokens(tokens, max_tokens))
        r = cliente.messages.create(
            model=modelo, max_tokens=max_tokens, system=system, messages=[{"role": "user", "content": contenido}],
            output_config={"effort": cfg["esfuerzo"], "format": {"type": "json_schema", "schema": esquema}})
    except anthropic.APIError as e:
        raise ErrorClaude(f"API de Claude ({type(e).__name__}): {enmascarar(str(e))[:300]}") from None
    cuenta["llamadas"] += 1
    cuenta["costo_usd"] = round(cuenta["costo_usd"] + gasto.registrar(r.usage), 6)
    for clave, campo in (("entrada", "input_tokens"), ("salida", "output_tokens"),
                         ("cache_lectura", "cache_read_input_tokens"), ("cache_escritura", "cache_creation_input_tokens")):
        cuenta["tokens"][clave] += getattr(r.usage, campo, None) or 0
    texto = next((b.text for b in r.content if getattr(b, "type", None) == "text"), None)
    return texto, r.stop_reason


def _validar_extraccion(texto, paginas):
    """(dict, citas malas, None) o (None, None, error de esquema)."""
    try:
        datos = fe.ExtraccionBases.model_validate(fe.desde_api(json.loads(texto))).model_dump()
    except (TypeError, ValueError, KeyError, AttributeError, ValidationError) as e:
        return None, None, f"no cumple el esquema: {type(e).__name__} {str(e)[:300]}"
    return datos, fe.verificar_citas(datos, paginas), None


def extraer_parte(cliente, cfg, modelo, gasto, texto_parte, paginas, cuenta):
    """Extracción de una parte. (dict, citas que no calzaron) o (None, error) tras dos intentos."""
    system = [{"type": "text", "text": INSTRUCCIONES_EXTRACCION, "cache_control": {"type": "ephemeral"}}]
    error, datos, malas = None, None, []
    for _ in (1, 2):
        contenido = "Bases (texto extraído del PDF):\n\n" + texto_parte
        if error:
            contenido += f"\n\nTu respuesta anterior no pasó la validación: {error} Corrígela."
        respuesta, motivo = _llamar(cliente, cfg, modelo, gasto, system, contenido, fe.ESQUEMA_EXTRACCION, cuenta)
        if motivo == "refusal":
            return None, "el modelo rechazó la solicitud"
        if motivo == "max_tokens":
            error = "la respuesta se cortó por max_tokens; sé más breve en los textos."
            continue
        nuevo, nuevas_malas, error_esquema = _validar_extraccion(respuesta, paginas)
        if error_esquema:
            error = error_esquema
            continue
        datos, malas = nuevo, nuevas_malas
        if not malas:
            return datos, []
        error = ("estas citas no aparecen textualmente en la página indicada: " + ", ".join(malas[:12]) +
                 ". Copia la frase exacta del texto o no incluyas el dato.")
    return (datos, malas) if datos else (None, error)


def recomendar(cliente, cfg, modelo, gasto, perfil, resumen, cuenta):
    """(dict de Recomendacion o None, error)."""
    system = [{"type": "text", "text": INSTRUCCIONES_RECOMENDACION},
              {"type": "text", "text": "Perfil de M5 Industrial (YAML):\n" + yaml.safe_dump(perfil, allow_unicode=True, sort_keys=True),
               "cache_control": {"type": "ephemeral"}}]
    error = None
    for _ in (1, 2):
        contenido = "Ficha (JSON):\n" + json.dumps(resumen, ensure_ascii=False)
        if error:
            contenido += f"\n\nTu respuesta anterior no pasó la validación: {error} Corrígela."
        respuesta, motivo = _llamar(cliente, cfg, modelo, gasto, system, contenido, fe.ESQUEMA_RECOMENDACION, cuenta)
        if motivo == "refusal":
            return None, "el modelo rechazó la solicitud"
        try:
            r = fe.Recomendacion.model_validate(json.loads(respuesta or ""))
            if any(not x.strip() or len(x) > 220 or "\n" in x.strip() for x in r.razones):
                raise ValueError("cada razón debe ser una línea de hasta 160 caracteres")
            return r.model_dump(), None
        except (ValueError, ValidationError) as e:
            error = f"respuesta inválida: {str(e)[:200]}"
    return None, error


# --- Combinar partes y quitar datos sin respaldo ---------------------------------------------------

def _quitar(nodo, ruta):
    """Saca de `nodo` el dato en `ruta` (a.b[2].c): null si es un campo, fuera de la lista si es elemento."""
    pasos = re.findall(r"[^.\[\]]+|\[\d+\]", ruta)
    for p in pasos[:-1]:
        nodo = nodo[int(p[1:-1])] if p.startswith("[") else nodo[p]
    ultimo = pasos[-1]
    if ultimo.startswith("["):
        nodo[int(ultimo[1:-1])] = None
    else:
        nodo[ultimo] = None


def _obtener(nodo, ruta):
    for p in re.findall(r"[^.\[\]]+|\[\d+\]", ruta):
        nodo = nodo[int(p[1:-1])] if p.startswith("[") else nodo[p]
    return nodo


def depurar(extraccion, malas):
    """Quita de la extracción los datos con cita no verificada y devuelve qué se quitó (para revisión)."""
    quitados = []
    for ruta in malas:
        d = _obtener(extraccion, ruta)
        quitados.append({"campo": ruta, "texto": d.get("texto") or d.get("criterio"),
                         "documento": d["documento"], "pagina": d["pagina"]})
    # Los elementos de lista quedan en None y se sacan al final, así los índices de `malas` siguen valiendo.
    for ruta in malas:
        _quitar(extraccion, ruta)
    _sin_nulos_en_listas(extraccion)
    return quitados


def _sin_nulos_en_listas(n):
    if isinstance(n, dict):
        for v in n.values():
            _sin_nulos_en_listas(v)
    elif isinstance(n, list):
        n[:] = [x for x in n if x is not None]
        for v in n:
            _sin_nulos_en_listas(v)


def combinar(extracciones):
    """Une las extracciones de varias partes: el primer dato no nulo y las listas sin repetir."""
    def unir(a, b):
        if isinstance(a, dict) and "cita" not in a and isinstance(b, dict):
            return {k: unir(a.get(k), b.get(k)) for k in a}
        if isinstance(a, list) and isinstance(b, list):
            vistos = {fe.normalizar(x.get("texto") or x.get("criterio") or "") for x in a}
            return a + [x for x in b if fe.normalizar(x.get("texto") or x.get("criterio") or "") not in vistos]
        return a if a is not None else b
    total = extracciones[0]
    for e in extracciones[1:]:
        total = unir(total, e)
    return total


# --- Cálculos (los hace el código, nunca Claude) ---------------------------------------------------

_PCT = re.compile(r"(\d{1,3}(?:[.,]\d+)?)\s*(?:%|por\s*ciento)", re.I)
# Pesos: con separador de miles o de 4 dígitos o más, y que no sea un porcentaje ("$5% del valor" visto en bases reales).
_CLP = re.compile(r"\$\s*(\d{1,3}(?:\.\d{3})+|\d{4,})(?![.,]?\d)(?!\s*%)")
_UF = re.compile(r"\bU\.?F\.?\s*(\d{1,3}(?:\.\d{3})*(?:,\d+)?|\d+(?:,\d+)?)", re.I)
_PLAZO = re.compile(r"(\d{1,4})\s*(d[ií]as?|mes(?:es)?|semanas?|años?)\s*(corridos|h[aá]biles|calendario)?", re.I)


def _numero(texto):
    return float(texto.replace(".", "").replace(",", "."))


def porcentaje(texto):
    m = _PCT.search(texto or "")
    return float(m.group(1).replace(",", ".")) if m else None


def monto_clp(texto):
    m = _CLP.search(texto or "")
    return int(m.group(1).replace(".", "")) if m else None


def monto_uf(texto):
    m = _UF.search(texto or "")
    return _numero(m.group(1)) if m else None


def plazo(texto):
    """{'cantidad': 120, 'unidad': 'días', 'tipo': 'corridos'} o None."""
    m = _PLAZO.search(texto or "")
    if not m:
        return None
    unidad = m.group(2).lower()
    unidad = "días" if unidad.startswith("d") else "meses" if unidad.startswith("m") else \
        "semanas" if unidad.startswith("s") else "años"
    tipo = (m.group(3) or "").lower().replace("á", "a") or None
    return {"cantidad": int(m.group(1)), "unidad": unidad, "tipo": tipo}


def dias_habiles(desde, hasta, feriados):
    """Días hábiles (lunes a viernes sin feriados) después de `desde` y hasta `hasta` inclusive."""
    if hasta <= desde:
        return 0
    n, d = 0, desde
    while d < hasta:
        d += timedelta(days=1)
        if d.weekday() < 5 and d not in feriados:
            n += 1
    return n


def fechas_api(det, lic, zona):
    """Fechas oficiales del detalle de la API (hora de Chile); el cierre cae a licitaciones_mp si no hay detalle."""
    from .detalle import fecha_chile
    f = (det or {}).get("Fechas") or {}
    return {
        "publicacion": fecha_chile(f.get("FechaPublicacion"), zona) or lic.get("fecha_publicacion"),
        "inicio_consultas": fecha_chile(f.get("FechaInicio"), zona),
        "fin_consultas": fecha_chile(f.get("FechaFinal"), zona),
        "respuestas": fecha_chile(f.get("FechaPubRespuestas"), zona),
        "visita_terreno": fecha_chile(f.get("FechaVisitaTerreno"), zona),
        "cierre": fecha_chile(f.get("FechaCierre"), zona) or lic.get("fecha_cierre"),
        "adjudicacion": fecha_chile(f.get("FechaAdjudicacion") or f.get("FechaEstimadaAdjudicacion"), zona),
    }


def calcular(extraccion, fechas, monto_api, hoy, feriados, dias_alerta):
    """Cifras de la ficha: días al cierre y a cada fecha, garantías y ponderaciones."""
    def dias(iso):
        if not iso:
            return None
        d = datetime.fromisoformat(iso).date()
        return {"corridos": (d - hoy).days, "habiles": dias_habiles(hoy, d, feriados)}
    plazos = {k: dias(v) for k, v in fechas.items() if v and datetime.fromisoformat(v).date() >= hoy}
    presupuesto_txt = ((extraccion or {}).get("presupuesto_oficial") or {}).get("texto")
    base = monto_api or monto_clp(presupuesto_txt)
    garantias = {}
    for nombre in ("seriedad_oferta", "fiel_cumplimiento"):
        g = ((extraccion or {}).get("garantias") or {}).get(nombre) or {}
        texto = (g.get("monto_o_porcentaje") or {}).get("texto")
        pct, clp, uf = porcentaje(texto), monto_clp(texto), monto_uf(texto)
        garantias[nombre] = {
            "porcentaje": pct, "monto_clp": clp, "monto_uf": uf,
            "monto_referencial_clp": round(base * pct / 100) if pct is not None and base and clp is None else None,
            "base_referencial": ("monto estimado publicado" if monto_api else "presupuesto oficial de las bases")
            if pct is not None and base and clp is None else None,
            "vigencia": plazo((g.get("vigencia") or {}).get("texto")),
        }
    criterios = (extraccion or {}).get("criterios_evaluacion") or []
    ponderaciones = [porcentaje(c.get("ponderacion")) for c in criterios]
    suma = round(sum(p for p in ponderaciones if p is not None), 2) if any(p is not None for p in ponderaciones) else None
    plazo_ej = plazo((((extraccion or {}).get("contrato") or {}).get("plazo_ejecucion") or {}).get("texto"))
    cierre = plazos.get("cierre")
    return {
        "dias": plazos,
        "dias_habiles_cierre": cierre["habiles"] if cierre else None,
        "alerta_cierre": bool(cierre and cierre["habiles"] < int(dias_alerta)),
        "monto_base_clp": base,
        "garantias": garantias,
        "ponderaciones_pct": ponderaciones,
        "suma_ponderaciones_pct": suma,
        "aviso_ponderaciones": f"las ponderaciones suman {suma:g}%, no 100%" if suma is not None and abs(suma - 100) > 0.5 else None,
        "plazo_ejecucion": plazo_ej,
    }


def _fuente(dato):
    return None if not dato else {"documento": dato["documento"], "pagina": dato["pagina"], "cita": dato["cita"]}


def checklist(extraccion, fechas, calculos):
    """Tareas de postulación con fecha límite (de la API) y la fuente en las bases de cada una."""
    e = extraccion or {}
    adm, gar = e.get("admisibilidad") or {}, (e.get("garantias") or {}).get("seriedad_oferta") or {}
    cierre, dias = fechas.get("cierre"), calculos["dias"]
    api = "API Mercado Público"
    tareas = []

    def tarea(texto, fecha, clave, fuente, nota=None):
        vencida = bool(fecha) and clave not in dias   # `dias` solo trae las fechas de hoy en adelante
        tareas.append({"tarea": texto, "fecha_limite": fecha, "dias": dias.get(clave) if fecha else None,
                       "fuente": fuente, "nota": "PLAZO VENCIDO" if vencida else nota, "vencida": vencida})

    if fechas.get("fin_consultas"):
        tarea("Enviar consultas por el foro de Mercado Público", fechas["fin_consultas"], "fin_consultas", api)
    visita = (e.get("fechas") or {}).get("visita_terreno") or adm.get("visita_terreno_obligatoria")
    if fechas.get("visita_terreno") or visita:
        tarea("Asistir a la visita a terreno", fechas.get("visita_terreno"), "visita_terreno", _fuente(visita) or api,
              None if fechas.get("visita_terreno") else "la API no trae la fecha: ver la cita en las bases")
    if adm.get("registro_proveedores"):
        tarea("Inscripción vigente en el Registro de Proveedores", cierre, "cierre", _fuente(adm["registro_proveedores"]),
              "confirmar si se exige al ofertar o al contratar")
    for r in adm.get("otros_registros") or []:
        tarea(f"Registro: {r['texto']}", cierre, "cierre", _fuente(r))
    if adm.get("experiencia_minima"):
        tarea("Acreditar experiencia mínima", cierre, "cierre", _fuente(adm["experiencia_minima"]))
    if adm.get("capacidad_economica"):
        tarea("Acreditar capacidad económica", cierre, "cierre", _fuente(adm["capacidad_economica"]))
    if gar.get("monto_o_porcentaje"):
        tarea("Garantía de seriedad de la oferta", cierre, "cierre", _fuente(gar["monto_o_porcentaje"]),
              "si se entrega en papel, revisar en las bases el lugar y la hora límite")
    for d in adm.get("documentos_obligatorios") or []:
        tarea(f"Documento: {d['texto']}", cierre, "cierre", _fuente(d))
    if cierre:
        tarea("Ingresar la oferta en Mercado Público", cierre, "cierre", api)
    return tareas


# --- Ficha ----------------------------------------------------------------------------------------

def generar(lic, metas_pdf, ajustes, perfil, cliente, mp, sb_bases, gasto_por_modelo, ahora, pdfs_locales=None):
    """Arma la ficha de una licitación. Nunca lanza por un problema de esta licitación (queda en la ficha);
    sí propaga TopeGasto / TopeCorrida / LimiteSolicitudes para que la corrida se detenga."""
    from .bases import descargar
    from .detalle import sanitizar
    cfg = ajustes["fichas"]
    zona = ZoneInfo(ajustes["horario"]["zona"])
    hoy = ahora.date()
    feriados = {date.fromisoformat(str(f)) for f in cfg.get("feriados") or []}
    codigo = lic["codigo_externo"]
    cuenta = {"llamadas": 0, "costo_usd": 0.0, "tokens": {"entrada": 0, "salida": 0, "cache_lectura": 0, "cache_escritura": 0}}
    monto_api = lic.get("monto_estimado")
    modelo = cfg["modelo_grande"] if monto_api and monto_api >= float(cfg["monto_modelo_grande_clp"]) else cfg["modelo"]
    ficha = {"codigo_externo": codigo, "generado_en": ahora.isoformat(timespec="seconds"), "aviso": AVISO,
             "estado": "lista", "errores": [], "modelo": modelo, "bases_ids": sorted(m["id"] for m in metas_pdf),
             "url_ficha_oficial": lic.get("url_ficha"), "documentos": [], "extraccion": None, "calculos": None,
             "partes": 0, "checklist": [], "recomendacion": None, "datos_descartados_por_cita": []}

    # 1. Datos oficiales de la API (fechas completas). Si la API falla, se sigue con lo de Supabase.
    det = None
    if mp is not None:
        try:
            crudo = mp.detalle(codigo)
            det = sanitizar(crudo)[0] if crudo else None
        except LimiteSolicitudes:
            raise
        except ErrorAPI as e:
            ficha["errores"].append(f"API de Mercado Público: {str(e)[:200]}")
    fechas = fechas_api(det, lic, zona)
    ficha["datos"] = {
        "codigo": codigo, "nombre": lic.get("nombre"), "organismo": lic.get("organismo"), "region": lic.get("region"),
        "comuna": lic.get("comuna"), "tipo_licitacion": lic.get("tipo"), "monto_estimado_clp": monto_api,
        "tipo_de_obra": lic.get("tipo_de_obra"), "puntaje": lic.get("puntaje"),
        "recomendacion_evaluacion": lic.get("recomendacion"), "fechas": fechas,
    }

    # 2. PDF
    textos, docs = {}, []
    fuentes = pdfs_locales if pdfs_locales is not None else metas_pdf
    for n, meta in enumerate(fuentes, 1):
        nombre = meta.get("nombre_archivo") or meta.get("ruta") or f"documento {n}"
        try:
            if (meta.get("bytes") or 0) > float(cfg["max_mb"]) * 1024 * 1024:
                raise ValueError(f"pesa más de {cfg['max_mb']} MB: no se descargó")
            if "contenido" in meta:
                contenido = meta["contenido"]
            else:
                if n > 1:
                    time.sleep(float(cfg["pausa_descargas_s"]))
                contenido = descargar(sb_bases, meta["ruta"])
            if len(contenido) > float(cfg["max_mb"]) * 1024 * 1024:
                raise ValueError(f"pesa más de {cfg['max_mb']} MB")
            paginas = leer_pdf(contenido)
            textos[n] = paginas
            docs.append(documento(n, nombre, paginas, cfg))
        except ValueError as e:
            docs.append({"n": n, "nombre": nombre, "paginas": 0, "paginas_sin_texto": [], "escaneado": False, "error": str(e)})
        except Exception as e:  # Storage caído, etc.: queda en la ficha
            docs.append({"n": n, "nombre": nombre, "paginas": 0, "paginas_sin_texto": [], "escaneado": False,
                         "error": f"no se pudo descargar ({type(e).__name__})"})
    ficha["documentos"] = docs
    utiles = [d for d in docs if not d["escaneado"] and not d["error"]]
    if not fuentes:
        ficha["estado"] = "adjuntos_pendientes"
    elif not utiles:
        ficha["estado"] = "escaneado" if any(d["escaneado"] for d in docs) else "error"

    # 3. Extracción por partes
    if utiles:
        paginas = {(n, i): t for n, ps in textos.items() for i, t in enumerate(ps, 1)}
        gasto = gasto_por_modelo(modelo)
        textos_partes = partes(docs, textos, int(cfg["max_caracteres_por_parte"]))
        ficha["partes"] = len(textos_partes)
        extracciones = []
        for i, texto_parte in enumerate(textos_partes, 1):
            try:
                datos, malas = extraer_parte(cliente, cfg, modelo, gasto, texto_parte, paginas, cuenta)
            except ErrorClaude as e:
                datos, malas = None, str(e)
            if datos is None:
                ficha["errores"].append(f"parte {i}: {malas}")
                continue
            if malas:
                ficha["datos_descartados_por_cita"] += depurar(datos, malas)
            extracciones.append(datos)
        if extracciones:
            ficha["extraccion"] = combinar(extracciones)
        if len(extracciones) < len(textos_partes) or ficha["datos_descartados_por_cita"]:
            ficha["estado"] = "revision_manual"
        if any(d["escaneado"] or d["error"] for d in docs) and ficha["estado"] == "lista":
            ficha["estado"] = "revision_manual"

    # 4. Cálculos y checklist (código)
    ficha["calculos"] = calcular(ficha["extraccion"], fechas, monto_api, hoy, feriados, cfg["dias_habiles_alerta"])
    ficha["checklist"] = checklist(ficha["extraccion"], fechas, ficha["calculos"])

    # 5. Recomendación (solo con bases leídas)
    if ficha["extraccion"] is not None:
        resumen = {"datos": ficha["datos"], "calculos": ficha["calculos"], "extraccion": ficha["extraccion"],
                   "documentos_no_leidos": [d["nombre"] for d in docs if d["escaneado"] or d["error"]]}
        try:
            rec, error = recomendar(cliente, cfg, modelo, gasto_por_modelo(modelo), perfil, resumen, cuenta)
        except ErrorClaude as e:
            rec, error = None, str(e)
        ficha["recomendacion"] = rec
        if error:
            ficha["errores"].append(f"recomendación: {error}")
            ficha["estado"] = "revision_manual"
    ficha["costo"] = cuenta
    return ficha


# --- Markdown -------------------------------------------------------------------------------------

def _f(iso):
    return datetime.fromisoformat(iso).strftime("%d-%m-%Y %H:%M") if iso else "—"


def _m(v):
    return "—" if v is None else "$" + f"{float(v):,.0f}".replace(",", ".")


def _d(dato):
    if not dato:
        return "**No aparece en las bases.**"
    return f"{dato['texto']} — _doc. {dato['documento']}, pág. {dato['pagina']}: «{dato['cita']}»_"


def markdown(ficha):
    d, c, e = ficha["datos"], ficha["calculos"] or {}, ficha["extraccion"] or {}
    fechas, dias = d["fechas"], c.get("dias") or {}
    L = [f"# Ficha de postulación · {d['codigo']}", "", f"**{d['nombre'] or ''}**", "",
         f"> ⚠️ **{AVISO}.** Montos, plazos y garantías son datos críticos: verificarlos en el PDF antes de postular.", ""]
    if c.get("alerta_cierre"):
        L += [f"> 🔴 **CIERRA EN {c['dias_habiles_cierre']} DÍAS HÁBILES** ({_f(fechas.get('cierre'))}).", ""]
    estados = {"lista": "lista", "revision_manual": "**REVISIÓN MANUAL**",
               "adjuntos_pendientes": "**ADJUNTOS PENDIENTES**: subir las bases en licitaciones.html",
               "escaneado": "**PDF ESCANEADO** (sin texto; esta versión no hace OCR)", "error": "**ERROR**"}
    L += [f"Estado: {estados.get(ficha['estado'], ficha['estado'])} · Ficha oficial: {ficha['url_ficha_oficial']}", ""]
    rec = ficha.get("recomendacion")
    if rec:
        L += [f"## Recomendación: {rec['decision'].upper()}", ""] + [f"{i}. {r}" for i, r in enumerate(rec["razones"], 1)] + [""]

    L += ["## Datos clave", "", "| Dato | Valor |", "|---|---|",
          f"| Organismo | {d['organismo'] or '—'} |", f"| Región | {d['region'] or '—'} |",
          f"| Tipo de obra | {(e.get('tipo_de_obra') or {}).get('texto') or d['tipo_de_obra'] or '—'} |",
          f"| Monto estimado (API) | {_m(d['monto_estimado_clp'])} |",
          f"| Presupuesto oficial (bases) | {(e.get('presupuesto_oficial') or {}).get('texto') or '—'} |",
          f"| Puntaje evaluación | {d['puntaje'] or '—'} ({d['recomendacion_evaluacion'] or '—'}) |", ""]
    L += ["## Fechas (API Mercado Público)", "", "| Hito | Fecha | Días corridos | Días hábiles |", "|---|---|---|---|"]
    for clave, nombre in (("publicacion", "Publicación"), ("fin_consultas", "Fin de consultas"), ("respuestas", "Respuestas"),
                          ("visita_terreno", "Visita a terreno"), ("cierre", "Cierre"), ("adjudicacion", "Adjudicación")):
        x = dias.get(clave) or {}
        L.append(f"| {nombre} | {_f(fechas.get(clave))} | {x.get('corridos', '—')} | {x.get('habiles', '—')} |")
    L.append("")

    if ficha["documentos"]:
        L += ["## Documentos leídos", ""]
        for doc in ficha["documentos"]:
            estado = doc["error"] or ("escaneado, sin texto" if doc["escaneado"] else
                                      f"{doc['paginas']} págs." + (f", sin texto: {doc['paginas_sin_texto']}" if doc["paginas_sin_texto"] else ""))
            L.append(f"{doc['n']}. {doc['nombre']} — {estado}")
        L.append("")

    if e:
        adm = e["admisibilidad"]
        L += ["## Requisitos de admisibilidad", "",
              f"- **Registro de Proveedores:** {_d(adm['registro_proveedores'])}",
              f"- **Experiencia mínima:** {_d(adm['experiencia_minima'])}",
              f"- **Capacidad económica:** {_d(adm['capacidad_economica'])}",
              f"- **Visita a terreno:** {_d(adm['visita_terreno_obligatoria'] or e['fechas']['visita_terreno'])}"]
        for r in adm["otros_registros"]:
            L.append(f"- **Registro:** {_d(r)}")
        L += ["", "**Documentos obligatorios**", ""] + ([f"- {_d(x)}" for x in adm["documentos_obligatorios"]] or ["- No aparecen en las bases."]) + [""]

        L += [f"## Garantías ({AVISO.lower()})", ""]
        for clave, nombre in (("seriedad_oferta", "Seriedad de la oferta"), ("fiel_cumplimiento", "Fiel cumplimiento")):
            g, cg = e["garantias"][clave], c["garantias"][clave]
            calculo = []
            if cg["porcentaje"] is not None:
                calculo.append(f"{cg['porcentaje']:g}%")
            if cg["monto_clp"] is not None:
                calculo.append(_m(cg["monto_clp"]))
            if cg["monto_uf"] is not None:
                calculo.append(f"UF {cg['monto_uf']:g}")
            if cg["monto_referencial_clp"] is not None:
                calculo.append(f"≈ {_m(cg['monto_referencial_clp'])} sobre el {cg['base_referencial']} (referencial)")
            L += [f"**{nombre}**", f"- Monto: {_d(g['monto_o_porcentaje'])}" + (f" → calculado: {', '.join(calculo)}" if calculo else ""),
                  f"- Vigencia: {_d(g['vigencia'])}", f"- Formatos: {_d(g['formatos'])}", ""]

        L += ["## Criterios de evaluación", ""]
        if e["criterios_evaluacion"]:
            L += ["| Criterio | Ponderación | Fuente |", "|---|---|---|"]
            L += [f"| {x['criterio']} | {x['ponderacion'] or '—'} | doc. {x['documento']}, pág. {x['pagina']}: «{x['cita']}» |"
                  for x in e["criterios_evaluacion"]]
            if c.get("aviso_ponderaciones"):
                L.append(f"\n⚠️ {c['aviso_ponderaciones']}.")
        else:
            L.append("No aparecen en las bases.")
        L.append("")

        k = e["contrato"]
        pe = c.get("plazo_ejecucion")
        L += [f"## Contrato ({AVISO.lower()})", "",
              f"- **Plazo de ejecución:** {_d(k['plazo_ejecucion'])}" +
              (f" → {pe['cantidad']} {pe['unidad']} {pe['tipo'] or ''}".rstrip() if pe else ""),
              f"- **Multas:** {_d(k['multas'])}", f"- **Retenciones:** {_d(k['retenciones'])}",
              f"- **Forma de pago:** {_d(k['forma_pago'])}", f"- **Reajustes:** {_d(k['reajustes'])}", ""]
        L += ["## Riesgos y cláusulas inusuales", ""] + ([f"- {_d(x)}" for x in e["riesgos"]] or ["- Ninguno marcado."]) + [""]

    L += ["## Checklist de postulación", "", "| | Tarea | Fecha límite | Días hábiles | Fuente |", "|---|---|---|---|---|"]
    for t in ficha["checklist"]:
        fuente = t["fuente"] if isinstance(t["fuente"], str) else f"doc. {t['fuente']['documento']}, pág. {t['fuente']['pagina']}: «{t['fuente']['cita']}»"
        nota = f" ({t['nota']})" if t["nota"] else ""
        L.append(f"| ☐ | {t['tarea']}{nota} | {_f(t['fecha_limite'])} | {(t['dias'] or {}).get('habiles', '—')} | {fuente} |")
    L.append("")
    if ficha["datos_descartados_por_cita"]:
        L += ["## Revisar a mano: datos descartados", "",
              "La cita que dio el modelo no aparece en la página indicada; no se usaron en la ficha.", ""]
        L += [f"- `{x['campo']}`: {x['texto']} (doc. {x['documento']}, pág. {x['pagina']})" for x in ficha["datos_descartados_por_cita"]]
        L.append("")
    if ficha["errores"]:
        L += ["## Errores", ""] + [f"- {x}" for x in ficha["errores"]] + [""]
    co = ficha.get("costo") or {}
    L.append(f"_Generada {_f(ficha['generado_en'])} con {ficha['modelo']} · {co.get('llamadas', 0)} llamadas · "
             f"US$ {co.get('costo_usd', 0):.4f}_")
    return "\n".join(L) + "\n"


# --- Guardar ----------------------------------------------------------------------------------------

def fila(ficha, md):
    rec = ficha.get("recomendacion") or {}
    calc = ficha.get("calculos") or {}
    return {"codigo_externo": ficha["codigo_externo"], "estado": ficha["estado"], "recomendacion": rec.get("decision"),
            "razones": rec.get("razones") or [], "fecha_cierre": ficha["datos"]["fechas"].get("cierre"),
            "dias_habiles_cierre": calc.get("dias_habiles_cierre"), "alerta_cierre": bool(calc.get("alerta_cierre")),
            "bases_ids": ficha["bases_ids"], "ficha": ficha, "ficha_md": md, "modelo": ficha["modelo"],
            "tokens": ficha["costo"]["tokens"], "costo_usd": ficha["costo"]["costo_usd"],
            "error": "; ".join(ficha["errores"])[:500] or None, "generado_en": ficha["generado_en"]}


def _registrar_costo(ficha):
    CARPETA.mkdir(parents=True, exist_ok=True)
    co = ficha["costo"]
    with open(CARPETA / "costos.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"fecha": ficha["generado_en"], "codigo": ficha["codigo_externo"], "estado": ficha["estado"],
                            "modelo": ficha["modelo"], "llamadas": co["llamadas"], "tokens": co["tokens"],
                            "costo_usd": co["costo_usd"]}, ensure_ascii=False) + "\n")


def para_reporte(generadas, cfg):
    """Filas de la sección "Licitaciones con ficha nueva" del reporte (salida/AAAA-MM-DD/fichas_nuevas.json)."""
    return [{"codigo": f["codigo_externo"], "organismo": f["datos"]["organismo"], "cierre": f["datos"]["fechas"]["cierre"],
             "recomendacion": (f["recomendacion"] or {}).get("decision"), "estado": f["estado"],
             "alerta_cierre": f["calculos"]["alerta_cierre"], "dias_habiles_cierre": f["calculos"]["dias_habiles_cierre"],
             "url": cfg["url_ficha"].format(f["codigo_externo"])} for f, _ in generadas]


def guardar_local(ficha, md):
    from .descarga import escribir_json
    carpeta = CARPETA / ficha["codigo_externo"]
    escribir_json(carpeta / "ficha.json", ficha)
    (carpeta / "ficha.md").write_text(md, encoding="utf-8")
    _registrar_costo(ficha)


# --- Corrida -----------------------------------------------------------------------------------------

def procesar(ajustes, perfil, maximo=None, codigo=None, dry_run=False, pdfs_locales=None, cliente=None, mp=None,
             sb_lic=None, sb_bases=None, sb_fichas=None, ahora=None):
    """Genera las fichas pendientes. Devuelve (resumen solo con cifras, [(ficha, markdown)]).
    dry_run: una sola licitación, imprime la ficha y no guarda nada (ni Supabase, ni archivos, ni gasto)."""
    from .bases import TABLA_BASES
    from .evaluacion import cliente_claude
    from .supabase_mp import Supabase, TABLA as TABLA_LIC

    cfg = ajustes["fichas"]
    zona = ZoneInfo(ajustes["horario"]["zona"])
    ahora = ahora or datetime.now(zona)
    resumen = {"candidatas": 0, "generadas": 0, "por_estado": {}, "alerta_cierre": 0, "errores": 0,
               "costo_usd": 0.0, "interrumpida": None}
    if not cfg.get("activo", True) and not dry_run and not codigo:
        log.info("Fichas: desactivadas en ajustes.yaml")
        return resumen, []
    sb_lic = sb_lic or Supabase(ajustes, tabla=TABLA_LIC)
    sb_bases = sb_bases or Supabase(ajustes, tabla=TABLA_BASES)
    sb_fichas = sb_fichas or (None if dry_run else Supabase(ajustes, tabla=TABLA))

    if codigo:
        lic = sb_lic._pedir("GET", params=[("select", "*"), ("codigo_externo", f"eq.{codigo}")]).json()
        lic = lic[0] if lic else {"codigo_externo": codigo, "url_ficha": None}
        metas = [] if pdfs_locales is not None else sb_bases._pedir("GET", params=[
            ("select", "id,codigo_externo,ruta,nombre_archivo,bytes"), ("codigo_externo", f"eq.{codigo}"), ("order", "id")]).json()
        lista = [(lic, metas)]
    else:
        lista = candidatas(cfg, sb_lic, sb_bases, sb_fichas or _SinFichas(), ahora)
        if dry_run:
            lista = [x for x in lista if x[1]][:1] or lista[:1]
    if maximo is not None:
        lista = lista[:maximo]
    resumen["candidatas"] = len(lista)
    if not lista:
        log.info("Fichas: no hay licitaciones que necesiten ficha")
        return resumen, []

    if mp is None:
        from .mp_api import MercadoPublico
        mp = MercadoPublico(ajustes)
    if cliente is None and any(m or pdfs_locales for _, m in lista):
        cliente = cliente_claude(ajustes)
    gastos, corrida = {}, {"usd": 0.0}

    def gasto_por_modelo(modelo):
        if modelo not in gastos:
            gastos[modelo] = Gasto(ajustes, modelo, cfg["tope_por_corrida_usd"], corrida, guardar=not dry_run, zona=zona)
        return gastos[modelo]

    fichas = []
    for lic, metas in lista:
        try:
            ficha = generar(lic, metas, ajustes, perfil, cliente, mp, sb_bases, gasto_por_modelo, ahora,
                            pdfs_locales=pdfs_locales)
        except (TopeGasto, LimiteSolicitudes) as e:
            resumen["interrumpida"] = str(e)
            log.warning("Fichas: se detiene la corrida (%s). Lo que falta queda para la próxima.", type(e).__name__)
            break
        except Exception as e:  # un fallo inesperado en una licitación no detiene las demás
            resumen["errores"] += 1
            log.error("Fichas: error inesperado en una licitación (%s): %s", type(e).__name__, enmascarar(str(e))[:200])
            continue
        md = markdown(ficha)
        fichas.append((ficha, md))
        resumen["generadas"] += 1
        resumen["por_estado"][ficha["estado"]] = resumen["por_estado"].get(ficha["estado"], 0) + 1
        resumen["alerta_cierre"] += int(bool(ficha["calculos"]["alerta_cierre"]))
        resumen["costo_usd"] = round(resumen["costo_usd"] + ficha["costo"]["costo_usd"], 6)
        if dry_run:
            continue
        try:
            guardar_local(ficha, md)
            sb_fichas.upsert([fila(ficha, md)])
        except Exception as e:
            resumen["errores"] += 1
            log.error("Fichas: no se pudo guardar una ficha (%s): %s", type(e).__name__, enmascarar(str(e))[:200])
    log.info("Fichas: %d candidatas, %d generadas %s, %d con cierre en menos de %s días hábiles, %d errores, US$ %.4f%s",
             resumen["candidatas"], resumen["generadas"], resumen["por_estado"], resumen["alerta_cierre"],
             cfg["dias_habiles_alerta"], resumen["errores"], resumen["costo_usd"],
             " (interrumpida por tope)" if resumen["interrumpida"] else "")
    return resumen, fichas


class _SinFichas:
    """En --dry-run no se consulta la tabla de fichas: todas las candidatas cuentan como nuevas."""
    def _pedir(self, *a, **k):
        from types import SimpleNamespace
        return SimpleNamespace(json=lambda: [])
