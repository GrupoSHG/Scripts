"""Etapa 1: consulta las licitaciones activas y muestra la cantidad y las 10 primeras.

    python prueba.py
"""
import logging
import sys

from mp_api import ErrorAPI, MercadoPublico

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")


def main():
    mp = MercadoPublico()
    try:
        datos = mp.licitaciones(estado="activas")
    except ErrorAPI as e:
        raise SystemExit(f"Error: {e}")
    lista = datos.get("Listado") or []
    print(f"Licitaciones activas: {datos.get('Cantidad', len(lista))}")
    print(f"Fecha de la respuesta: {datos.get('FechaCreacion', '-')}")
    print()
    for lic in lista[:10]:
        print(f"  {lic.get('CodigoExterno', ''):<18} {lic.get('Nombre', '')}")
    print()
    print(f"Solicitudes en esta ejecución: {mp.hechas} · hoy: {mp.contador.leer()} de {mp.contador.tope} permitidas")


if __name__ == "__main__":
    main()
