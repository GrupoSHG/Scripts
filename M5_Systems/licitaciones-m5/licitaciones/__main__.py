"""Línea de comandos.

    python -m licitaciones descargar [--fecha ddmmaaaa] [--max N] [--forzar] [--perfil RUTA]
    python -m licitaciones evaluar [--dia AAAA-MM-DD] [--max N] [--perfil RUTA]
    python -m licitaciones guardar [--dia AAAA-MM-DD]   # upsert en Supabase m5.licitaciones_mp
    python -m licitaciones reporte [--dia AAAA-MM-DD] [--sin-supabase]   # reporte.html y reporte.txt
    python -m licitaciones detalle CODIGO      # qué entrega la API para una licitación real

Códigos de salida: 0 ok · 1 configuración · 2 error de la API de Mercado Público · 3 tope de
solicitudes · 4 error de la API de Claude · 5 tope de gasto · 6 demasiadas respuestas JSON inválidas ·
7 error de Supabase.
"""
import argparse
import json
import logging
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

from . import descarga, evaluacion, reporte, supabase_mp
from .config import SALIDA, cargar_ajustes, cargar_env, cargar_perfil, configurar_logging
from .detalle import URL_FICHA, estructura, sanitizar
from .errores import ErrorProceso
from .mp_api import MercadoPublico

log = logging.getLogger("licitaciones")


def cmd_descargar(args):
    embudo, _ = descarga.ejecutar(cargar_ajustes(), cargar_perfil(args.perfil), fecha=args.fecha,
                                  max_detalles=args.max, forzar=args.forzar)
    print(json.dumps({k: v for k, v in embudo.items() if k != "errores_detalle"}, ensure_ascii=False, indent=1))


def cmd_evaluar(args):
    ajustes = cargar_ajustes()
    dia = args.dia or f"{datetime.now(ZoneInfo(ajustes['horario']['zona'])):%Y-%m-%d}"
    costo, resultados = evaluacion.ejecutar(ajustes, cargar_perfil(args.perfil), SALIDA / dia, max_n=args.max)
    print(evaluacion.tabla(resultados))
    print(json.dumps(costo, ensure_ascii=False, indent=1))


def _carpeta_dia(ajustes, dia):
    return SALIDA / (dia or f"{datetime.now(ZoneInfo(ajustes['horario']['zona'])):%Y-%m-%d}")


def cmd_guardar(args):
    ajustes = cargar_ajustes()
    print(json.dumps(supabase_mp.guardar(ajustes, _carpeta_dia(ajustes, args.dia)), ensure_ascii=False))


def cmd_reporte(args):
    ajustes = cargar_ajustes()
    ruta_html, ruta_txt, _ = reporte.generar(ajustes, _carpeta_dia(ajustes, args.dia),
                                             usar_supabase=False if args.sin_supabase else None)
    print(ruta_txt.read_text(encoding="utf-8"))
    print(f"HTML: {ruta_html}")


def cmd_detalle(args):
    mp = MercadoPublico(cargar_ajustes())
    det = mp.detalle(args.codigo)
    if not det:
        print(f"La API no devolvió detalle para {args.codigo}.")
        return 1
    limpio, descartados = sanitizar(det)
    print(f"Licitación {args.codigo} · ficha web: {URL_FICHA.format(args.codigo)}\n")
    print("Estructura del detalle (solo nombres y tipos, sin valores):")
    print("\n".join(estructura(det)))
    claves = [l.strip() for l in estructura(det, max_nivel=6)]
    sospechosos = [l for l in claves if any(p in l.lower() for p in ("adjunt", "document", "archivo", "anexo", "base", "url"))]
    print("\nCampos que podrían ser adjuntos o bases:", sospechosos or "ninguno")
    print("Campos descartados por la lista blanca (posibles datos personales):", descartados)
    ruta = SALIDA / f"detalle_{args.codigo}.json"
    descarga.escribir_json(ruta, limpio)
    print(f"\nDetalle saneado guardado en {ruta.relative_to(SALIDA.parent)} · solicitudes: {mp.hechas}")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m licitaciones", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="comando", required=True)
    p = sub.add_parser("descargar", help="etapa 1: listado, filtro y detalle")
    p.add_argument("--fecha", help="ddmmaaaa; por defecto hoy y ayer")
    p.add_argument("--max", type=int, help="pedir el detalle de a lo más N candidatas (pruebas)")
    p.add_argument("--forzar", action="store_true", help="permitir más detalles fuera de 22:00-07:00")
    p.add_argument("--perfil", help="otro archivo de perfil (por defecto PERFIL_M5_YAML o config/perfil_m5.yaml)")
    p.set_defaults(fn=cmd_descargar)
    p = sub.add_parser("evaluar", help="etapa 2: puntuar con Claude las filtradas del día")
    p.add_argument("--dia", help="carpeta salida/AAAA-MM-DD; por defecto la de hoy")
    p.add_argument("--max", type=int, help="evaluar a lo más N licitaciones (pruebas)")
    p.add_argument("--perfil", help="otro archivo de perfil (por defecto PERFIL_M5_YAML o config/perfil_m5.yaml)")
    p.set_defaults(fn=cmd_evaluar)
    p = sub.add_parser("guardar", help="etapa 4: upsert del día en Supabase (m5.licitaciones_mp)")
    p.add_argument("--dia", help="carpeta salida/AAAA-MM-DD; por defecto la de hoy")
    p.set_defaults(fn=cmd_guardar)
    p = sub.add_parser("reporte", help="etapa 3: reporte del día en HTML y texto (salida/AAAA-MM-DD/)")
    p.add_argument("--dia", help="carpeta salida/AAAA-MM-DD; por defecto la de hoy")
    p.add_argument("--sin-supabase", action="store_true", help="'cierran pronto' solo con lo evaluado en el día")
    p.set_defaults(fn=cmd_reporte)
    p = sub.add_parser("detalle", help="mostrar qué entrega la API para una licitación")
    p.add_argument("codigo")
    p.set_defaults(fn=cmd_detalle)
    args = ap.parse_args(argv)

    configurar_logging()
    cargar_env()
    try:
        return args.fn(args) or 0
    except ErrorProceso as e:
        log.error("%s", e)
        return e.codigo_salida
    except Exception:
        log.exception("Error inesperado")
        return 1


if __name__ == "__main__":
    sys.exit(main())
