"""Etapa 2: puntuación de las licitaciones filtradas con Claude.

- Una llamada por licitación con el perfil de M5 y un resumen del detalle (sin datos de funcionarios).
- Respuesta con esquema fijo (`ESQUEMA`, pedido a la API con output_config.format) y validada en local
  con `Evaluacion`. Además se verifica que el monto y la fecha de cierre sean los publicados o null:
  un valor que no está en los datos se trata como inventado. Si falla, se reintenta una vez
  indicando el error; si vuelve a fallar, la licitación queda "revisar_manualmente".
- Antes de cada llamada se verifica que el peor caso (entrada estimada + max_tokens) no supere el
  tope diario de gasto; el gasto real del día queda en estado/gasto_claude_AAAAMMDD.json.
"""
import json
import logging
from datetime import datetime
from typing import Literal, Optional

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from .config import ESTADO, enmascarar, secreto
from .errores import ErrorClaude, ErrorConfig, TopeGasto

log = logging.getLogger("licitaciones.evaluacion")

RECOMENDACIONES = ("postular", "revisar", "descartar")
_NULO = {"type": "null"}

# Esquema que se pide a la API. Las restricciones que la salida estructurada no admite
# (largo, rango) las revisa `Evaluacion`.
ESQUEMA = {
    "type": "object",
    "properties": {
        "puntaje": {"type": "integer", "enum": [1, 2, 3, 4, 5],
                    "description": "5 = calza claramente con el perfil; 1 = fuera del perfil"},
        "motivo": {"type": "string", "description": "una línea, máximo 200 caracteres"},
        "tipo_de_obra": {"anyOf": [{"type": "string"}, _NULO]},
        "monto_estimado_clp": {"anyOf": [{"type": "integer"}, _NULO],
                               "description": "monto_publicado_clp tal cual, o null"},
        "fecha_cierre": {"anyOf": [{"type": "string"}, _NULO],
                         "description": "fecha_cierre tal cual (ISO 8601), o null"},
        "requisitos_clave": {"type": "array", "items": {"type": "string"}},
        "riesgos": {"type": "array", "items": {"type": "string"}},
        "recomendacion": {"type": "string", "enum": list(RECOMENDACIONES)},
    },
    "required": ["puntaje", "motivo", "tipo_de_obra", "monto_estimado_clp", "fecha_cierre",
                 "requisitos_clave", "riesgos", "recomendacion"],
    "additionalProperties": False,
}


