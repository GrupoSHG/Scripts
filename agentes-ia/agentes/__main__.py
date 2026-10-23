"""python -m agentes ejecutar --id N

Toma la instrucción N de shg_dashboards.agentes_instrucciones, la marca 'trabajando', la resuelve
con el agente que corresponde y deja la respuesta (o el error) en la misma fila. El log solo
muestra cifras: Scripts es un repo público y el texto de la instrucción y la respuesta pueden
traer datos de la empresa.

Variables: ANTHROPIC_API_KEY, SUPABASE_SERVICE_KEY, AGENTES_GH_TOKEN (solo los Desarrolladores),
CLAUDE_CODE_OAUTH_TOKEN (opcional: los Desarrolladores usan la suscripción de Claude en vez de la API
y no cuentan para el tope diario), AGENTES_TOPE_DIARIO_USD (por defecto 5),
AGENTES_TOPE_INSTRUCCION_USD (analistas, por defecto 1,5), AGENTES_TOPE_DEV_USD (Desarrollador, por defecto 3),
RUN_URL (enlace a la corrida, lo pone el workflow).
"""
import argparse
import os
import sys

from . import analista, desarrollador, perfiles, supabase


def topes(agente):
    if agente in perfiles.DESARROLLADORES:
        por_instruccion = os.environ.get("AGENTES_TOPE_DEV_USD") or 3
    else:
        por_instruccion = os.environ.get("AGENTES_TOPE_INSTRUCCION_USD") or 1.5
    return float(os.environ.get("AGENTES_TOPE_DIARIO_USD") or 5), float(por_instruccion)


def ejecutar(id_):
    ins = supabase.leer_instruccion(id_)
    if ins["estado"] != "pendiente":
        print(f"Instrucción {id_}: ya estaba '{ins['estado']}', no se hace nada.")
        return 0
    agente = ins["agente"]
    if agente not in perfiles.AGENTES:
        supabase.actualizar_instruccion(id_, estado="error", error=f"Agente desconocido: {agente}",
                                        terminada=supabase.ahora_iso())
        return 1

    es_dev = agente in perfiles.DESARROLLADORES
    tope_dia, tope_ins = topes(agente)
    # Con suscripción el Desarrollador no gasta de la API: el tope diario no lo frena.
    if not (es_dev and os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")):
        gastado = supabase.gasto_de_hoy()
        if gastado >= tope_dia:
            supabase.actualizar_instruccion(id_, estado="error", terminada=supabase.ahora_iso(),
                                            error=f"Se alcanzó el tope diario de US$ {tope_dia:.2f} (gastado hoy: US$ {gastado:.2f}).")
            print(f"Instrucción {id_}: tope diario alcanzado.")
            return 5
        tope_ins = min(tope_ins, tope_dia - gastado)

    supabase.actualizar_instruccion(id_, estado="trabajando", iniciada=supabase.ahora_iso(),
                                    run_url=os.environ.get("RUN_URL"))
    print(f"Instrucción {id_}: agente {agente}, tope US$ {tope_ins:.2f}.")
    cuenta, tokens, consultas = {"usd": 0.0}, None, 0
    try:
        if es_dev:
            respuesta, cuenta["usd"], tokens = desarrollador.responder(ins, tope_ins)
        else:
            import anthropic
            cliente = anthropic.Anthropic(max_retries=3)
            respuesta, _, tokens, consultas = analista.responder(cliente, agente, ins["texto"], tope_ins, cuenta=cuenta)
    except Exception as e:  # noqa: BLE001 — cualquier falla queda escrita en la fila
        mensaje = str(e) if isinstance(e, (analista.TopeGasto, analista.Rechazo, desarrollador.ErrorDesarrollador,
                                           supabase.ErrorSupabase)) else f"{type(e).__name__}: {e}"
        supabase.actualizar_instruccion(id_, estado="error", error=mensaje[:2000], terminada=supabase.ahora_iso(),
                                        costo_usd=round(cuenta["usd"], 4))
        print(f"Instrucción {id_}: error ({type(e).__name__}).")
        return 4
    supabase.actualizar_instruccion(id_, estado="listo", respuesta=respuesta, terminada=supabase.ahora_iso(),
                                    costo_usd=round(cuenta["usd"], 4), tokens=tokens)
    print(f"Instrucción {id_}: lista. Consultas: {consultas}. Costo: US$ {cuenta['usd']:.4f}.")
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(prog="agentes")
    sub = p.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("ejecutar", help="Resolver una instrucción de la Oficina de Agentes")
    e.add_argument("--id", type=int, required=True)
    args = p.parse_args(argv)
    try:
        return ejecutar(args.id)
    except supabase.ErrorSupabase as e:
        print(f"Supabase: {e}", file=sys.stderr)
        return 7


if __name__ == "__main__":
    sys.exit(main())
