"""Acceso a Supabase (PostgREST) con la clave service_role.

La tabla shg_dashboards.agentes_instrucciones guarda cada instrucción de la Oficina de Agentes
y su respuesta; public.agente_consulta(sql) es la única puerta de los agentes a los datos
(rol agentes_lectura, solo SELECT, transacción de solo lectura). Ver
automatizacion/oficina_agentes.sql.
"""
import json
import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import requests

SUPABASE_URL = "https://ffxopvzxyeacpbtxuagu.supabase.co"
ESQUEMA = "shg_dashboards"
TABLA = "agentes_instrucciones"
SANTIAGO = ZoneInfo("America/Santiago")


class ErrorSupabase(RuntimeError):
    pass


def _cabeceras(esquema=None, prefer=None):
    clave = os.environ.get("SUPABASE_SERVICE_KEY")
    if not clave:
        raise ErrorSupabase("Falta SUPABASE_SERVICE_KEY")
    h = {"apikey": clave, "Authorization": f"Bearer {clave}", "Content-Type": "application/json"}
    if esquema:
        h["Accept-Profile"] = esquema
        h["Content-Profile"] = esquema
    if prefer:
        h["Prefer"] = prefer
    return h


def _pedir(metodo, ruta, esquema=None, prefer=None, cuerpo=None, params=None, timeout=60):
    try:
        r = requests.request(metodo, f"{SUPABASE_URL}/rest/v1/{ruta}", headers=_cabeceras(esquema, prefer),
                             params=params, data=None if cuerpo is None else json.dumps(cuerpo), timeout=timeout)
    except requests.RequestException as e:
        raise ErrorSupabase(f"No se pudo conectar a Supabase: {e}") from e
    if r.status_code >= 400:
        raise ErrorSupabase(f"Supabase respondió HTTP {r.status_code} en {metodo} {ruta}: {r.text[:300]}")
    return r.json() if r.text else None


def leer_instruccion(id_):
    filas = _pedir("GET", TABLA, ESQUEMA, params={"id": f"eq.{int(id_)}", "select": "*"})
    if not filas:
        raise ErrorSupabase(f"No existe la instrucción {id_}")
    return filas[0]


def actualizar_instruccion(id_, **campos):
    _pedir("PATCH", TABLA, ESQUEMA, prefer="return=minimal", cuerpo=campos, params={"id": f"eq.{int(id_)}"})


def gasto_de_hoy():
    """US$ gastados hoy (hora de Santiago) por todas las instrucciones."""
    inicio = datetime.now(SANTIAGO).replace(hour=0, minute=0, second=0, microsecond=0)
    filas = _pedir("GET", TABLA, ESQUEMA, params={"select": "costo_usd", "creada": f"gte.{inicio.isoformat()}"})
    return sum(float(f["costo_usd"] or 0) for f in filas or [])


def consultar(sql, limite=200):
    """Corre una consulta de solo lectura como agentes_lectura. Devuelve {filas, n, limite}."""
    return _pedir("POST", "rpc/agente_consulta", cuerpo={"p_sql": sql, "p_limite": limite}, timeout=130)


def ahora_iso():
    return datetime.now(timezone.utc).isoformat()

