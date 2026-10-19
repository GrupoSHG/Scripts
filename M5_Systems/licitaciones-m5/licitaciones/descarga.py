"""Etapa 1: listado del día, filtro por nombre, detalle de las candidatas y filtro fino.

El listado por fecha trae ~1.000-1.500 licitaciones con solo código, nombre, estado y cierre,
y cada detalle cuesta 1 solicitud (con 1,5 s de pausa). Por eso el detalle se pide solo de las
que pasan el filtro por nombre. Salida en salida/AAAA-MM-DD/:
  listado.json     lo que devolvió el listado (código, nombre, estado, cierre)
  descartadas.json código, nombre y motivo de cada descarte (para calibrar el perfil)
  filtradas.json   las que pasan, con el detalle saneado: entrada de la etapa 2
  embudo.json      cantidades de cada paso, solicitudes y códigos HTTP vistos
y salida/estados_vistos.json (código de estado -> textos vistos, para verificar la documentación).
"""
import json
import logging
from collections import Counter
from datetime import datetime, time as dtime, timedelta

from .config import SALIDA
from .detalle import registro, sanitizar
from .errores import ErrorAPI, ErrorConfig, LimiteSolicitudes
from .filtro import Filtro
from .mp_api import MercadoPublico

log = logging.getLogger("licitaciones.descarga")


def dentro_de_ventana(ajustes, ahora):
    h = ajustes["horario"]
    desde, hasta = dtime.fromisoformat(h["carga_masiva_desde"]), dtime.fromisoformat(h["carga_masiva_hasta"])
    t = ahora.time()
    return t >= desde or t < hasta


def escribir_json(ruta, datos):
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")


def leer_json(ruta, defecto):
    try:
        return json.loads(ruta.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return defecto


def ejecutar(ajustes, perfil, fecha=None, max_detalles=None, forzar=False, mp=None):
    filtro = Filtro(perfil, ajustes)
    mp = mp or MercadoPublico(ajustes)
    zona = mp.contador.zona
    ahora = datetime.now(zona)
    carpeta = SALIDA / f"{ahora:%Y-%m-%d}"
    desc = ajustes["descarga"]

    # 1. Listado (si falla, no hay corrida)
    if fecha:
        fechas = [fecha]
    else:
        fechas = [f"{ahora - timedelta(days=d):%d%m%Y}" for d in range(int(desc["dias_atras"]), -1, -1)]
    listado = {}
    for f in fechas:
        for lic in mp.listado(fecha=f):
            listado[lic["CodigoExterno"]] = lic
    escribir_json(carpeta / "listado.json", list(listado.values()))
    por_estado = Counter(str(l.get("CodigoEstado")) for l in listado.values())
    log.info("Listado %s: %d licitaciones; por estado %s", ", ".join(fechas), len(listado), dict(por_estado))

    estados_vistos = leer_json(SALIDA / "estados_vistos.json", {})
    for lic in listado.values():
        estados_vistos.setdefault(str(lic.get("CodigoEstado")), [])

    # 2. Filtro por nombre
    estados = set(desc["estados_a_procesar"])
    en_estado = [l for l in listado.values() if l.get("CodigoEstado") in estados]
    candidatas, descartadas = [], []
    for lic in en_estado:
        pasa, info = filtro.por_nombre(lic.get("Nombre"))
        if pasa:
            candidatas.append(lic)
        else:
            descartadas.append({"codigo_externo": lic["CodigoExterno"], "nombre": lic.get("Nombre"),
                                "paso": "nombre", "motivo": info})
    log.info("En estados %s: %d · pasan el filtro por nombre: %d", sorted(estados), len(en_estado), len(candidatas))

    if max_detalles is not None:
        candidatas = candidatas[:max_detalles]
    limite_fuera = int(ajustes["horario"]["max_detalles_fuera_de_horario"])
    if not dentro_de_ventana(ajustes, ahora) and len(candidatas) > limite_fuera and not forzar:
        raise ErrorConfig(f"Son {len(candidatas)} detalles por pedir y son las {ahora:%H:%M} en Chile, fuera de la "
                          f"ventana {ajustes['horario']['carga_masiva_desde']}-{ajustes['horario']['carga_masiva_hasta']} "
                          f"que pide ChileCompra para descargas masivas. Usar --max {limite_fuera} o menos, "
                          "ejecutar de noche o, con justificación, --forzar.")

    # 3. Detalle y filtro fino. Las salidas se escriben siempre, también si la corrida se corta.
    filtradas, errores, obtenidos, interrupcion = [], [], 0, None
    try:
        for i, lic in enumerate(candidatas, 1):
            codigo = lic["CodigoExterno"]
            try:
                det = mp.detalle(codigo)
            except ErrorAPI as e:
                if e.fatal:
                    raise
                errores.append({"codigo_externo": codigo, "http": e.http, "error": str(e)})
                log.warning("Sin detalle de %s: %s", codigo, e)
                if len(errores) > int(desc["max_errores_detalle"]):
                    raise ErrorAPI(f"{len(errores)} detalles fallidos (máximo {desc['max_errores_detalle']}): "
                                   "se detiene la corrida. Ver embudo.json.") from None
                continue
            if not det:
                errores.append({"codigo_externo": codigo, "http": 200, "error": "detalle vacío"})
                continue
            obtenidos += 1
            textos = estados_vistos.setdefault(str(det.get("CodigoEstado")), [])
            if det.get("Estado") and det["Estado"] not in textos:
                textos.append(det["Estado"])
            limpio, _ = sanitizar(det)
            pasa, info = filtro.por_detalle(limpio)
            if pasa:
                filtradas.append(registro(limpio, info, filtro.organismo_prioritario(limpio), zona))
            else:
                descartadas.append({"codigo_externo": codigo, "nombre": lic.get("Nombre"), "paso": "detalle", "motivo": info})
            if i % 25 == 0:
                log.info("Detalle %d/%d · pasan %d · solicitudes hoy %d", i, len(candidatas), len(filtradas), mp.contador.leer())
    except (ErrorAPI, LimiteSolicitudes) as e:
        interrupcion = str(e)
        raise
    finally:
        embudo = {
            "corrida": ahora.isoformat(timespec="seconds"),
            "fechas_listado": fechas,
            "listado_total": len(listado),
            "listado_por_estado": dict(por_estado),
            "en_estados_a_procesar": len(en_estado),
            "pasan_filtro_nombre": len(candidatas),
            "detalles_obtenidos": obtenidos,
            "detalles_con_error": len(errores),
            "pasan_filtro_detalle": len(filtradas),
            "solicitudes_corrida": mp.hechas,
            "solicitudes_hoy": mp.contador.leer(),
            "tope_solicitudes": mp.contador.tope,
            "respuestas_http": {str(k): v for k, v in mp.respuestas.items()},
            "interrumpida": interrupcion,
            "errores_detalle": errores,
        }
        escribir_json(carpeta / "filtradas.json", filtradas)
        escribir_json(carpeta / "descartadas.json", descartadas)
        escribir_json(carpeta / "embudo.json", embudo)
        escribir_json(SALIDA / "estados_vistos.json", estados_vistos)
        log.info("Embudo: listado %d -> estado %d -> nombre %d -> detalle %d -> filtradas %d · "
                 "solicitudes %d (hoy %d de tope %d) · HTTP %s · salida en %s",
                 len(listado), len(en_estado), len(candidatas), obtenidos, len(filtradas),
                 mp.hechas, mp.contador.leer(), mp.contador.tope, embudo["respuestas_http"], carpeta.name)
    return embudo, filtradas
