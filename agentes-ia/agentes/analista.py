"""Agentes analistas: Claude con una sola herramienta, consultar_sql (solo lectura)."""
import json

from . import perfiles, supabase

MODELO = "claude-opus-5-5"
ESFUERZO = "medium"
MAX_TURNOS = 20
MAX_RESULTADO = 30_000          # caracteres de cada resultado de consulta que ve el modelo
# US$ por token (Claude Opus 5.5: $4 / $20 por millón; lectura de caché $0,20; escritura 1,25×)
PRECIOS = {"entrada": 4 / 1e6, "salida": 20 / 1e6, "cache_lectura": 0.20 / 1e6, "cache_escritura": 5 / 1e6}

HERRAMIENTA = {
    "name": "consultar_sql",
    "description": ("Corre una consulta SELECT (o WITH ... SELECT) de solo lectura en la base de Grupo SHG y "
                    "devuelve las filas en JSON, a lo más 'limite' filas (máximo 500). Una consulta por "
                    "llamada; califica las tablas con su esquema. Agrega en SQL (sum, count, group by) en "
                    "vez de traer miles de filas."),
    "input_schema": {
        "type": "object",
        "properties": {
            "sql": {"type": "string", "description": "La consulta SELECT."},
            "limite": {"type": "integer", "description": "Máximo de filas a devolver (1 a 500)."},
        },
        "required": ["sql", "limite"],
        "additionalProperties": False,
    },
    "strict": True,
}


class TopeGasto(RuntimeError):
    pass


class Rechazo(RuntimeError):
    pass


def costo(usage):
    g = lambda campo: getattr(usage, campo, None) or 0
    return (g("input_tokens") * PRECIOS["entrada"] + g("output_tokens") * PRECIOS["salida"]
            + g("cache_read_input_tokens") * PRECIOS["cache_lectura"]
            + g("cache_creation_input_tokens") * PRECIOS["cache_escritura"])


def ejecutar_consulta(entrada):
    """Resultado de la herramienta como texto, y si fue error."""
    try:
        r = supabase.consultar(entrada["sql"], entrada.get("limite") or 200)
    except supabase.ErrorSupabase as e:
        return f"Error: {e}", True
    texto = json.dumps(r, ensure_ascii=False, default=str)
    if len(texto) > MAX_RESULTADO:
        texto = texto[:MAX_RESULTADO] + f"\n[recortado: el resultado tenía {len(texto)} caracteres; agrega o filtra más]"
    return texto, False


def responder(cliente, agente, texto, tope_usd, consulta=ejecutar_consulta, cuenta=None):
    """Corre el ciclo de herramientas. Devuelve (respuesta, costo_usd, tokens, consultas).

    `cuenta` (dict) acumula el gasto en cuenta["usd"] aunque el ciclo termine en excepción.
    """
    cuenta = {"usd": 0.0} if cuenta is None else cuenta
    sistema = [{"type": "text", "text": perfiles.sistema(agente), "cache_control": {"type": "ephemeral"}}]
    mensajes = [{"role": "user", "content": texto}]
    consultas = 0
    tokens = {"entrada": 0, "salida": 0, "cache_lectura": 0}
    for _ in range(MAX_TURNOS):
        r = cliente.beta.messages.create(
            model=MODELO, max_tokens=16000, system=sistema, tools=[HERRAMIENTA], messages=mensajes,
            output_config={"effort": ESFUERZO},
            betas=["server-side-fallback-2026-07-01"], extra_body={"fallbacks": "default"},
        )
        cuenta["usd"] += costo(r.usage)
        tokens["entrada"] += r.usage.input_tokens or 0
        tokens["salida"] += r.usage.output_tokens or 0
        tokens["cache_lectura"] += getattr(r.usage, "cache_read_input_tokens", None) or 0
        if r.stop_reason == "refusal":
            raise Rechazo("El modelo rechazó la instrucción (stop_reason refusal).")
        usos = [b for b in r.content if b.type == "tool_use"]
        if r.stop_reason != "tool_use" or not usos:
            final = "\n\n".join(b.text for b in r.content if b.type == "text").strip()
            if r.stop_reason == "max_tokens":
                final += "\n\n_(Respuesta cortada por largo.)_"
            return final or "(El agente terminó sin texto.)", cuenta["usd"], tokens, consultas
        if cuenta["usd"] > tope_usd:
            raise TopeGasto(f"La instrucción pasó el tope de US$ {tope_usd:.2f} antes de terminar.")
        mensajes.append({"role": "assistant", "content": r.content})
        resultados = []
        for u in usos:
            salida, es_error = consulta(u.input) if u.name == "consultar_sql" else (f"Error: no existe la herramienta {u.name}", True)
            consultas += 1
            resultados.append({"type": "tool_result", "tool_use_id": u.id, "content": salida, "is_error": es_error})
        mensajes.append({"role": "user", "content": resultados})
    raise TopeGasto(f"El agente no terminó en {MAX_TURNOS} turnos.")