class Evaluacion(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    puntaje: int = Field(ge=1, le=5)
    motivo: str = Field(min_length=1, max_length=300)
    tipo_de_obra: Optional[str]
    monto_estimado_clp: Optional[int] = Field(ge=0)
    fecha_cierre: Optional[str]
    requisitos_clave: list[str]
    riesgos: list[str]
    recomendacion: Literal["postular", "revisar", "descartar"]

    @field_validator("motivo")
    @classmethod
    def _una_linea(cls, v):
        if "\n" in v.strip():
            raise ValueError("el motivo debe ser una sola línea")
        return v.strip()

    @field_validator("fecha_cierre")
    @classmethod
    def _iso(cls, v):
        if v is not None:
            datetime.fromisoformat(v)  # ValueError si no es ISO 8601
        return v


def validar(texto, registro):
    """(dict validado, None) o (None, descripción del error)."""
    try:
        datos = json.loads(texto)
    except (TypeError, ValueError) as e:
        return None, f"no es JSON: {e}"
    try:
        ev = Evaluacion.model_validate(datos)
    except ValidationError as e:
        errores = "; ".join(f"{'.'.join(map(str, x['loc'])) or 'raíz'}: {x['msg']}" for x in e.errors())
        return None, f"no cumple el esquema: {errores}"

    publicado = registro.get("monto_estimado_clp")
    if ev.monto_estimado_clp is not None:
        if publicado is None:
            return None, "monto_estimado_clp debe ser null: la licitación no publica monto (no se estima)"
        if abs(ev.monto_estimado_clp - publicado) > max(1.0, publicado * 0.001):
            return None, f"monto_estimado_clp {ev.monto_estimado_clp} no coincide con el publicado {publicado:.0f}"
    cierre = registro.get("fecha_cierre")
    if ev.fecha_cierre is not None:
        if cierre is None:
            return None, "fecha_cierre debe ser null: la licitación no trae fecha de cierre"
        if datetime.fromisoformat(ev.fecha_cierre).date() != datetime.fromisoformat(cierre).date():
            return None, f"fecha_cierre {ev.fecha_cierre} no coincide con la publicada {cierre}"
    return ev.model_dump(), None


# --- Prompt -------------------------------------------------------------------

INSTRUCCIONES = """Eres analista de licitaciones de M5 Industrial, constructora del Grupo SHG (Chile). Evalúas licitaciones de Mercado Público contra el perfil de la empresa y respondes solo con el JSON del esquema.

Solo tienes la ficha resumida que entrega la API: nombre, descripción (máximo 500 caracteres), organismo, región, monto si el organismo lo publicó, fechas e ítems. Las bases administrativas y técnicas no vienen incluidas: no supongas su contenido.

Criterios:
- puntaje de 1 a 5: 5 = calza claramente con el perfil y conviene postular; 3 = podría calzar pero falta información; 1 = fuera del perfil.
- recomendacion: "postular" si calza y no hay nada conocido en contra; "revisar" si falta información clave o hay dudas; "descartar" si está fuera del perfil.
- motivo: una sola línea, máximo 200 caracteres, con la razón principal.
- tipo_de_obra: frase corta (por ejemplo "edificación pública", "pavimentación", "mantención de edificio") según nombre, descripción e ítems; null si no se puede saber.
- monto_estimado_clp: copia monto_publicado_clp como número entero. Si es null, responde null. No lo estimes a partir del tipo de licitación ni de ningún otro dato.
- fecha_cierre: copia fecha_cierre tal cual. Si es null, responde null.
- requisitos_clave: solo los que aparecen explícitamente en los datos (visita a terreno, registros, experiencia, garantías...). Lista vacía si no aparece ninguno.
- riesgos: lo que juega en contra o falta verificar (cierre cercano, región o monto fuera del perfil, bases no revisadas...).
- Si un dato no está, usa null o una lista vacía. Nunca inventes montos, fechas, requisitos ni nombres."""


def sistema(perfil):
    texto_perfil = yaml.safe_dump(perfil, allow_unicode=True, sort_keys=True)
    return [
        {"type": "text", "text": INSTRUCCIONES},
        {"type": "text", "text": "Perfil de M5 Industrial (YAML):\n" + texto_perfil,
         "cache_control": {"type": "ephemeral"}},
    ]


def datos_para_modelo(registro):
    """Lo que ve el modelo: solo datos de la licitación, nunca de funcionarios."""
    det = registro.get("detalle") or {}
    fechas = det.get("Fechas") or {}
    items = (det.get("Items") or {}).get("Listado") or []
    return {
        "codigo": registro["codigo_externo"],
        "nombre": registro.get("nombre"),
        "descripcion": det.get("Descripcion"),
        "organismo": registro.get("organismo"),
        "organismo_prioritario": registro.get("organismo_prioritario"),
        "region": registro.get("region"),
        "comuna": registro.get("comuna"),
        "tipo_licitacion": registro.get("tipo"),
        "monto_publicado_clp": registro.get("monto_estimado_clp"),
        "fuente_financiamiento": (det.get("FuenteFinanciamiento") or "").strip() or None,
        "fecha_publicacion": registro.get("fecha_publicacion"),
        "fecha_cierre": registro.get("fecha_cierre"),
        "fecha_visita_terreno": _fecha_api(fechas.get("FechaVisitaTerreno")),
        "items": [{"categoria": i.get("Categoria"), "producto": i.get("NombreProducto"),
                   "descripcion": i.get("Descripcion"), "cantidad": i.get("Cantidad"),
                   "unidad": i.get("UnidadMedida")} for i in items],
        "coincidencias_del_filtro": registro.get("coincidencias"),
    }


def _fecha_api(valor):
    return None if not valor or str(valor).startswith("1900") else str(valor)


# --- Gasto --------------------------------------------------------------------

class Presupuesto:
    """Gasto del día (hora de Chile) en Claude, con tope. Persistido en estado/gasto_claude_AAAAMMDD.json."""

    def __init__(self, ajustes, zona, carpeta=ESTADO):
        ev = ajustes["evaluacion"]
        self.modelo = ev["modelo"]
        precios = (ev.get("precios_usd_por_mtok") or {}).get(self.modelo)
        if not precios:
            raise ErrorConfig(f"ajustes.yaml no tiene precios para el modelo {self.modelo}: sin ellos no se "
                              "puede controlar el tope de gasto. Agregarlo en evaluacion.precios_usd_por_mtok.")
        self.precios = {k: float(v) / 1_000_000 for k, v in precios.items()}
        self.tope = float(ev["tope_gasto_diario_usd"])
        self.zona = zona
        self.carpeta = carpeta

    def _archivo(self):
        return self.carpeta / f"gasto_claude_{datetime.now(self.zona):%Y%m%d}.json"

    def leer(self):
        try:
            return float(json.loads(self._archivo().read_text(encoding="utf-8"))["usd"])
        except (FileNotFoundError, KeyError, ValueError):
            return 0.0

    def costo(self, usage):
        g = lambda campo: getattr(usage, campo, None) or 0
        return (g("input_tokens") * self.precios["entrada"] + g("output_tokens") * self.precios["salida"]
                + g("cache_read_input_tokens") * self.precios.get("cache_lectura", self.precios["entrada"])
                + g("cache_creation_input_tokens") * self.precios.get("cache_escritura", self.precios["entrada"]))

    def peor_caso(self, caracteres_entrada, max_tokens):
        # ~2,5 caracteres por token sobreestima a propósito (el español ronda 3,5-4).
        return caracteres_entrada / 2.5 * self.precios["entrada"] + max_tokens * self.precios["salida"]

    def verificar(self, estimado):
        gastado = self.leer()
        if gastado + estimado > self.tope:
            raise TopeGasto(f"Tope diario de gasto en Claude: US$ {self.tope:.2f}. Gastado hoy US$ {gastado:.4f}; "
                            f"la siguiente llamada podría costar hasta US$ {estimado:.4f}. Se detiene la evaluación.")

    def registrar(self, usd):
        self.carpeta.mkdir(parents=True, exist_ok=True)
        self._archivo().write_text(json.dumps({"usd": round(self.leer() + usd, 6)}), encoding="utf-8")


# --- Llamada ------------------------------------------------------------------

def cliente_claude(ajustes):
    import anthropic
    ev = ajustes["evaluacion"]
    # La clave se pasa explícita: solo vale la variable de entorno, no perfiles guardados en el equipo.
    return anthropic.Anthropic(api_key=secreto("ANTHROPIC_API_KEY"), max_retries=int(ev["reintentos_sdk"]),
                               timeout=float(ev["timeout_s"]))


def evaluar_una(cliente, registro, perfil, ajustes, presupuesto):
    """Evalúa una licitación. Devuelve el resultado con estado 'ok' o 'revisar_manualmente'."""
    import anthropic
    ev = ajustes["evaluacion"]
    system = sistema(perfil)
    entrada = json.dumps(datos_para_modelo(registro), ensure_ascii=False)
    resultado = {"codigo_externo": registro["codigo_externo"], "estado": "revisar_manualmente",
                 "evaluacion": None, "error": None, "intentos": 0, "costo_usd": 0.0,
                 "tokens": {"entrada": 0, "salida": 0, "cache_lectura": 0, "cache_escritura": 0},
                 "request_ids": []}
    error_previo = None
    for intento in (1, 2):
        contenido = "Licitación a evaluar (JSON):\n" + entrada
        if error_previo:
            contenido += f"\n\nTu respuesta anterior no pasó la validación: {error_previo}. Corrígela."
        presupuesto.verificar(presupuesto.peor_caso(sum(len(b["text"]) for b in system) + len(contenido),
                                                    int(ev["max_tokens"])))
        try:
            r = cliente.messages.create(
                model=ev["modelo"], max_tokens=int(ev["max_tokens"]), system=system,
                messages=[{"role": "user", "content": contenido}],
                output_config={"effort": ev["esfuerzo"], "format": {"type": "json_schema", "schema": ESQUEMA}},
            )
        except anthropic.APIError as e:
            raise ErrorClaude(f"API de Claude ({type(e).__name__}) en {registro['codigo_externo']}: "
                              f"{enmascarar(str(e))[:300]}") from None
        resultado["intentos"] = intento
        resultado["request_ids"].append(getattr(r, "_request_id", None))
        usd = presupuesto.costo(r.usage)
        presupuesto.registrar(usd)
        resultado["costo_usd"] = round(resultado["costo_usd"] + usd, 6)
        for clave, campo in (("entrada", "input_tokens"), ("salida", "output_tokens"),
                             ("cache_lectura", "cache_read_input_tokens"), ("cache_escritura", "cache_creation_input_tokens")):
            resultado["tokens"][clave] += getattr(r.usage, campo, None) or 0

        if r.stop_reason == "refusal":
            resultado["error"] = "el modelo rechazó la solicitud (stop_reason refusal)"
            return resultado  # repetir la misma solicitud daría lo mismo
        if r.stop_reason == "max_tokens":
            error_previo = "la respuesta se cortó por max_tokens"
            continue
        texto = next((b.text for b in r.content if getattr(b, "type", None) == "text"), None)
        datos, error_previo = validar(texto, registro)
        if datos:
            resultado.update(estado="ok", evaluacion=datos, error=None)
            return resultado
        log.warning("%s intento %d: %s", registro["codigo_externo"], intento, error_previo)
    resultado["error"] = error_previo
    return resultado


# --- Corrida ------------------------------------------------------------------

def separar(resultados, ajustes):
    """(conservadas, descartadas). Se conservan las recomendaciones de `evaluacion.conservar` y siempre
    las que quedaron para revisión manual (sin una evaluación válida no hay cómo descartarlas)."""
    conservar = set(ajustes["evaluacion"].get("conservar") or ("postular", "revisar"))
    conservadas, descartadas = [], []
    for r in resultados:
        e = r.get("evaluacion")
        if e is None or e["recomendacion"] in conservar:
            conservadas.append(r)
        else:
            descartadas.append(r)
    return conservadas, descartadas


def ejecutar(ajustes, perfil, carpeta, max_n=None, cliente=None, zona=None):
    """Evalúa salida/AAAA-MM-DD/filtradas.json. Escribe evaluadas.json (solo las conservadas: postular,
    revisar y revisión manual), descartadas_claude.json, costo.json y evaluacion.md."""
    from zoneinfo import ZoneInfo
    from .descarga import escribir_json, leer_json
    from .errores import ErrorEvaluacion

    ruta = carpeta / "filtradas.json"
    if not ruta.is_file():
        raise ErrorConfig(f"No existe {ruta.parent.name}/filtradas.json: correr primero `descargar`.")
    registros = leer_json(ruta, [])
    if max_n is not None:
        registros = registros[:max_n]
    zona = zona or ZoneInfo(ajustes["horario"]["zona"])
    presupuesto = Presupuesto(ajustes, zona)
    ev = ajustes["evaluacion"]
    if registros and cliente is None:
        cliente = cliente_claude(ajustes)

    resultados, interrupcion, gasto_inicial = [], None, presupuesto.leer()
    try:
        for i, reg in enumerate(registros, 1):
            res = evaluar_una(cliente, reg, perfil, ajustes, presupuesto)
            resultados.append({**{k: reg.get(k) for k in ("codigo_externo", "nombre", "organismo", "region",
                                                          "fecha_cierre", "monto_estimado_clp", "url_ficha",
                                                          "organismo_prioritario")}, **res})
            log.debug("Evaluada %d/%d %s: %s%s", i, len(registros), reg["codigo_externo"], res["estado"],
                     f" · puntaje {res['evaluacion']['puntaje']} {res['evaluacion']['recomendacion']}"
                     if res["evaluacion"] else f" · {res['error']}")
    except (ErrorClaude, TopeGasto) as e:
        interrupcion = str(e)
        raise
    finally:
        tok = {k: sum(r["tokens"][k] for r in resultados) for k in ("entrada", "salida", "cache_lectura", "cache_escritura")}
        conservadas, descartadas = separar(resultados, ajustes)
        costo = {
            "modelo": ev["modelo"], "esfuerzo": ev["esfuerzo"],
            "licitaciones": len(registros), "evaluadas": len(resultados),
            "ok": sum(r["estado"] == "ok" for r in resultados),
            "revisar_manualmente": sum(r["estado"] != "ok" for r in resultados),
            "conservadas": len(conservadas),
            "descartadas_por_claude": len(descartadas),
            "llamadas": sum(r["intentos"] for r in resultados),
            "tokens": tok,
            "costo_usd_corrida": round(sum(r["costo_usd"] for r in resultados), 6),
            "gasto_usd_hoy": round(presupuesto.leer(), 6),
            "gasto_usd_hoy_antes_de_la_corrida": round(gasto_inicial, 6),
            "tope_gasto_diario_usd": presupuesto.tope,
            "interrumpida": interrupcion,
        }
        escribir_json(carpeta / "evaluadas.json", conservadas)
        escribir_json(carpeta / "descartadas_claude.json", descartadas)
        escribir_json(carpeta / "costo.json", costo)
        (carpeta / "evaluacion.md").write_text(tabla(conservadas), encoding="utf-8")
        log.info("Evaluación: %d de %d (%d ok, %d a revisar a mano) · conservadas %d, descartadas por Claude %d · "
                 "%d llamadas · tokens %s · US$ %.4f (hoy US$ %.4f de tope %.2f)", len(resultados), len(registros),
                 costo["ok"], costo["revisar_manualmente"], len(conservadas), len(descartadas), costo["llamadas"],
                 tok, costo["costo_usd_corrida"], costo["gasto_usd_hoy"], presupuesto.tope)

    malas = sum(r["estado"] != "ok" and r["error"] and "refusal" not in r["error"] for r in resultados)
    if malas > int(ev["max_revision_manual_por_json"]):
        raise ErrorEvaluacion(f"{malas} respuestas no pasaron la validación del esquema "
                              f"(máximo {ev['max_revision_manual_por_json']}). Ver evaluadas.json.")
    return costo, conservadas


def _celda(valor, largo=None):
    texto = "—" if valor in (None, "", []) else str(valor)
    texto = texto.replace("|", "/").replace("\n", " ")
    return texto[:largo - 1] + "…" if largo and len(texto) > largo else texto


def _monto(v):
    return "—" if v is None else f"${v:,.0f}".replace(",", ".")


def tabla(resultados):
    """Tabla Markdown ordenada por puntaje, para calibrar el perfil."""
    def orden(r):
        e = r["evaluacion"] or {}
        return (-(e.get("puntaje") or 0), r.get("fecha_cierre") or "9999")
    filas = ["| Pje | Recomendación | Código | Nombre | Tipo de obra | Monto | Cierre | Motivo |",
             "|---|---|---|---|---|---|---|---|"]
    for r in sorted(resultados, key=orden):
        e = r["evaluacion"]
        if e:
            filas.append(f"| {e['puntaje']} | {e['recomendacion']} | [{r['codigo_externo']}]({r['url_ficha']}) | "
                         f"{_celda(r['nombre'], 50)} | {_celda(e['tipo_de_obra'], 30)} | {_monto(e['monto_estimado_clp'])} | "
                         f"{_celda((e['fecha_cierre'] or '')[:10])} | {_celda(e['motivo'], 120)} |")
        else:
            filas.append(f"| — | **revisar a mano** | [{r['codigo_externo']}]({r['url_ficha']}) | {_celda(r['nombre'], 50)} "
                         f"| — | {_monto(r.get('monto_estimado_clp'))} | {_celda((r.get('fecha_cierre') or '')[:10])} "
                         f"| {_celda(r['error'], 120)} |")
    return "\n".join(filas) + "\n"
