"""Sincroniza el CRM de M5 Industrial (GoHighLevel) con el schema m5 de Supabase.

Lee los pipelines y todas las oportunidades de la subcuenta M5 y llama a
m5.sincronizar_ghl, que en una sola transacción:
  - actualiza m5.pipeline_etapas (la probabilidad ya cargada no se pisa),
  - reemplaza m5.oportunidades,
  - crea en m5.proyectos un proyecto por cada oportunidad ganada que aún no tenga.

Variables de entorno: GHL_M5_TOKEN, SUPABASE_SERVICE_KEY, GHL_M5_LOCATION (opcional).
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

GHL_API = "https://services.leadconnectorhq.com"
LOCATION = os.environ.get("GHL_M5_LOCATION") or "LVfUGrPaqm62ekFL9z0I"
SUPABASE_URL = "https://ffxopvzxyeacpbtxuagu.supabase.co"

# Probabilidad inicial por etapa, igual que el pipeline de Polchile (cockpit-comercial).
# Después se puede ajustar a mano en m5.pipeline_etapas.
PROB = [("lead no atendido", 5), ("lead atendido", 10), ("cotizacion enviada", 40),
        ("negociacion cierre", 70), ("nv emitida", 90), ("compromiso de comp", 95), ("ganado", 100)]


def sin_tildes(s):
    return s.lower().translate(str.maketrans("áéíóúü", "aeiouu"))


def probabilidad(nombre):
    n = sin_tildes(nombre)
    for clave, p in PROB:
        if clave in n:
            return p
    return 20


def ghl(ruta, params):
    url = f"{GHL_API}{ruta}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={
        "Authorization": "Bearer " + os.environ["GHL_M5_TOKEN"],
        "Version": "2021-07-28", "Accept": "application/json"})
    for intento in range(4):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code == 429 and intento < 3:
                time.sleep(5 * (intento + 1))
                continue
            raise SystemExit(f"GHL rechazó {ruta} (HTTP {e.code}): {e.read().decode('utf-8', 'replace')[:300]}")


def usuarios():
    """Nombres de los usuarios para 'asignado_a'. Si el token no tiene permiso, quedan los IDs."""
    try:
        datos = ghl("/users/", {"locationId": LOCATION})
    except SystemExit as e:
        print(f"aviso: sin nombres de usuarios ({e})")
        return {}
    return {u["id"]: (u.get("name") or f'{u.get("firstName", "")} {u.get("lastName", "")}').strip()
            for u in datos.get("users", [])}


def main():
    pipelines = ghl("/opportunities/pipelines", {"locationId": LOCATION}).get("pipelines", [])
    etapas, info_etapa = [], {}
    for p in pipelines:
        for i, s in enumerate(p.get("stages", [])):
            orden = s.get("position", i)
            etapas.append({"etapa_id": s["id"], "pipeline_id": p["id"], "pipeline_nombre": p["name"],
                           "etapa_nombre": s["name"], "orden": orden, "probabilidad": probabilidad(s["name"])})
            info_etapa[s["id"]] = (s["name"], orden)
    nombres = usuarios()

    oportunidades, pagina = [], 1
    while True:
        datos = ghl("/opportunities/search", {"location_id": LOCATION, "limit": 100, "page": pagina})
        lote = datos.get("opportunities", [])
        for o in lote:
            contacto = o.get("contact") or {}
            etapa, orden = info_etapa.get(o.get("pipelineStageId"), (None, None))
            pipeline = next((p["name"] for p in pipelines if p["id"] == o.get("pipelineId")), None)
            oportunidades.append({
                "id": o["id"], "nombre": (o.get("name") or "").strip(),
                "pipeline_id": o.get("pipelineId"), "pipeline_nombre": pipeline,
                "etapa_id": o.get("pipelineStageId"), "etapa_nombre": etapa, "etapa_orden": orden,
                "estado": o.get("status"), "monto": o.get("monetaryValue") or 0,
                "contacto": contacto.get("name"), "empresa": contacto.get("companyName"),
                "asignado_a": nombres.get(o.get("assignedTo"), o.get("assignedTo")),
                "fuente": o.get("source"), "creada_en": o.get("createdAt"),
                "cambio_etapa_en": o.get("lastStageChangeAt"), "actualizada_en": o.get("updatedAt"),
            })
        total = (datos.get("meta") or {}).get("total")
        if len(lote) < 100 or (total is not None and len(oportunidades) >= total):
            break
        pagina += 1

    print(f"GHL: {len(pipelines)} pipelines, {len(etapas)} etapas, {len(oportunidades)} oportunidades")
    if "--simular" in sys.argv:
        print(json.dumps(oportunidades[:3], ensure_ascii=False, indent=1))
        return

    key = os.environ["SUPABASE_SERVICE_KEY"]
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/rpc/sincronizar_ghl",
        data=json.dumps({"etapas": etapas, "oportunidades": oportunidades}).encode("utf-8"),
        headers={"apikey": key, "Authorization": "Bearer " + key, "Content-Type": "application/json",
                 "Content-Profile": "m5"},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            print("Supabase:", r.read().decode())
    except urllib.error.HTTPError as e:
        raise SystemExit(f"Supabase rechazó la sincronización (HTTP {e.code}): {e.read().decode('utf-8', 'replace')[:500]}")


if __name__ == "__main__":
    main()
