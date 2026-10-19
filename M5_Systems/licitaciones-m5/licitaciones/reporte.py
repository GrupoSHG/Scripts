"""Etapa 3: reporte diario en HTML y texto (salida/AAAA-MM-DD/reporte.html y reporte.txt).

Secciones: mejores del día (evaluadas hoy, por puntaje), las que cierran en los próximos N días y
las que quedaron para revisión manual, cada una con enlace a la ficha. "Cierran pronto" sale de
Supabase (todas las guardadas, no solo las de hoy) cuando hay SUPABASE_URL y SUPABASE_KEY; si no,
solo de lo evaluado en el día. No envía nada: solo escribe los archivos.
"""
import html
import logging
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .descarga import leer_json

log = logging.getLogger("licitaciones.reporte")


def _normalizar(r):
    """Misma forma para una licitación evaluada hoy (evaluadas.json) o una fila de Supabase."""
    if "evaluacion" in r:  # evaluadas.json (la evaluación viene anidada; None si quedó para revisión manual)
        e = r["evaluacion"] or {}
        return {"codigo": r["codigo_externo"], "nombre": r.get("nombre"), "organismo": r.get("organismo"),
                "region": r.get("region"), "cierre": r.get("fecha_cierre"), "monto": r.get("monto_estimado_clp"),
                "url": r.get("url_ficha"), "puntaje": e.get("puntaje"), "recomendacion": e.get("recomendacion"),
                "motivo": e.get("motivo") or r.get("error"), "riesgos": e.get("riesgos") or [],
                "manual": r.get("estado") == "revisar_manualmente"}
    return {"codigo": r["codigo_externo"], "nombre": r.get("nombre"), "organismo": r.get("organismo"),
            "region": r.get("region"), "cierre": r.get("fecha_cierre"), "monto": r.get("monto_estimado"),
            "url": r.get("url_ficha"), "puntaje": r.get("puntaje"), "recomendacion": r.get("recomendacion"),
            "motivo": r.get("motivo"), "riesgos": r.get("riesgos") or [],
            "manual": r.get("estado_evaluacion") == "revisar_manualmente"}


def _fecha(valor, zona):
    if not valor:
        return None
    try:
        return datetime.fromisoformat(valor).astimezone(zona)
    except ValueError:
        return None


def armar(ajustes, carpeta, sb=None, ahora=None):
    """Datos del reporte: dict con mejores, cierran, manual y el resumen de la corrida."""
    zona = ZoneInfo(ajustes["horario"]["zona"])
    ahora = ahora or datetime.now(zona)
    cfg = ajustes.get("reporte") or {}
    dias = int(cfg.get("dias_cierre", 7))
    hoy = [_normalizar(r) for r in leer_json(carpeta / "evaluadas.json", [])]

    mejores = sorted((x for x in hoy if not x["manual"] and x["puntaje"] is not None),
                     key=lambda x: (-x["puntaje"], x["cierre"] or "9999"))[:int(cfg.get("max_mejores", 10))]
    manual = [x for x in hoy if x["manual"]]

    # Hasta el final del día N (no a la misma hora): una que cierra el día 7 a las 15:00 entra.
    hasta = (ahora + timedelta(days=dias)).replace(hour=23, minute=59, second=59, microsecond=0)
    fuente_cierre = "las evaluadas hoy"
    candidatas = {x["codigo"]: x for x in hoy}
    if sb is not None:
        for fila in sb.cierran_entre(ahora.isoformat(timespec="seconds"), hasta.isoformat(timespec="seconds")):
            candidatas.setdefault(fila["codigo_externo"], _normalizar(fila))
        fuente_cierre = "todas las guardadas en Supabase"
    cierran = sorted((x for x in candidatas.values()
                      if x["recomendacion"] != "descartar" and (c := _fecha(x["cierre"], zona)) and ahora <= c <= hasta),
                     key=lambda x: x["cierre"])
    # Las capturadas antes de la evaluación con Claude van aparte, en una lista compacta y acotada.
    sin_evaluar = [x for x in cierran if x["puntaje"] is None and not x["manual"]]
    cierran = [x for x in cierran if x not in sin_evaluar]

    return {"fecha": ahora, "dias": dias, "mejores": mejores, "cierran": cierran, "manual": manual,
            "sin_evaluar": sin_evaluar, "max_sin_evaluar": int(cfg.get("max_sin_evaluar", 30)),
            "fuente_cierre": fuente_cierre, "embudo": leer_json(carpeta / "embudo.json", {}),
            "costo": leer_json(carpeta / "costo.json", {}), "zona": zona}


