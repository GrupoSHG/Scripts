"""Pruebas sin red: el ciclo de herramientas con un cliente falso, costos, topes y nombres de rama."""
import os
import unittest
from types import SimpleNamespace as NS
from unittest import mock

from agentes import __main__ as principal
from agentes import analista, desarrollador, perfiles


def uso(entrada=1000, salida=200):
    return NS(input_tokens=entrada, output_tokens=salida, cache_read_input_tokens=0, cache_creation_input_tokens=0)


class ClienteFalso:
    """Responde en orden la lista de mensajes que recibe y guarda cada pedido."""

    def __init__(self, respuestas):
        self.respuestas = list(respuestas)
        self.pedidos = []
        self.beta = NS(messages=NS(create=self._crear))

    def _crear(self, **kw):
        self.pedidos.append({**kw, "messages": list(kw["messages"])})
        return self.respuestas.pop(0)


def pide_sql(sql):
    return NS(stop_reason="tool_use", usage=uso(),
              content=[NS(type="tool_use", id="t1", name="consultar_sql", input={"sql": sql, "limite": 10})])


def termina(texto):
    return NS(stop_reason="end_turn", usage=uso(), content=[NS(type="text", text=texto)])


class CicloAnalista(unittest.TestCase):
    def test_consulta_y_responde(self):
        cliente = ClienteFalso([pide_sql("select 1"), termina("Vendimos $ 10.")])
        vistas = []
        consulta = lambda e: (vistas.append(e["sql"]) or '{"filas": [{"x": 1}]}', False)
        texto, usd, tokens, n = analista.responder(cliente, "comercial", "¿Cuánto vendimos?", 1.0, consulta=consulta)
        self.assertEqual(texto, "Vendimos $ 10.")
        self.assertEqual(vistas, ["select 1"])
        self.assertEqual(n, 1)
        self.assertAlmostEqual(usd, 2 * (1000 * 4 + 200 * 20) / 1e6)
        self.assertEqual(tokens["entrada"], 2000)
        segundo = cliente.pedidos[1]["messages"]
        self.assertEqual(segundo[-1]["content"][0]["tool_use_id"], "t1")
        self.assertEqual(cliente.pedidos[0]["model"], "claude-opus-5-5")
        self.assertIn("Analista Comercial", cliente.pedidos[0]["system"][0]["text"])

    def test_tope_por_instruccion(self):
        cliente = ClienteFalso([pide_sql("select 1")] * 5)
        cuenta = {"usd": 0.0}
        with self.assertRaises(analista.TopeGasto):
            analista.responder(cliente, "finanzas", "x", 0.001, consulta=lambda e: ("[]", False), cuenta=cuenta)
        self.assertGreater(cuenta["usd"], 0)

    def test_rechazo(self):
        cliente = ClienteFalso([NS(stop_reason="refusal", usage=uso(), content=[])])
        with self.assertRaises(analista.Rechazo):
            analista.responder(cliente, "planta", "x", 1.0, consulta=lambda e: ("[]", False))

    def test_resultado_largo_se_recorta(self):
        with mock.patch.object(analista.supabase, "consultar", return_value={"filas": ["a" * 50_000]}):
            texto, error = analista.ejecutar_consulta({"sql": "select 1", "limite": 1})
        self.assertFalse(error)
        self.assertLess(len(texto), analista.MAX_RESULTADO + 200)
        self.assertIn("recortado", texto)


class Varios(unittest.TestCase):
    def test_rama(self):
        self.assertEqual(desarrollador.rama(12, "Corregir el botón ¡YA! en Producción"), "agente/12-corregir-el-bot-n-ya-en-producci-n")
        self.assertEqual(desarrollador.rama(3, "!!!"), "agente/3-cambio")

    def test_topes(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(principal.topes("comercial"), (5.0, 1.5))
            self.assertEqual(principal.topes("dev"), (5.0, 3.0))
        with mock.patch.dict(os.environ, {"AGENTES_TOPE_DIARIO_USD": "2", "AGENTES_TOPE_INSTRUCCION_USD": "0.5"}):
            self.assertEqual(principal.topes("planta"), (2.0, 0.5))

    def test_agentes_conocidos(self):
        self.assertEqual(perfiles.AGENTES, {"comercial", "finanzas", "planta", "dev"})


if __name__ == "__main__":
    unittest.main()
