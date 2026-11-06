"""
filtrar_vendedores.py
======================
notas_venta_pendientes y facturacion_periodo tienen una FK a
shg_dashboards.vendedores(codvend). Cuando Manager crea un vendedor nuevo
(ej. codvend 10, noviembre 2026) y todavía no tiene fila en vendedores, el
upsert completo falla con 23503 y el pipeline se corta sin llegar al stock.

Este filtro deja fuera solo las filas de vendedores no registrados y avisa
en el log (solo el código, sin montos: el repo es público), para que el
resto del pipeline siga. Para que el vendedor aparezca en los dashboards
basta con agregar su fila en shg_dashboards.vendedores.
"""

import logging

log = logging.getLogger(__name__)


def filtrar_vendedores_registrados(supabase, filas, tabla):
    """Devuelve las filas cuyo codvend existe en vendedores (o es nulo)."""
    resp = supabase.table("vendedores").select("codvend").execute()
    registrados = {v["codvend"] for v in resp.data}

    validas, omitidas = [], {}
    for fila in filas:
        cod = fila.get("codvend")
        if cod is None or cod in registrados:
            validas.append(fila)
        else:
            omitidas[cod] = omitidas.get(cod, 0) + 1

    for cod, n in sorted(omitidas.items()):
        log.warning(
            "⚠️ %s: se omiten %d filas del codvend %s porque no está en "
            "shg_dashboards.vendedores (agregarlo para que aparezca).",
            tabla, n, cod,
        )
    return validas
