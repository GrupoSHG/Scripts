"""Normalización de ítems de órdenes de compra: esquema, conversiones y precios, sin red."""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from licitaciones.evaluacion import Presupuesto
from licitaciones.normalizacion import Normalizado, agrupar, ejecutar, precios, validar_lote

AJUSTES = {"horario": {"zona": "America/Santiago"}, "evaluacion": {
    "modelo": "claude-haiku-5-5", "esfuerzo": "low", "tope_gasto_diario_usd": 1.0,
    "precios_usd_por_mtok": {"claude-haiku-5-5": {"entrada": 0.10, "salida": 0.50}}}}


def norm(**c):
    base = {"indice": 0, "es_material_construccion": True, "material": "sellador poliuretano", "especificacion": "gris",
            "presentacion": "cartucho", "contenido": 300.0, "unidad_contenido": "ml", "confianza": "alta"}
    base.update(c)
    return base


class TestConversion(unittest.TestCase):
    def test_unidades(self):
        casos = [("ml", 300.0, 0.3, "litro"), ("g", 370.0, 0.37, "kg"), ("galon", 1.0, 3.785, "litro"),
                 ("cm", 40.0, 0.4, "m"), ("kg", 25.0, 25.0, "kg"), ("unidad", 100.0, 100.0, "unidad")]
        for unidad, contenido, esperado, base in casos:
            n = Normalizado.model_validate(norm(contenido=contenido, unidad_contenido=unidad))
            self.assertEqual(n.base(), (esperado, base), unidad)

    def test_sin_contenido_no_hay_precio_base(self):
        n = Normalizado.model_validate(norm(contenido=None, unidad_contenido=None))
        self.assertEqual(precios({"precio_neto": 4500}, n), (4500.0, None))

    def test_precio_por_unidad_base(self):
        n = Normalizado.model_validate(norm())
        self.assertEqual(precios({"precio_neto": 7143}, n), (7143.0, 23810.0))


class TestValidarLote(unittest.TestCase):
    def test_ok_y_errores(self):
        ok = json.dumps({"items": [norm(indice=0), norm(indice=1)]})
        self.assertIsNone(validar_lote(ok, [0, 1])[1])
        self.assertIn("índices", validar_lote(ok, [0, 2])[1])
        self.assertIsNotNone(validar_lote(json.dumps({"items": [norm(unidad_contenido="pulgada")]}), [0])[1])
        self.assertIsNotNone(validar_lote(json.dumps({"items": [norm(precio=1000)]}), [0])[1])  # no acepta precios
        self.assertIsNotNone(validar_lote("no es json", [0])[1])


class ClienteFalso:
    def __init__(self, respuesta):
        self.respuesta, self.pedidos, self.messages = respuesta, [], self

    def create(self, **kw):
        self.pedidos.append(kw)
        return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=self.respuesta)],
                               usage=SimpleNamespace(input_tokens=1000, output_tokens=300,
                                                     cache_read_input_tokens=0, cache_creation_input_tokens=0))


class TestEjecutar(unittest.TestCase):
    def test_lote_completo_y_claude_no_ve_precios(self):
        ocs = [{"codigo": "1-1-SE26", "fecha_envio": None, "region": "RM", "items": [
            {"producto": "Selladores", "especificacion_comprador": "SIKAFLEX 300ML", "cantidad": 2,
             "precio_neto": 7143, "moneda": "CLP"},
            {"producto": "Arena", "especificacion_comprador": "Arena", "cantidad": 0, "precio_neto": 0, "moneda": "CLP"}]}]
        cliente = ClienteFalso(json.dumps({"items": [norm(indice=0)]}))
        with tempfile.TemporaryDirectory() as tmp:
            pres = Presupuesto(AJUSTES, ZoneInfo("America/Santiago"), carpeta=Path(tmp))
            filas, resumen = ejecutar(AJUSTES, ocs, cliente=cliente, presupuesto=pres)
        self.assertEqual((resumen["items_con_precio"], resumen["normalizados"]), (1, 1))   # el de precio 0 no se envía
        self.assertEqual((filas[0]["precio_unidad_base"], filas[0]["unidad_base"]), (23810.0, "litro"))
        enviado = cliente.pedidos[0]["messages"][0]["content"]
        self.assertNotIn("7143", enviado)
        self.assertNotIn("precio", enviado.lower())

    def test_agrupar(self):
        f = {"es_material_construccion": True, "material": "cemento", "especificacion": "25 kg", "presentacion": "saco",
             "unidad_base": "kg"}
        g = agrupar([{**f, "precio_presentacion": 4000, "precio_unidad_base": 160},
                     {**f, "precio_presentacion": 5000, "precio_unidad_base": 200},
                     {**f, "es_material_construccion": False, "precio_presentacion": 1, "precio_unidad_base": 1}])
        self.assertEqual((g[0]["n"], g[0]["mediana_presentacion"], g[0]["mediana_unidad_base"]), (2, 4500, 180))


if __name__ == "__main__":
    unittest.main()
