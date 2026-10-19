"""Descarga con un cliente falso: las ya evaluadas en Supabase no se vuelven a pedir."""
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
from zoneinfo import ZoneInfo

from licitaciones import descarga

AJUSTES = {"horario": {"carga_masiva_desde": "00:00", "carga_masiva_hasta": "23:59", "max_detalles_fuera_de_horario": 50},
           "descarga": {"dias_atras": 0, "estados_a_procesar": [5], "max_errores_detalle": 3},
           "filtro": {"prefijos_rubro_unspsc": []}}
PERFIL = {"palabras_clave_incluir": ["construccion"]}


class MPFalso:
    def __init__(self):
        self.contador = SimpleNamespace(zona=ZoneInfo("America/Santiago"), leer=lambda: 0, tope=8000)
        self.hechas, self.respuestas, self.pedidos = 0, Counter(), []

    def listado(self, fecha):
        return [{"CodigoExterno": c, "Nombre": f"Construcción {c}", "CodigoEstado": 5} for c in ("nueva", "vieja")]

    def detalle(self, codigo):
        self.pedidos.append(codigo)
        return {"CodigoExterno": codigo, "Nombre": f"Construcción {codigo}", "CodigoEstado": 5, "Estado": "Publicada",
                "Comprador": {}, "Fechas": {}, "Items": {"Listado": []}}


class TestOmitirEvaluadas(unittest.TestCase):
    def test_no_pide_detalle_de_las_ya_evaluadas(self):
        mp = MPFalso()
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(descarga, "SALIDA", Path(tmp)):
            embudo, filtradas = descarga.ejecutar(AJUSTES, PERFIL, mp=mp, evaluadas={"vieja"})
        self.assertEqual(mp.pedidos, ["nueva"])
        self.assertEqual([f["codigo_externo"] for f in filtradas], ["nueva"])
        self.assertEqual((embudo["ya_evaluadas_omitidas"], embudo["pasan_filtro_nombre"]), (1, 1))


if __name__ == "__main__":
    unittest.main()
