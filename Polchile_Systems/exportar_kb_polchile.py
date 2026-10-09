"""Exporta la base de conocimientos (Knowledge Base) del CRM de Polchile (GoHighLevel).

Recorre todas las bases de conocimiento de la subcuenta y baja, para cada una, sus
preguntas frecuentes (FAQ) y las páginas web entrenadas. Deja todo en salida/:
  kb_polchile.json  (crudo, tal como lo devuelve la API)
  kb_polchile.md    (legible: FAQ en formato P: / R: y lista de páginas)

Lo corre el workflow .github/workflows/exportar-kb-polchile.yml (workflow_dispatch) con el
token GHL_POLCHILE_TOKEN; el resultado queda como artifact "kb-polchile".

Variables de entorno: GHL_POLCHILE_TOKEN, GHL_POLCHILE_LOCATION (opcional).
El Private Integration Token necesita acceso a Knowledge Base (lectura); si no lo tiene, la
API responde 401/403 y el error queda escrito en salida/kb_polchile.md.
"""
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

GHL_API = "https://services.leadconnectorhq.com"
LOCATION_POLCHILE = "Gx3QQKLSPxmRU9211gGO"
SALIDA = "salida"


def location():
    return os.environ.get("GHL_POLCHILE_LOCATION") or LOCATION_POLCHILE


def ghl(ruta, params=None):
    """GET a la API v2. Devuelve (json, error); error es None si la llamada fue bien."""
    url = f"{GHL_API}{ruta}" + (f"?{urllib.parse.urlencode(params)}" if params else "")
    req = urllib.request.Request(url, headers={
        "Authorization": "Bearer " + os.environ["GHL_POLCHILE_TOKEN"],
        "Version": "2021-07-28", "Accept": "application/json",
        "User-Agent": "Mozilla/5.0 (compatible; PolchileExportadorKB/1.0)"})
    for intento in range(5):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read()), None
        except urllib.error.HTTPError as e:
            if e.code == 429 and intento < 4:
                time.sleep(5 * (intento + 1))
                continue
            return None, f"HTTP {e.code} en {ruta}: {e.read().decode('utf-8', 'replace')[:300]}"
        except Exception as e:  # red, timeout
            if intento < 4:
                time.sleep(3)
                continue
            return None, f"{type(e).__name__} en {ruta}: {e}"


def primera_lista(obj):
    """La API envuelve las listas con nombres distintos (data.knowledgeBases, faqs, urls...)."""
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        for v in obj.values():
            if isinstance(v, list) and (not v or isinstance(v[0], dict)):
                return v
        for v in obj.values():
            if isinstance(v, dict):
                lista = primera_lista(v)
                if lista:
                    return lista
    return []


def buscar(obj, clave):
    if isinstance(obj, dict):
        if clave in obj:
            return obj[clave]
        for v in obj.values():
            r = buscar(v, clave)
            if r is not None:
                return r
    return None


def main():
    loc = location()
    os.makedirs(SALIDA, exist_ok=True)
    errores = []
    bases = []

    # 1. Bases de conocimiento de la subcuenta (paginado por lastKnowledgeBaseId)
    ultimo = None
    while True:
        params = {"locationId": loc, "limit": 100}
        if ultimo:
            params["lastKnowledgeBaseId"] = ultimo
        datos, err = ghl("/knowledge-bases/", params)
        if err:
            errores.append(err)
            break
        lote = primera_lista(datos)
        bases.extend(lote)
        ultimo = buscar(datos, "lastKnowledgeBaseId")
        if not buscar(datos, "hasMore") or not lote or not ultimo:
            break

    # 2. Detalle, FAQ y páginas entrenadas por base
    for kb in bases:
        kid = kb.get("id") or kb.get("_id")
        if not kid:
            continue
        detalle, err = ghl(f"/knowledge-bases/{kid}")
        if err:
            errores.append(err)
        kb["detalle"] = detalle

        faqs, ultimo_faq = [], None
        while True:
            params = {"knowledgeBaseId": kid, "locationId": loc, "limit": 100}
            if ultimo_faq:
                params["lastFaqId"] = ultimo_faq
            datos, err = ghl("/knowledge-bases/faqs", params)
            if err:
                errores.append(err)
                break
            lote = primera_lista(datos)
            faqs.extend(lote)
            ultimo_faq = buscar(datos, "lastFaqId")
            if not buscar(datos, "hasMore") or not lote or not ultimo_faq:
                break
        kb["faqs"] = faqs

        urls, pagina = [], 1
        while True:
            datos, err = ghl("/knowledge-bases/crawler",
                             {"knowledgeBaseId": kid, "locationId": loc, "page": pagina, "pageLength": 100})
            if err:
                errores.append(err)
                break
            lote = primera_lista(datos)
            urls.extend(lote)
            total = buscar(datos, "count")
            if not lote or (isinstance(total, int) and len(urls) >= total) or pagina > 50:
                break
            pagina += 1
        kb["urls"] = urls

    # 3. Agentes de Conversation AI (opcional: requiere scope conversation-ai.readonly)
    agentes, err = ghl("/conversation-ai/agents/search", {"limit": 50})
    if err:
        errores.append(err)

    with open(os.path.join(SALIDA, "kb_polchile.json"), "w", encoding="utf-8") as f:
        json.dump({"locationId": loc, "bases": bases, "agentes": agentes, "errores": errores}, f,
                  ensure_ascii=False, indent=1)

    md = ["# Base de conocimientos del CRM Polchile (GoHighLevel)", "",
          f"Subcuenta {loc} · {len(bases)} base(s) de conocimiento · exportado {time.strftime('%Y-%m-%d %H:%M')} UTC", ""]
    for kb in bases:
        nombre = kb.get("name") or kb.get("title") or kb.get("id")
        md += [f"## {nombre}", ""]
        desc = kb.get("description") or buscar(kb.get("detalle") or {}, "description")
        if desc:
            md += [str(desc), ""]
        md += [f"### Preguntas frecuentes ({len(kb['faqs'])})", ""]
        for fq in kb["faqs"]:
            md += [f"P: {str(fq.get('question', '')).strip()}", "", f"R: {str(fq.get('answer', '')).strip()}", ""]
        md += [f"### Páginas web entrenadas ({len(kb['urls'])})", ""]
        for u in kb["urls"]:
            enlace = u.get("url") or u.get("link") or json.dumps(u, ensure_ascii=False)
            estado = u.get("status") or u.get("trainingStatus") or ""
            md += [f"- {enlace} {('(' + str(estado) + ')') if estado else ''}".rstrip()]
        md += [""]
    if agentes:
        md += ["## Agentes de Conversation AI", "", "```json", json.dumps(agentes, ensure_ascii=False, indent=1)[:20000], "```", ""]
    if errores:
        md += ["## Errores", ""] + [f"- {e}" for e in errores] + [""]
    with open(os.path.join(SALIDA, "kb_polchile.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(md))

    print(f"{len(bases)} bases, {sum(len(k['faqs']) for k in bases)} FAQ, "
          f"{sum(len(k['urls']) for k in bases)} páginas, {len(errores)} errores")
    for e in errores:
        print("ERROR:", e)


if __name__ == "__main__":
    main()