# --- Formatos -------------------------------------------------------------------

def _monto(v):
    return "—" if v is None else "$" + f"{float(v):,.0f}".replace(",", ".")


def _cierre(x, zona, ahora):
    c = _fecha(x["cierre"], zona)
    if not c:
        return "—", ""
    dias = (c.date() - ahora.date()).days
    resto = "hoy" if dias <= 0 else "mañana" if dias == 1 else f"en {dias} días"
    return f"{c:%d-%m-%Y %H:%M}", resto


def texto(datos):
    z, ahora = datos["zona"], datos["fecha"]
    e, c = datos["embudo"], datos["costo"]
    lineas = [f"LICITACIONES M5 INDUSTRIAL · {ahora:%d-%m-%Y %H:%M}", ""]
    if e:
        lineas.append(f"Embudo: {e.get('listado_total', 0)} en el listado -> {e.get('en_estados_a_procesar', 0)} publicadas -> "
                      f"{e.get('pasan_filtro_nombre', 0)} por nombre -> {e.get('pasan_filtro_detalle', 0)} tras el filtro fino")
    if c:
        lineas.append(f"Claude ({c.get('modelo')}): {c.get('evaluadas', 0)} evaluadas, {c.get('conservadas', 0)} conservadas, "
                      f"{c.get('descartadas_por_claude', 0)} descartadas · US$ {c.get('costo_usd_corrida', 0):.4f}")
    lineas.append("")

    def bloque(titulo, filas, vacio):
        lineas.extend([titulo, "-" * len(titulo)])
        if not filas:
            lineas.extend([vacio, ""])
            return
        for x in filas:
            fecha, resto = _cierre(x, z, ahora)
            pje = f"[{x['puntaje']}] {x['recomendacion'] or ''}".strip() if x["puntaje"] is not None else (
                "[?] revisar a mano" if x["manual"] else "[-] sin evaluar")
            lineas.append(f"{pje} · {x['codigo']} · {x['nombre']}")
            lineas.append(f"    {x['organismo'] or '—'} · {x['region'] or '—'} · cierre {fecha} ({resto or '—'}) · monto {_monto(x['monto'])}")
            if x["motivo"]:
                lineas.append(f"    {x['motivo']}")
            if x["riesgos"]:
                lineas.append(f"    Riesgos: {'; '.join(x['riesgos'])}")
            lineas.append(f"    {x['url']}")
        lineas.append("")

    bloque(f"MEJORES DEL DÍA ({len(datos['mejores'])})", datos["mejores"], "Sin licitaciones evaluadas hoy.")
    bloque(f"CIERRAN EN LOS PRÓXIMOS {datos['dias']} DÍAS ({len(datos['cierran'])}, de {datos['fuente_cierre']})",
           datos["cierran"], "Ninguna.")
    bloque(f"REVISIÓN MANUAL ({len(datos['manual'])})", datos["manual"], "Ninguna.")
    sin = datos["sin_evaluar"]
    if sin:
        titulo = f"TAMBIÉN CIERRAN EN {datos['dias']} DÍAS, SIN EVALUAR ({len(sin)})"
        lineas.extend([titulo, "-" * len(titulo)])
        for x in sin[:datos["max_sin_evaluar"]]:
            fecha, resto = _cierre(x, z, ahora)
            lineas.append(f"{fecha} ({resto}) · {x['codigo']} · {x['nombre']} · {x['url']}")
        if len(sin) > datos["max_sin_evaluar"]:
            lineas.append(f"... y {len(sin) - datos['max_sin_evaluar']} más en el dashboard de M5.")
        lineas.append("")
    lineas.append("Solo usa la ficha de la API: las bases no están incluidas; revisarlas antes de postular.")
    return "\n".join(lineas) + "\n"


