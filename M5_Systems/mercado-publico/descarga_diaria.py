"""Proceso diario: licitaciones de obras relevantes para M5 Industrial.

1. Lista las licitaciones con movimiento hoy y ayer (licitaciones.json?fecha=, 2 solicitudes)
   o, con --activas, todas las activas (carga inicial).
2. Se queda con los estados de config.json (Publicada) cuyo NOMBRE coincide con alguna
   palabra clave y ninguna exclusión. Solo de esas pide el detalle (1 solicitud cada una)
   y vuelve a filtrar con descripción, ítems y categoría (rubro 72 = construcción).
3. Las ya conocidas que aparecen en el listado con otro estado se actualizan sin pedir detalle.
4. Guarda salida/historico.json (todas las relevantes), salida/licitaciones_AAAAMMDD.json
   (las de esta corrida) y salida/reporte_AAAAMMDD.md (nuevas + cierran en los próximos días).
   Con --supabase además hace upsert en m5.licitaciones_mp (etapa 3).

    python descarga_diaria.py                 # hoy y ayer
    python descarga_diaria.py --fecha 15102026
    python descarga_diaria.py --activas       # carga inicial, solo entre 22:00 y 07:00
"""
import argparse
import json
import logging
import re
import sys
import unicodedata
from datetime import datetime, time as dtime, timedelta

from mp_api import CARPETA, ErrorAPI, LimiteDiarioAlcanzado, MercadoPublico, cargar_config

log = logging.getLogger("mercado_publico")
URL_FICHA = "https://www.mercadopublico.cl/Procurement/Modules/RFB/DetailsAcquisition.aspx?idlicitacion={}"


def normalizar(texto):
    texto = unicodedata.normalize("NFKD", (texto or "").lower())
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", texto)


class Filtro:
    def __init__(self, cfg):
        # Coincidencia desde el inicio de palabra: "edificio" también encuentra "edificios".
        self.claves = [(p, re.compile(r"\b" + re.escape(normalizar(p)))) for p in cfg["palabras_clave"]]
        self.exclusiones = [re.compile(r"\b" + re.escape(normalizar(p))) for p in cfg["exclusiones"]]
        self.prefijos = tuple(cfg.get("prefijos_categoria") or ())

    def coincidencias(self, texto):
        t = normalizar(texto)
        if any(e.search(t) for e in self.exclusiones):
            return []
        return [p for p, rx in self.claves if rx.search(t)]

    def coincidencias_detalle(self, lic):
        nombre = lic.get("Nombre") or ""
        if any(e.search(normalizar(nombre)) for e in self.exclusiones):
            return []
        items = (lic.get("Items") or {}).get("Listado") or []
        texto = " ".join([nombre, lic.get("Descripcion") or ""] +
                         [f"{i.get('NombreProducto') or ''} {i.get('Descripcion') or ''} {i.get('Categoria') or ''}" for i in items])
        claves = [p for p, rx in self.claves if rx.search(normalizar(texto))]
        if any(str(i.get("CodigoCategoria") or "").startswith(self.prefijos) for i in items if self.prefijos):
            claves.append("rubro construcción (UNSPSC 72)")
        return claves


def fecha_chile(valor, zona):
    """Las fechas de la API vienen en hora local de Chile sin zona: se les agrega."""
    if not valor or valor.startswith("1900"):
        return None
    try:
        return datetime.fromisoformat(valor[:19]).replace(tzinfo=zona).isoformat()
    except ValueError:
        return None


def registro(lic, claves, cfg, zona, ahora):
    """Solo datos institucionales: no se guardan nombres, correos ni teléfonos de funcionarios."""
    comp = lic.get("Comprador") or {}
    fechas = lic.get("Fechas") or {}
    monto = lic.get("MontoEstimado")
    codigo_estado = lic.get("CodigoEstado")
    return {
        "codigo_externo": lic["CodigoExterno"],
        "nombre": (lic.get("Nombre") or "").strip(),
        "organismo": (comp.get("NombreOrganismo") or "").strip(),
        "region": (comp.get("RegionUnidad") or "").strip() or None,
        "comuna": (comp.get("ComunaUnidad") or "").strip() or None,
        "codigo_estado": codigo_estado,
        "estado": lic.get("Estado") or cfg["estados"].get(str(codigo_estado)),
        "tipo": lic.get("Tipo"),
        "fecha_publicacion": fecha_chile(fechas.get("FechaPublicacion"), zona),
        "fecha_cierre": fecha_chile(fechas.get("FechaCierre") or lic.get("FechaCierre"), zona),
        # Visibilidad 1 = el organismo publica el monto; 0 o vacío no es un monto real.
        "monto_estimado": monto if (monto and lic.get("VisibilidadMonto") == 1) else None,
        "moneda": lic.get("Moneda"),
        "url_ficha": URL_FICHA.format(lic["CodigoExterno"]),
        "palabras_clave": claves,
        "fecha_captura": ahora.isoformat(timespec="seconds"),
    }


