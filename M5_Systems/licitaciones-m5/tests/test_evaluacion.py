"""Validación del JSON de Claude, reintento, tope de gasto y costo, con un cliente falso (sin red)."""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from licitaciones.errores import ErrorConfig, TopeGasto
from licitaciones.evaluacion import Presupuesto, datos_para_modelo, evaluar_una, validar

ZONA = ZoneInfo("America/Santiago")
AJUSTES = {"evaluacion": {
    "modelo": "claude-haiku-5-5", "esfuerzo": "low", "max_tokens": 1000, "timeout_s": 10, "reintentos_sdk": 0,
    "tope_gasto_diario_usd": 1.0, "max_revision_manual_por_json": 3,
    "precios_usd_por_mtok": {"claude-haiku-5-5": {"entrada": 0.10, "salida": 0.50,
                                                  "cache_lectura": 0.01, "cache_escritura": 0.125}}}}
REGISTRO = {
    "codigo_externo": "2675-130-LP26", "nombre": "CONSTRUCCIÓN SEDE SOCIAL", "organismo": "Municipalidad",
    "region": "Región de O'Higgins", "monto_estimado_clp": 306412000.0,
    "fecha_cierre": "2026-11-18T15:00:00-03:00", "url_ficha": "https://example/ficha",
    "detalle": {"Descripcion": "Obra", "NombreResponsablePago": "No debe llegar",
                "Items": {"Listado": [{"Categoria": "Construcción", "NombreProducto": "Obras civiles"}]}},
}


def respuesta(**cambios):
    base = {"puntaje": 4, "motivo": "Edificación pública en región de interés", "tipo_de_obra": "edificación pública",
            "monto_estimado_clp": 306412000, "fecha_cierre": "2026-11-18T15:00:00-03:00",
            "requisitos_clave": [], "riesgos": ["bases no revisadas"], "recomendacion": "postular"}
    base.update(cambios)
    return json.dumps(base)


class TestValidar(unittest.TestCase):
    def test_valida(self):
        datos, error = validar(respuesta(), REGISTRO)
        self.assertIsNone(error)
        self.assertEqual(datos["puntaje"], 4)

    def test_no_es_json(self):
        self.assertIn("no es JSON", validar("puntaje: 4", REGISTRO)[1])
        self.assertIn("no es JSON", validar(None, REGISTRO)[1])

    def test_puntaje_fuera_de_rango_o_texto(self):
        self.assertIsNotNone(validar(respuesta(puntaje=6), REGISTRO)[1])
        self.assertIsNotNone(validar(respuesta(puntaje=0), REGISTRO)[1])
        self.assertIsNotNone(validar(respuesta(puntaje="5"), REGISTRO)[1])

    def test_recomendacion_invalida(self):
        self.assertIsNotNone(validar(respuesta(recomendacion="tal vez"), REGISTRO)[1])

    def test_campo_extra_o_faltante(self):
        self.assertIsNotNone(validar(respuesta(extra=1), REGISTRO)[1])
        datos = json.loads(respuesta())
        del datos["riesgos"]
        self.assertIsNotNone(validar(json.dumps(datos), REGISTRO)[1])

    def test_motivo_en_una_linea(self):
        self.assertIsNotNone(validar(respuesta(motivo="uno\ndos"), REGISTRO)[1])

    def test_fecha_no_iso(self):
        self.assertIsNotNone(validar(respuesta(fecha_cierre="18 de noviembre"), REGISTRO)[1])

    def test_monto_inventado_cuando_no_se_publica(self):
        sin_monto = {**REGISTRO, "monto_estimado_clp": None}
        self.assertIn("null", validar(respuesta(), sin_monto)[1])
        self.assertIsNone(validar(respuesta(monto_estimado_clp=None), sin_monto)[1])

    def test_monto_distinto_al_publicado(self):
        self.assertIn("no coincide", validar(respuesta(monto_estimado_clp=300000000), REGISTRO)[1])

    def test_fecha_inventada_o_distinta(self):
        self.assertIn("null", validar(respuesta(), {**REGISTRO, "fecha_cierre": None})[1])
        self.assertIn("no coincide", validar(respuesta(fecha_cierre="2026-11-20"), REGISTRO)[1])
        self.assertIsNone(validar(respuesta(fecha_cierre="2026-11-18"), REGISTRO)[1])

    def test_nulls_permitidos(self):
        sin_datos = {**REGISTRO, "monto_estimado_clp": None, "fecha_cierre": None}
        texto = respuesta(tipo_de_obra=None, monto_estimado_clp=None, fecha_cierre=None, recomendacion="revisar")
        self.assertIsNone(validar(texto, sin_datos)[1])


