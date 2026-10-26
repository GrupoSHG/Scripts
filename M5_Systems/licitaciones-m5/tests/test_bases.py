"""Bases de licitaciones: esquema, conversiones, tope por documento y recorrido completo, sin red."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
from zoneinfo import ZoneInfo

from licitaciones import bases
from licitaciones.errores import TopeGasto
from licitaciones.evaluacion import Presupuesto

ZONA = ZoneInfo("America/Santiago")
EV = {"modelo": "claude-haiku-5-5", "esfuerzo": "low", "tope_gasto_diario_usd": 3.0,
      "precios_usd_por_mtok": {"claude-haiku-5-5": {"entrada": 0.10, "salida": 0.50}},
      "contexto_largo": {"claude-haiku-5-5": {"umbral_tokens": 100000, "factor": 5}}}
CFG = {"modelo": "claude-haiku-5-5", "esfuerzo": "low", "max_tokens": 32000, "max_mb": 30, "max_por_corrida": 5,
       "tope_por_documento_usd": 0.80}
AJUSTES = {"horario": {"zona": "America/Santiago"}, "evaluacion": EV, "bases": CFG}


def material(**c):
    m = {"item": "Hormigón H-25 en losas", "material": "hormigon", "especificacion": "H-25", "cantidad": 12.5,
         "unidad": "m3", "pagina": 4, "confianza": "alta"}
    m.update(c)
    return m


class TestMaterial(unittest.TestCase):
    def test_conversion(self):
        self.assertEqual(bases.Material.model_validate(material()).base(), (12.5, "m3"))
        self.assertEqual(bases.Material.model_validate(material(cantidad=250.0, unidad="cm")).base(), (2.5, "m"))
        self.assertEqual(bases.Material.model_validate(material(cantidad=None, unidad=None)).base(), (None, None))

    def test_validar(self):
        self.assertIsNone(bases.validar(json.dumps({"materiales": [material()]}))[1])
        self.assertIsNotNone(bases.validar(json.dumps({"materiales": [material(unidad="gl")]}))[1])
        self.assertIsNotNone(bases.validar(json.dumps({"materiales": [material(precio=1)]}))[1])   # sin precios
        self.assertIsNotNone(bases.validar(json.dumps({"materiales": [material(cantidad=-1.0)]}))[1])

    def test_instrucciones_usan_nombres_conocidos(self):
        texto = bases.instrucciones({"cemento", "plancha yeso cartón"})
        self.assertIn("cemento, plancha yeso cartón", texto)
        self.assertIn("METROS LINEALES", texto)


class TestPresupuestoLargo(unittest.TestCase):
    def test_factor_sobre_umbral(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Presupuesto(AJUSTES, ZONA, carpeta=Path(tmp))
        corto = SimpleNamespace(input_tokens=50_000, output_tokens=1000)
        largo = SimpleNamespace(input_tokens=150_000, output_tokens=1000)
        self.assertAlmostEqual(p.costo(corto), 50_000 * 0.1e-6 + 1000 * 0.5e-6)
        self.assertAlmostEqual(p.costo(largo), 5 * (150_000 * 0.1e-6 + 1000 * 0.5e-6))
        self.assertAlmostEqual(p.peor_caso_tokens(150_000, 32000), 5 * (150_000 * 0.1e-6 + 32000 * 0.5e-6))


class Flujo:
    def __init__(self, mensaje):
        self.mensaje = mensaje

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get_final_message(self):
        return self.mensaje


class ClienteFalso:
    def __init__(self, tokens, texto):
        self.tokens, self.texto, self.pedidos = tokens, texto, []
        self.messages = self

    def count_tokens(self, **kw):
        return SimpleNamespace(input_tokens=self.tokens)

    def stream(self, **kw):
        self.pedidos.append(kw)
        return Flujo(SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=self.texto)],
                                     usage=SimpleNamespace(input_tokens=self.tokens, output_tokens=2000)))


class SupabaseFalso:
    """Registra las llamadas y responde lo mínimo para el recorrido."""
    def __init__(self, filas=None):
        self.filas, self.llamadas = filas or [], []
        self.sesion = SimpleNamespace(get=lambda url, timeout: SimpleNamespace(status_code=200, content=b"%PDF-1.4"))

    def _pedir(self, metodo, **kw):
        self.llamadas.append((metodo, kw))
        return SimpleNamespace(json=lambda: self.filas)


class TestProcesar(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = mock.patch.dict(os.environ, {"SUPABASE_URL": "https://x.supabase.co"})
        self.env.start()
        self.estado = mock.patch("licitaciones.evaluacion.ESTADO", Path(self.tmp.name))
        self.estado.start()

    def tearDown(self):
        self.estado.stop()
        self.env.stop()
        self.tmp.cleanup()

    def correr(self, base, cliente):
        sb_bases, sb_mat, sb_prec = SupabaseFalso([base]), SupabaseFalso(), SupabaseFalso([{"material": "hormigon"}])
        with mock.patch("licitaciones.evaluacion.Presupuesto.__init__.__defaults__", (Path(self.tmp.name),)):
            resumen = bases.procesar(AJUSTES, cliente=cliente, sb_bases=sb_bases, sb_materiales=sb_mat,
                                     sb_precios=sb_prec)
        return resumen, sb_bases, sb_mat

    def test_pdf_listo(self):
        base = {"id": 7, "codigo_externo": "1-1-LP26", "ruta": "1-1-LP26/bases.pdf", "bytes": 1000}
        cliente = ClienteFalso(40_000, json.dumps({"materiales": [material(), material(item="Acero A630", material="acero",
                                                                                         cantidad=800.0, unidad="kg")]}))
        resumen, sb_bases, sb_mat = self.correr(base, cliente)
        self.assertEqual((resumen["listos"], resumen["materiales"], resumen["con_error"]), (1, 2, 0))
        estados = [kw["json"].get("estado") for m, kw in sb_bases.llamadas if m == "PATCH"]
        self.assertEqual(estados, ["procesando", "listo"])
        metodos = [m for m, _ in sb_mat.llamadas]
        self.assertEqual(metodos, ["DELETE", "POST"])                      # reemplaza, no duplica
        insertadas = sb_mat.llamadas[1][1]["json"]
        self.assertEqual((insertadas[1]["cantidad_base"], insertadas[1]["unidad_base"]), (800.0, "kg"))
        self.assertIn("hormigon", cliente.pedidos[0]["system"])            # nombres conocidos en el prompt
        self.assertNotIn("precio", json.dumps(insertadas))

    def test_pdf_muy_largo_queda_en_error_sin_gastar(self):
        base = {"id": 8, "codigo_externo": "1-1-LP26", "ruta": "x.pdf", "bytes": 1000}
        cliente = ClienteFalso(2_000_000, "{}")   # peor caso US$ 1,08 > tope 0,80
        resumen, sb_bases, _ = self.correr(base, cliente)
        self.assertEqual(resumen["con_error"], 1)
        self.assertEqual(cliente.pedidos, [])
        error = [kw["json"] for m, kw in sb_bases.llamadas if m == "PATCH"][-1]
        self.assertEqual(error["estado"], "error")
        self.assertIn("muy largo", error["error"])

    def test_tope_de_gasto_devuelve_a_pendiente(self):
        base = {"id": 9, "codigo_externo": "1-1-LP26", "ruta": "x.pdf", "bytes": 1000}
        with mock.patch.object(Presupuesto, "verificar", side_effect=TopeGasto("tope")):
            with self.assertRaises(TopeGasto):
                self.correr(base, ClienteFalso(40_000, "{}"))


if __name__ == "__main__":
    unittest.main()
