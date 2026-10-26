"""Línea de comandos.

    python -m licitaciones descargar [--fecha ddmmaaaa] [--max N] [--forzar] [--perfil RUTA]
    python -m licitaciones evaluar [--dia AAAA-MM-DD] [--max N] [--perfil RUTA]
    python -m licitaciones guardar [--dia AAAA-MM-DD]   # upsert en Supabase m5.licitaciones_mp
    python -m licitaciones reporte [--dia AAAA-MM-DD] [--sin-supabase]   # reporte.html y reporte.txt
    python -m licitaciones diario [--fecha ddmmaaaa] [--max N]   # las 4 etapas (lo que corre GitHub Actions)
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

from . import descarga, evaluacion, precios_oc, reporte, supabase_mp
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


def cmd_diario(args):
    """Descarga (omitiendo las ya evaluadas), evaluación, Supabase y reporte. Solo imprime cifras
    agregadas: en GitHub Actions el log es público y no debe llevar las evaluaciones."""
    ajustes, perfil = cargar_ajustes(), cargar_perfil(args.perfil)
    sb = supabase_mp.Supabase(ajustes)
    evaluadas = {c for c, f in sb.conocidas().items() if f.get("evaluado_en")}
    log.info("Supabase: %d licitaciones ya evaluadas (no se vuelven a pedir)", len(evaluadas))
    embudo, _ = descarga.ejecutar(ajustes, perfil, fecha=args.fecha, max_detalles=args.max, evaluadas=evaluadas)
    carpeta = SALIDA / embudo["corrida"][:10]
    costo, _ = evaluacion.ejecutar(ajustes, perfil, carpeta)
    guardado = supabase_mp.guardar(ajustes, carpeta, sb=sb)
    _, _, datos = reporte.generar(ajustes, carpeta, sb=sb)
    resumen = {"carpeta": carpeta.name,
               "embudo": {k: embudo[k] for k in ("listado_total", "en_estados_a_procesar", "ya_evaluadas_omitidas",
                                                 "pasan_filtro_nombre", "detalles_obtenidos", "pasan_filtro_detalle",
                                                 "solicitudes_corrida", "respuestas_http")},
               "claude": {k: costo[k] for k in ("modelo", "evaluadas", "ok", "revisar_manualmente", "conservadas",
                                                "descartadas_por_claude", "costo_usd_corrida", "gasto_usd_hoy")},
               "supabase": guardado,
               "reporte": {"mejores": len(datos["mejores"]), "cierran": len(datos["cierran"]),
                           "revision_manual": len(datos["manual"])}}
    print(json.dumps(resumen, ensure_ascii=False, indent=1))


def cmd_precios_oc(args):
    """Prueba de precios de referencia desde órdenes de compra de Mercado Público."""
    from .errores import ErrorConfig
    ajustes = cargar_ajustes()
    mp = MercadoPublico(ajustes)
    ahora = datetime.now(mp.contador.zona)
    tope = int(ajustes["horario"]["max_detalles_fuera_de_horario"])
    if not descarga.dentro_de_ventana(ajustes, ahora) and args.max > tope:
        raise ErrorConfig(f"Fuera de la ventana nocturna se piden a lo más {tope} detalles (pediste {args.max}).")
    fecha = args.fecha or f"{ahora:%d%m%Y}"
    res = precios_oc.probar(mp, fecha, args.max)
    descarga.escribir_json(SALIDA / "precios_oc" / f"{fecha[4:]}{fecha[2:4]}{fecha[:2]}.json", res)
    r = res["resumen"]
    print(json.dumps({k: v for k, v in res.items() if k not in ("ocs", "resumen")}, ensure_ascii=False, indent=1))
    print(f"Ítems: {r['items']} · calidad: {r['calidad']}")
    print("| n | Producto (Mercado Público) | Unidad (texto) | Mediana | Mín | Máx |")
    print("|---|---|---|---|---|---|")
    for x in r["productos"][:args.mostrar]:
        print(f"| {x['n']} | {(x['producto'] or '')[:45]} | {x['unidad']} | {x['mediana']:,.0f} | {x['minimo']:,.0f} | {x['maximo']:,.0f} |".replace(",", "."))


def cmd_precios_normalizar(args):
    """Normaliza con Claude los ítems de una prueba de precios-oc (no pide nada a Mercado Público)."""
    from . import normalizacion
    from .errores import ErrorConfig
    origen = SALIDA / "precios_oc" / f"{args.dia}.json"
    if not origen.is_file():
        raise ErrorConfig(f"No existe salida/precios_oc/{args.dia}.json: correr primero precios-oc.")
    ocs = descarga.leer_json(origen, {}).get("ocs") or []
    filas, resumen = normalizacion.ejecutar(cargar_ajustes(), ocs)
    grupos = normalizacion.agrupar(filas)
    descarga.escribir_json(SALIDA / "precios_oc" / f"{args.dia}-normalizado.json",
                           {"resumen": resumen, "filas": filas, "grupos": grupos})
    print(json.dumps(resumen, ensure_ascii=False))
    print("| n | Material | Especificación | Presentación | Mediana presentación | Mediana por unidad base |")
    print("|---|---|---|---|---|---|")
    mil = lambda v: "—" if v is None else f"{v:,.0f}".replace(",", ".")
    for g in grupos[:args.mostrar]:
        base = f"{mil(g['mediana_unidad_base'])} / {g['unidad_base']}" if g["mediana_unidad_base"] is not None else "—"
        print(f"| {g['n']} | {g['material']} | {g['especificacion'] or '—'} | {g['presentacion']} | "
              f"{mil(g['mediana_presentacion'])} | {base} |")


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
    p = sub.add_parser("diario", help="etapas 1 a 4 seguidas, con Supabase (lo que corre GitHub Actions)")
    p.add_argument("--fecha", help="ddmmaaaa; por defecto hoy y ayer")
    p.add_argument("--max", type=int, help="pedir el detalle de a lo más N candidatas (pruebas)")
    p.add_argument("--perfil", help="otro archivo de perfil (por defecto PERFIL_M5_YAML o config/perfil_m5.yaml)")
    p.set_defaults(fn=cmd_diario)
    p = sub.add_parser("precios-oc", help="prueba: precios de materiales desde órdenes de compra de Mercado Público")
    p.add_argument("--fecha", help="ddmmaaaa; por defecto hoy")
    p.add_argument("--max", type=int, default=50, help="detalles a pedir (fuera de 22:00-07:00, máximo 50)")
    p.add_argument("--mostrar", type=int, default=25, help="filas de la tabla de precios")
    p.set_defaults(fn=cmd_precios_oc)
    p = sub.add_parser("precios-normalizar", help="prueba: normalizar con Claude los ítems de precios-oc")
    p.add_argument("--dia", required=True, help="AAAAMMDD del archivo salida/precios_oc/AAAAMMDD.json")
    p.add_argument("--mostrar", type=int, default=40, help="filas de la tabla")
    p.set_defaults(fn=cmd_precios_normalizar)
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
