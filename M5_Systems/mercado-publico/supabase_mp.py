"""Lectura y upsert de m5.licitaciones_mp por la API REST de Supabase.

Variable de entorno: SUPABASE_SERVICE_KEY (service_role; nunca en el código).
El upsert va por codigo_externo y no envía fecha_captura, así la fecha de la primera
captura se conserva y solo cambia `actualizado`.
"""
import os

import requests

SUPABASE_URL = os.environ.get("SUPABASE_URL") or "https://ffxopvzxyeacpbtxuagu.supabase.co"
TABLA = f"{SUPABASE_URL}/rest/v1/licitaciones_mp"
TIMEOUT = (10, 60)
COLUMNAS = ["codigo_externo", "nombre", "organismo", "region", "comuna", "codigo_estado", "estado", "tipo",
            "fecha_publicacion", "fecha_cierre", "monto_estimado", "moneda", "url_ficha", "palabras_clave"]


def _cabeceras(**extra):
    clave = os.environ.get("SUPABASE_SERVICE_KEY", "").strip()
    if not clave:
        raise SystemExit("Falta la variable de entorno SUPABASE_SERVICE_KEY (ver README.md).")
    return {"apikey": clave, "Authorization": f"Bearer {clave}", **extra}


def _revisar(r, que):
    if r.status_code >= 300:
        raise SystemExit(f"Supabase rechazó {que} (HTTP {r.status_code}): {r.text[:300]}")


def leer_todas():
    """{codigo_externo: fila} de todo lo guardado, de a 1.000 filas."""
    filas, desde = {}, 0
    while True:
        r = requests.get(TABLA, params={"select": ",".join(COLUMNAS + ["fecha_captura"]), "order": "codigo_externo"},
                         headers=_cabeceras(**{"Accept-Profile": "m5", "Range": f"{desde}-{desde + 999}"}), timeout=TIMEOUT)
        _revisar(r, "la lectura")
        lote = r.json()
        filas.update({f["codigo_externo"]: f for f in lote})
        if len(lote) < 1000:
            return filas
        desde += 1000


def upsert(filas, ahora):
    for i in range(0, len(filas), 500):
        lote = [{**{k: f.get(k) for k in COLUMNAS}, "actualizado": ahora.isoformat(timespec="seconds")}
                for f in filas[i:i + 500]]
        r = requests.post(TABLA, params={"on_conflict": "codigo_externo"}, json=lote, timeout=TIMEOUT,
                          headers=_cabeceras(**{"Content-Profile": "m5",
                                                "Prefer": "resolution=merge-duplicates,return=minimal"}))
        _revisar(r, "el upsert")