def dentro_de_ventana(cfg, ahora):
    h = cfg["horario"]
    desde, hasta = (dtime.fromisoformat(h["carga_masiva_desde"]), dtime.fromisoformat(h["carga_masiva_hasta"]))
    t = ahora.time()
    return t >= desde or t < hasta


def leer_json(ruta, defecto):
    try:
        return json.loads(ruta.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return defecto


def reporte_md(nuevas, historico, ahora, dias):
    limite = ahora + timedelta(days=dias)
    cierran = sorted((r for r in historico.values()
                      if r.get("codigo_estado") == 5 and r.get("fecha_cierre")
                      and ahora <= datetime.fromisoformat(r["fecha_cierre"]) <= limite),
                     key=lambda r: r["fecha_cierre"])

    def fila(r):
        monto = f"${r['monto_estimado']:,.0f}".replace(",", ".") if r.get("monto_estimado") else "—"
        cierre = r["fecha_cierre"][:16].replace("T", " ") if r.get("fecha_cierre") else "—"
        return f"| [{r['codigo_externo']}]({r['url_ficha']}) | {r['nombre']} | {r['organismo']} | {cierre} | {monto} | {', '.join(r['palabras_clave'])} |"

    cab = "| Código | Nombre | Organismo | Cierre | Monto estimado | Coincidencias |\n|---|---|---|---|---|---|"
    partes = [f"# Licitaciones de obras · {ahora:%d-%m-%Y %H:%M}", "",
              f"## Nuevas relevantes ({len(nuevas)})", "", cab, *map(fila, nuevas), "",
              f"## Cierran en los próximos {dias} días ({len(cierran)})", "", cab, *map(fila, cierran), ""]
    return "\n".join(partes), cierran


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fecha", help="ddmmaaaa; por defecto hoy y ayer")
    ap.add_argument("--activas", action="store_true", help="partir de todas las activas (carga inicial)")
    ap.add_argument("--forzar", action="store_true", help="permitir una carga grande fuera de 22:00-07:00")
    ap.add_argument("--supabase", action="store_true", help="hacer upsert en m5.licitaciones_mp")
    ap.add_argument("--max", type=int, help="pedir el detalle de a lo más N candidatas (pruebas)")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

    cfg = cargar_config()
    mp = MercadoPublico(cfg)
    zona = mp.contador.zona
    ahora = datetime.now(zona)
    filtro = Filtro(cfg)
    salida = CARPETA / "salida"
    salida.mkdir(exist_ok=True)
    ruta_hist = salida / "historico.json"
    historico = leer_json(ruta_hist, {})
    if args.supabase:
        # La tabla es la fuente de verdad: lo ya guardado no se vuelve a pedir (en Actions no hay histórico local).
        import supabase_mp
        historico.update(supabase_mp.leer_todas())
        log.info("Supabase: %d licitaciones ya guardadas", len(historico))

    # 1. Listado
    if args.activas:
        consultas = [{"estado": "activas"}]
    elif args.fecha:
        consultas = [{"fecha": args.fecha}]
    else:
        consultas = [{"fecha": f"{ahora - timedelta(days=1):%d%m%Y}"}, {"fecha": f"{ahora:%d%m%Y}"}]
    listado = {}
    for c in consultas:
        for lic in mp.licitaciones(**c).get("Listado") or []:
            listado[lic["CodigoExterno"]] = lic
    log.info("Listado: %d licitaciones (%s)", len(listado), ", ".join(map(str, consultas)))

    # 2. Estados de las ya conocidas (sin pedir detalle)
    actualizadas = []
    for cod, lic in listado.items():
        r = historico.get(cod)
        if r and r.get("codigo_estado") != lic.get("CodigoEstado"):
            r["codigo_estado"] = lic.get("CodigoEstado")
            r["estado"] = cfg["estados"].get(str(lic.get("CodigoEstado")), r.get("estado"))
            r["fecha_cierre"] = fecha_chile(lic.get("FechaCierre"), zona) or r.get("fecha_cierre")
            r["actualizado"] = ahora.isoformat(timespec="seconds")
            actualizadas.append(r)
    log.info("Estados actualizados de licitaciones ya conocidas: %d", len(actualizadas))

    # 3. Candidatas por nombre
    estados = set(cfg["estados_a_descargar"])
    candidatas = [l for c, l in listado.items()
                  if l.get("CodigoEstado") in estados and c not in historico and filtro.coincidencias(l.get("Nombre"))]
    log.info("Candidatas por nombre (nuevas): %d", len(candidatas))
    if args.max is not None:
        candidatas = candidatas[:args.max]
    restantes = mp.contador.tope - mp.contador.leer()
    if (not dentro_de_ventana(cfg, ahora) and len(candidatas) > cfg["horario"]["max_solicitudes_fuera_de_horario"]
            and not args.forzar):
        raise SystemExit(f"Son {len(candidatas)} solicitudes de detalle y estamos fuera de la ventana "
                         f"{cfg['horario']['carga_masiva_desde']}-{cfg['horario']['carga_masiva_hasta']}. "
                         "Ejecutar de noche o usar --forzar.")
    if len(candidatas) > restantes:
        log.warning("Quedan %d solicitudes hoy: se procesarán solo esas; el resto queda para la próxima corrida.", restantes)

    # 4. Detalle y filtro fino
    nuevas, estados_vistos = [], leer_json(salida / "estados_vistos.json", {})
    for i, lic in enumerate(candidatas, 1):
        try:
            det = (mp.licitaciones(codigo=lic["CodigoExterno"]).get("Listado") or [None])[0]
        except LimiteDiarioAlcanzado as e:
            log.warning("%s Se detiene el detalle en %d de %d.", e, i - 1, len(candidatas))
            break
        except ErrorAPI as e:
            log.warning("Sin detalle de %s: %s", lic["CodigoExterno"], e)
            continue
        if not det:
            continue
        estados_vistos[str(det.get("CodigoEstado"))] = det.get("Estado")
        claves = filtro.coincidencias_detalle(det)
        if claves:
            r = registro(det, claves, cfg, zona, ahora)
            historico[r["codigo_externo"]] = r
            nuevas.append(r)
        if i % 50 == 0:
            log.info("Detalle %d/%d · relevantes %d · solicitudes hoy %d", i, len(candidatas), len(nuevas), mp.contador.leer())

    # 5. Salidas
    ruta_hist.write_text(json.dumps(historico, ensure_ascii=False, indent=1), encoding="utf-8")
    (salida / "estados_vistos.json").write_text(json.dumps(estados_vistos, ensure_ascii=False, indent=1), encoding="utf-8")
    (salida / f"licitaciones_{ahora:%Y%m%d}.json").write_text(json.dumps(nuevas, ensure_ascii=False, indent=1), encoding="utf-8")
    texto, cierran = reporte_md(nuevas, historico, ahora, cfg["reporte"]["dias_cierre"])
    (salida / f"reporte_{ahora:%Y%m%d}.md").write_text(texto, encoding="utf-8")

    if args.supabase:
        supabase_mp.upsert(nuevas + actualizadas, ahora)
        log.info("Supabase: upsert de %d filas (%d nuevas, %d con cambio de estado)",
                 len(nuevas) + len(actualizadas), len(nuevas), len(actualizadas))

    log.info("Listo: %d nuevas relevantes, %d cierran en %d días, %d en el histórico. Solicitudes: %d en esta corrida, %d hoy.",
             len(nuevas), len(cierran), cfg["reporte"]["dias_cierre"], len(historico), mp.hechas, mp.contador.leer())
    log.info("Estados vistos en el detalle: %s", estados_vistos)


if __name__ == "__main__":
    main()
