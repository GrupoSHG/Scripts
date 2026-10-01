"""Sincroniza el CRM de M5 Industrial (GoHighLevel) con el schema m5 de Supabase.

Lee los pipelines y todas las oportunidades de la subcuenta M5 y llama a
m5.sincronizar_ghl, que en una sola transacción:
  - actualiza m5.pipeline_etapas (la probabilidad ya cargada no se pisa),
  - reemplaza m5.oportunidades,
  - crea en m5.proyectos un proyecto por cada oportunidad ganada que aún no tenga.

Variables de entorno: GHL_M5_TOKEN, SUPABASE_SERVICE_KEY, GHL_M5_LOCATION (opcional).
Para probar en local se pueden poner en un .env junto a este archivo (no se sube a git):
  python .github/scripts/sync_ghl_m5.py --simular

Scopes del Private Integration Token: opportunities.readonly, contacts.readonly,
users.readonly y locations/customFields.readonly.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

# .env local opcional (en GitHub Actions los valores vienen de los secrets).
_ENV = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(_ENV):
    for _l in open(_ENV, encoding="utf-8"):
        _k, _, _v = _l.strip().partition("=")
        if _k and not _k.startswith("#"):
            os.environ.setdefault(_k.strip(), _v.strip().strip('"'))

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
        "Version": "2021-07-28", "Accept": "application/json",
        # Cloudflare (error 1010) bloquea la firma por defecto de Python-urllib.
        "User-Agent": "Mozilla/5.0 (compatible; PolchileDashboardM5/1.0)"})
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


def campos_personalizados():
    """Nombres de los campos personalizados de oportunidades (id -> nombre)."""
    try:
        datos = ghl(f"/locations/{LOCATION}/customFields", {"model": "opportunity"})
    except SystemExit as e:
        print(f"aviso: sin nombres de campos personalizados ({e})")
        return {}
    return {c["id"]: c.get("name") or c["id"] for c in datos.get("customFields", [])}


def valor_campo(c):
    for k in ("fieldValue", "value", "fieldValueString", "fieldValueNumber", "fieldValueDate", "fieldValueArray"):
        if c.get(k) not in (None, "", []):
            return c[k]
    return None


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
    nombres_campos = campos_personalizados()

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
                "campos": {nombres_campos.get(c.get("id"), c.get("id")): valor_campo(c)
                           for c in (o.get("customFields") or []) if valor_campo(c) is not None},
            })
        total = (datos.get("meta") or {}).get("total")
        if len(lote) < 100 or (total is not None and len(oportunidades) >= total):
            break
        pagina += 1

    print(f"GHL: {len(pipelines)} pipelines, {len(etapas)} etapas, {len(oportunidades)} oportunidades")
    if "--simular" in sys.argv:
        print("Pipelines:", ", ".join(f"{p['name']} ({len(p.get('stages', []))} etapas)" for p in pipelines))
        print("Campos personalizados:", ", ".join(sorted(set(nombres_campos.values()))) or "ninguno")
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