class TestDatosParaModelo(unittest.TestCase):
    def test_sin_datos_de_funcionarios(self):
        self.assertNotIn("No debe llegar", json.dumps(datos_para_modelo(REGISTRO), ensure_ascii=False))


def mensaje(texto, stop="end_turn", entrada=1000, salida=200):
    return SimpleNamespace(content=[SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text=texto)],
                           stop_reason=stop, _request_id="req_prueba",
                           usage=SimpleNamespace(input_tokens=entrada, output_tokens=salida,
                                                 cache_read_input_tokens=0, cache_creation_input_tokens=0))


class ClienteFalso:
    def __init__(self, *respuestas):
        self.respuestas = list(respuestas)
        self.pedidos = []
        self.messages = self

    def create(self, **kwargs):
        self.pedidos.append(kwargs)
        return self.respuestas.pop(0)


class TestEvaluarUna(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.presupuesto = Presupuesto(AJUSTES, ZONA, carpeta=Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def evaluar(self, *respuestas):
        self.cliente = ClienteFalso(*respuestas)
        return evaluar_una(self.cliente, REGISTRO, {"palabras_clave_incluir": ["obra"]}, AJUSTES, self.presupuesto)

    def test_ok_al_primer_intento(self):
        r = self.evaluar(mensaje(respuesta()))
        self.assertEqual((r["estado"], r["intentos"]), ("ok", 1))
        pedido = self.cliente.pedidos[0]
        self.assertEqual(pedido["model"], "claude-haiku-5-5")
        self.assertEqual(pedido["output_config"]["format"]["type"], "json_schema")

    def test_reintenta_una_vez_con_el_error(self):
        r = self.evaluar(mensaje(respuesta(puntaje=9)), mensaje(respuesta()))
        self.assertEqual((r["estado"], r["intentos"]), ("ok", 2))
        self.assertIn("no pasó la validación", self.cliente.pedidos[1]["messages"][0]["content"])

    def test_dos_fallos_quedan_para_revision_manual(self):
        r = self.evaluar(mensaje("no json"), mensaje(respuesta(monto_estimado_clp=1)))
        self.assertEqual((r["estado"], r["intentos"]), ("revisar_manualmente", 2))
        self.assertIsNone(r["evaluacion"])
        self.assertIn("no coincide", r["error"])

    def test_rechazo_no_se_reintenta(self):
        r = self.evaluar(mensaje("", stop="refusal"))
        self.assertEqual((r["estado"], r["intentos"]), ("revisar_manualmente", 1))

    def test_costo_y_tokens(self):
        r = self.evaluar(mensaje(respuesta(), entrada=10_000, salida=2_000))
        self.assertAlmostEqual(r["costo_usd"], 10_000 * 0.10e-6 + 2_000 * 0.50e-6)
        self.assertEqual(r["tokens"]["entrada"], 10_000)
        self.assertAlmostEqual(self.presupuesto.leer(), r["costo_usd"])

    def test_tope_de_gasto_detiene_antes_de_llamar(self):
        self.presupuesto.registrar(0.9999)
        with self.assertRaises(TopeGasto):
            self.evaluar(mensaje(respuesta()))
        self.assertEqual(self.cliente.pedidos, [])

    def test_modelo_sin_precio_es_error(self):
        otro = {"evaluacion": {**AJUSTES["evaluacion"], "modelo": "modelo-sin-precio"}}
        with self.assertRaises(ErrorConfig):
            Presupuesto(otro, ZONA)


class TestSeparar(unittest.TestCase):
    def test_conserva_postular_revisar_y_manual(self):
        from licitaciones.evaluacion import separar
        res = [{"codigo_externo": c, "nombre": c, "url_ficha": None,
                "evaluacion": None if rec is None else {"puntaje": 3, "recomendacion": rec, "motivo": "m"}}
               for c, rec in (("a", "postular"), ("b", "revisar"), ("c", "descartar"), ("d", None))]
        conservadas, descartadas = separar(res, AJUSTES)
        self.assertEqual([r["codigo_externo"] for r in conservadas], ["a", "b", "d"])
        self.assertEqual([(r["codigo_externo"], r["evaluacion"]["recomendacion"]) for r in descartadas],
                         [("c", "descartar")])


if __name__ == "__main__":
    unittest.main()
