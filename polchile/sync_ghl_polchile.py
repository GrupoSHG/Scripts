"""Sincroniza el CRM de Polchile (GoHighLevel) con el schema polchile_crm de Supabase,
para el Dashboard Gerencia Comercial (informe "Dashboard Gerencia Comercial Polchile").

Trae pipelines, usuarios, todas las oportunidades (con fuente, atribución de marketing,
razón de pérdida, etiquetas, región y campos personalizados) y todos los contactos, y
los reemplaza en una sola transacción con polchile_crm.sincronizar_ghl.

Variables de entorno: GHL_POLCHILE_TOKEN, SUPABASE_SERVICE_KEY, GHL_POLCHILE_LOCATION (opcional).
Para probar en local se pueden poner en un .env junto a este archivo (no se sube a git):
  python polchile/sync_ghl_polchile.py --simular

Scopes del Private Integration Token: opportunities.readonly, contacts.readonly,
users.readonly, locations.readonly y locations/customFields.readonly.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

_ENV = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(_ENV):
    for _l in open(_ENV, encoding="utf-8"):
        _k, _, _v = _l.strip().partition("=")
        if _k and not _k.startswith("#"):
            os.environ.setdefault(_k.strip(), _v.strip().strip('"'))

GHL_API = "https://services.leadconnectorhq.com"
SUPABASE_URL = "https://ffxopvzxyeacpbtxuagu.supabase.co"


# Subcuenta de Polchile en hub.thehublab.cl (sale en la URL /v2/location/<id>/). No es secreto.
LOCATION_POLCHILE = "Gx3QQKLSPxmRU9211gGO"


def location():
    return os.environ.get("GHL_POLCHILE_LOCATION") or LOCATION_POLCHILE


def ghl(ruta, params=None, cuerpo=None, opcional=False):
    url = f"{GHL_API}{ruta}" + (f"?{urllib.parse.urlencode(params)}" if params else "")
    req = urllib.request.Request(url, data=json.dumps(cuerpo).encode() if cuerpo is not None else None,
                                 method="POST" if cuerpo is not None else "GET", headers={
        "Authorization": "Bearer " + os.environ["GHL_POLCHILE_TOKEN"],
        "Version": "2021-07-28", "Accept": "application/json", "Content-Type": "application/json",
        # Cloudflare (error 1010) bloquea la firma por defecto de Python-urllib.
        "User-Agent": "Mozilla/5.0 (compatible; PolchileDashboardComercial/1.0)"})
    for intento in range(5):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code == 429 and intento < 4:
                time.sleep(5 * (intento + 1))
                continue
            detalle = f"GHL rechazó {ruta} (HTTP {e.code}): {e.read().decode('utf-8', 'replace')[:300]}"
            if opcional:
                print("aviso:", detalle)
                return None
            raise SystemExit(detalle)


def campos_personalizados(loc, modelo):
    datos = ghl(f"/locations/{loc}/customFields", {"model": modelo}, opcional=True) or {}
    return {c["id"]: c.get("name") or c["id"] for c in datos.get("customFields", [])}


def valor_campo(c):
    for k in ("fieldValue", "value", "fieldValueString", "fieldValueNumber", "fieldValueDate", "fieldValueArray"):
        if c.get(k) not in (None, "", []):
            return c[k]
    return None


def campos(lista, nombres):
    return {nombres.get(c.get("id"), c.get("id")): valor_campo(c)
            for c in (lista or []) if valor_campo(c) is not None}


def atribucion(obj):
    """Primer contacto de marketing: fuente de sesión, medio, utm_source y campaña."""
    lista = obj.get("attributions") or []
    a = next((x for x in lista if x.get("isFirst")), lista[0] if lista else None) or obj.get("attributionSource") or {}
    return {
        "fuente_sesion": a.get("utmSessionSource") or a.get("sessionSource"),
        "medio": a.get("medium") or a.get("utmMedium"),
        "utm_source": a.get("utmSource"),
        "campana": a.get("utmCampaign") or a.get("campaign"),
    }


def main():
    loc = location()
    pipelines = ghl("/opportunities/pipelines", {"locationId": loc}).get("pipelines", [])
    etapas, info_etapa = [], {}
    for p in pipelines:
        for i, s in enumerate(p.get("stages", [])):
            orden = s.get("position", i)
            etapas.append({"etapa_id": s["id"], "pipeline_id": p["id"], "pipeline_nombre": p["name"],
                           "etapa_nombre": s["name"], "orden": orden})
            info_etapa[s["id"]] = (s["name"], orden)
    nombre_pipeline = {p["id"]: p["name"] for p in pipelines}

    usuarios_raw = (ghl("/users/", {"locationId": loc}, opcional=True) or {}).get("users", [])
    usuarios = [{"id": u["id"], "email": u.get("email"),
                 "nombre": (u.get("name") or f'{u.get("firstName", "")} {u.get("lastName", "")}').strip(),
                 "rol": (u.get("roles") or {}).get("role")} for u in usuarios_raw]
    nombre_usuario = {u["id"]: u["nombre"] for u in usuarios}

    razones = {}
    datos_razones = ghl("/opportunities/lost-reason", {"locationId": loc}, opcional=True) or {}
    for r in datos_razones.get("lostReasons", datos_razones.get("lostReason", [])) or []:
        razones[r.get("id")] = r.get("name")

    campos_opp = campos_personalizados(loc, "opportunity")
    campos_con = campos_personalizados(loc, "contact")

    # Contactos (búsqueda paginada con searchAfter: sin el límite de 10.000 de page).
    contactos, contacto_por_id, despues = [], {}, None
    while True:
        cuerpo = {"locationId": loc, "pageLimit": 100}
        if despues:
            cuerpo["searchAfter"] = despues
        else:
            cuerpo["page"] = 1
        lote = (ghl("/contacts/search", cuerpo=cuerpo) or {}).get("contacts", [])
        for c in lote:
            fila = {"id": c["id"],
                    "nombre": (c.get("contactName") or f'{c.get("firstName") or ""} {c.get("lastName") or ""}').strip() or None,
                    "empresa": c.get("companyName"), "tipo": c.get("type"), "fuente": c.get("source"),
                    "etiquetas": c.get("tags") or [], "region": c.get("state"), "ciudad": c.get("city"),
                    "asignado_a": nombre_usuario.get(c.get("assignedTo"), c.get("assignedTo")),
                    "campos": campos(c.get("customFields"), campos_con), "creado_en": c.get("dateAdded")}
            fila.update({k: v for k, v in atribucion(c).items() if k != "utm_source"})
            contactos.append(fila)
            contacto_por_id[c["id"]] = fila
        if len(contactos) % 2000 < 100:
            print(f"  contactos: {len(contactos)}", flush=True)
        if len(lote) < 100:
            break
        despues = lote[-1].get("searchAfter")
        if not despues:
            break

    oportunidades, pagina = [], 1
    while True:
        datos = ghl("/opportunities/search", {"location_id": loc, "limit": 100, "page": pagina})
        lote = datos.get("opportunities", [])
        for o in lote:
            c = o.get("contact") or {}
            ficha = contacto_por_id.get(o.get("contactId") or c.get("id"), {})
            etapa, orden = info_etapa.get(o.get("pipelineStageId"), (None, None))
            fila = {
                "id": o["id"], "nombre": (o.get("name") or "").strip(),
                "pipeline_id": o.get("pipelineId"), "pipeline_nombre": nombre_pipeline.get(o.get("pipelineId")),
                "etapa_id": o.get("pipelineStageId"), "etapa_nombre": etapa, "etapa_orden": orden,
                "estado": o.get("status"), "monto": o.get("monetaryValue") or 0,
                "contacto_id": o.get("contactId") or c.get("id"), "contacto": c.get("name") or ficha.get("nombre"),
                "empresa": c.get("companyName") or ficha.get("empresa"),
                "asignado_id": o.get("assignedTo"), "asignado_a": nombre_usuario.get(o.get("assignedTo"), o.get("assignedTo")),
                "fuente": o.get("source"),
                "razon_perdida_id": o.get("lostReasonId"),
                "razon_perdida": razones.get(o.get("lostReasonId")) or o.get("lostReason"),
                "etiquetas": c.get("tags") or ficha.get("etiquetas") or [],
                "region": ficha.get("region"), "ciudad": ficha.get("ciudad"),
                "campos": campos(o.get("customFields"), campos_opp),
                "creada_en": o.get("createdAt"), "cambio_etapa_en": o.get("lastStageChangeAt"),
                "cambio_estado_en": o.get("lastStatusChangeAt"), "actualizada_en": o.get("updatedAt"),
            }
            fila.update(atribucion(o))
            for k in ("fuente_sesion", "medio", "campana"):      # sin atribución propia: la del contacto
                fila[k] = fila[k] or ficha.get(k)
            oportunidades.append(fila)
        total = (datos.get("meta") or {}).get("total")
        if len(lote) < 100 or (total is not None and len(oportunidades) >= total):
            break
        pagina += 1

    print(f"GHL Polchile: {len(pipelines)} pipelines, {len(etapas)} etapas, {len(usuarios)} usuarios, "
          f"{len(oportunidades)} oportunidades, {len(contactos)} contactos, {len(razones)} razones de pérdida")
    if "--simular" in sys.argv:
        print("Pipelines:", ", ".join(f"{p['name']} ({len(p.get('stages', []))} etapas)" for p in pipelines))
        print("Campos de oportunidad:", ", ".join(sorted(set(campos_opp.values()))) or "ninguno")
        print("Campos de contacto:", ", ".join(sorted(set(campos_con.values()))) or "ninguno")
        con_fuente = sum(1 for o in oportunidades if o["fuente_sesion"] or o["medio"] or o["fuente"])
        print(f"Oportunidades con fuente/atribución: {con_fuente} de {len(oportunidades)}")
        return

    key = os.environ["SUPABASE_SERVICE_KEY"]
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/rpc/sincronizar_ghl",
        data=json.dumps({"etapas": etapas, "usuarios": usuarios, "oportunidades": oportunidades,
                         "contactos": contactos}).encode("utf-8"),
        headers={"apikey": key, "Authorization": "Bearer " + key, "Content-Type": "application/json",
                 "Content-Profile": "polchile_crm"},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            print("Supabase:", r.read().decode())
    except urllib.error.HTTPError as e:
        raise SystemExit(f"Supabase rechazó la sincronización (HTTP {e.code}): {e.read().decode('utf-8', 'replace')[:500]}")


if __name__ == "__main__":
    try:
        main()
    except SystemExit as e:
        # En GitHub Actions el error queda como anotación visible en el resumen de la corrida.
        if e.code not in (None, 0) and os.environ.get("GITHUB_ACTIONS"):
            print(f"::error::{e.code}")
        raise
    except Exception as e:
        if os.environ.get("GITHUB_ACTIONS"):
            print(f"::error::{type(e).__name__}: {e}")
        raise