CSS = """
:root{--fondo:#eef1f6;--tarjeta:#fff;--borde:#dde2ec;--tinta:#101828;--suave:#5b6478;--azul:#101d37;--acento:#2f5fb7;
--verde:#1d7a4c;--verde-f:#e6f5ee;--naranja:#b5651d;--naranja-f:#fff4e6;--rojo:#a5321f;--rojo-f:#fbeceb;--gris-f:#eef1f6}
@media (prefers-color-scheme:dark){:root{--fondo:#0f1522;--tarjeta:#172033;--borde:#2a3550;--tinta:#e8ecf4;--suave:#9aa6bf;
--azul:#e8ecf4;--acento:#7fa6ff;--verde:#6fd6a0;--verde-f:#123326;--naranja:#f0b070;--naranja-f:#3a2a14;--rojo:#ff9b8a;
--rojo-f:#3a1b17;--gris-f:#222c42}}
*{box-sizing:border-box}body{margin:0;background:var(--fondo);color:var(--tinta);
font-family:-apple-system,"Segoe UI",Arial,sans-serif;font-size:14px;line-height:1.45}
main{max-width:980px;margin:0 auto;padding:20px 16px 32px}h1{font-size:20px;margin:0;color:var(--azul)}
.sub{color:var(--suave);font-size:12.5px;margin:4px 0 14px}.resumen{display:flex;flex-wrap:wrap;gap:10px;margin-bottom:16px}
.dato{background:var(--tarjeta);border:1px solid var(--borde);border-radius:10px;padding:10px 14px;flex:1;min-width:140px}
.dato b{display:block;font-size:20px;color:var(--azul)}.dato span{font-size:11.5px;color:var(--suave)}
section{background:var(--tarjeta);border:1px solid var(--borde);border-radius:10px;padding:14px 16px;margin-bottom:14px}
h2{font-size:15px;margin:0 0 10px;color:var(--azul)}h2 small{font-weight:400;color:var(--suave);font-size:12px}
.lic{display:flex;gap:12px;padding:10px 0;border-top:1px solid var(--borde)}.lic:first-of-type{border-top:none}
.pje{flex:0 0 auto;width:34px;height:34px;border-radius:8px;display:flex;align-items:center;justify-content:center;
font-weight:700;font-size:15px;background:var(--gris-f);color:var(--suave)}
.p5,.p4{background:var(--verde-f);color:var(--verde)}.p3{background:var(--naranja-f);color:var(--naranja)}
.p2,.p1{background:var(--rojo-f);color:var(--rojo)}.cuerpo{min-width:0;flex:1}
.cuerpo a{color:var(--acento);font-weight:600;text-decoration:none;overflow-wrap:anywhere}.cuerpo a:hover{text-decoration:underline}
.meta{color:var(--suave);font-size:12px;margin-top:2px}.motivo{margin-top:4px}.riesgos{color:var(--suave);font-size:12px;margin-top:2px}
.rec{font-size:10.5px;font-weight:700;text-transform:uppercase;letter-spacing:.3px;margin-left:6px}
.r-postular{color:var(--verde)}.r-revisar{color:var(--naranja)}.r-manual{color:var(--suave)}
.urgente{color:var(--rojo);font-weight:600}.compacta{margin:0;padding-left:18px}.compacta li{margin:3px 0}
.compacta a{color:var(--acento);text-decoration:none}.vacio{color:var(--suave)}.pie{color:var(--suave);font-size:12px;margin-top:8px}
"""


def html_reporte(datos):
    z, ahora, esc = datos["zona"], datos["fecha"], lambda v: html.escape(str(v if v is not None else ""))
    e, c = datos["embudo"], datos["costo"]

    def tarjeta(x):
        fecha, resto = _cierre(x, z, ahora)
        if x["puntaje"] is not None:
            pje, cls, rec = str(x["puntaje"]), f"p{x['puntaje']}", (x["recomendacion"] or "")
        elif x["manual"]:
            pje, cls, rec = "?", "", "revisar a mano"
        else:
            pje, cls, rec = "–", "", "sin evaluar"
        clase_rec = {"postular": "r-postular", "revisar": "r-revisar"}.get(rec, "r-manual")
        urgente = " urgente" if resto in ("hoy", "mañana") else ""
        return (f'<div class="lic"><div class="pje {cls}">{esc(pje)}</div><div class="cuerpo">'
                f'<a href="{esc(x["url"])}" target="_blank" rel="noopener">{esc(x["nombre"])}</a>'
                f'<span class="rec {clase_rec}">{esc(rec)}</span>'
                f'<div class="meta">{esc(x["codigo"])} · {esc(x["organismo"] or "—")} · {esc(x["region"] or "—")} · '
                f'cierre {esc(fecha)} <span class="{urgente.strip()}">({esc(resto or "—")})</span> · monto {esc(_monto(x["monto"]))}</div>'
                + (f'<div class="motivo">{esc(x["motivo"])}</div>' if x["motivo"] else "")
                + (f'<div class="riesgos">⚠ {esc(" · ".join(x["riesgos"]))}</div>' if x["riesgos"] else "")
                + "</div></div>")

    def seccion(titulo, detalle, filas, vacio):
        cuerpo = "".join(map(tarjeta, filas)) if filas else f'<p class="vacio">{esc(vacio)}</p>'
        return f'<section><h2>{esc(titulo)} <small>{esc(detalle)}</small></h2>{cuerpo}</section>'

    def compacta():
        sin, tope = datos["sin_evaluar"], datos["max_sin_evaluar"]
        if not sin:
            return ""
        filas = "".join(f'<li><span class="meta">{esc(_cierre(x, z, ahora)[0])} · {esc(_cierre(x, z, ahora)[1])}</span> '
                        f'<a href="{esc(x["url"])}" target="_blank" rel="noopener">{esc(x["nombre"])}</a> '
                        f'<span class="meta">{esc(x["codigo"])}</span></li>' for x in sin[:tope])
        mas = (f'<p class="pie">… y {len(sin) - tope} más en el '
               f'<a href="https://gruposhg-m5-proyectos.netlify.app/licitaciones.html">dashboard de M5</a>.</p>'
               if len(sin) > tope else "")
        return (f'<section><h2>También cierran en {datos["dias"]} días <small>capturadas antes de la evaluación '
                f'con Claude ({len(sin)})</small></h2><ul class="compacta">{filas}</ul>{mas}</section>')

    resumen = [(len(datos["mejores"]), "mejores del día"), (len(datos["cierran"]), f"evaluadas cierran en {datos['dias']} días"),
               (len(datos["manual"]), "revisión manual")]
    if e:
        resumen.append((e.get("listado_total", 0), f"en el listado · {e.get('pasan_filtro_detalle', 0)} pasaron el filtro"))
    if c:
        resumen.append((f"US$ {c.get('costo_usd_corrida', 0):.4f}", f"Claude · {c.get('evaluadas', 0)} evaluadas"))
    datos_html = "".join(f'<div class="dato"><b>{esc(v)}</b><span>{esc(t)}</span></div>' for v, t in resumen)

    return f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Licitaciones M5 · {ahora:%d-%m-%Y}</title><style>{CSS}</style></head>
<body><main>
<h1>Licitaciones M5 Industrial</h1>
<div class="sub">Reporte del {ahora:%d-%m-%Y %H:%M} · Mercado Público filtrado y puntuado con Claude según el perfil de M5</div>
<div class="resumen">{datos_html}</div>
{seccion("Mejores del día", "evaluadas hoy, por puntaje", datos["mejores"], "Sin licitaciones evaluadas hoy.")}
{seccion(f"Cierran en los próximos {datos['dias']} días", "de " + datos["fuente_cierre"], datos["cierran"], "Ninguna.")}
{seccion("Revisión manual", "la evaluación automática no se pudo validar", datos["manual"], "Ninguna.")}
{compacta()}
<p class="pie">Solo usa la ficha de la API de Mercado Público: las bases no están incluidas; revisarlas antes de postular.
Las que Claude recomienda descartar no aparecen.</p>
</main></body></html>
"""


def generar(ajustes, carpeta, usar_supabase=None, sb=None):
    """Escribe reporte.html y reporte.txt. Devuelve (ruta_html, ruta_txt, datos)."""
    if sb is None and usar_supabase is not False and os.environ.get("SUPABASE_URL") and os.environ.get("SUPABASE_KEY"):
        from .supabase_mp import Supabase
        sb = Supabase(ajustes)
    datos = armar(ajustes, carpeta, sb=sb)
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta_html, ruta_txt = carpeta / "reporte.html", carpeta / "reporte.txt"
    ruta_html.write_text(html_reporte(datos), encoding="utf-8")
    ruta_txt.write_text(texto(datos), encoding="utf-8")
    log.info("Reporte: %d mejores, %d cierran en %d días (%s), %d revisión manual -> %s",
             len(datos["mejores"]), len(datos["cierran"]), datos["dias"], datos["fuente_cierre"],
             len(datos["manual"]), ruta_html.name)
    return ruta_html, ruta_txt, datos
