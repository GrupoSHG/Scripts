"""Cliente de la API con una sesión falsa: sin red ni ticket real."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import requests

from licitaciones.config import enmascarar
from licitaciones.detalle import sanitizar
from licitaciones.errores import ErrorAPI, LimiteSolicitudes
from licitaciones.mp_api import Contador, MercadoPublico

TICKET = "TICKET-DE-PRUEBA-1234"
AJUSTES = {
    "api": {"base": "https://api.example/", "timeout_conexion_s": 1, "timeout_lectura_s": 1, "reintentos": 2,
            "espera_base_s": 1, "espera_maxima_s": 5, "pausa_entre_llamadas_s": 0},
    "limites": {"solicitudes_diarias": 10, "tope_pct": 80},
    "horario": {"zona": "America/Santiago"},
}


class Respuesta:
    def __init__(self, status, cuerpo, headers=None):
        self.status_code = status
        self.content = (json.dumps(cuerpo) if not isinstance(cuerpo, str) else cuerpo).encode("utf-8")
        self.headers = headers or {}


class Sesion:
    def __init__(self, *respuestas):
        self.respuestas = list(respuestas)
        self.headers = {}
        self.llamadas = 0

    def get(self, url, params, timeout):
        self.llamadas += 1
        assert params["ticket"] == TICKET and timeout
        r = self.respuestas.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


class TestCliente(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.esperas = []

    def tearDown(self):
        self.tmp.cleanup()

    def cliente(self, *respuestas):
        contador = Contador(AJUSTES, carpeta=Path(self.tmp.name))
        return MercadoPublico(AJUSTES, ticket=TICKET, sesion=Sesion(*respuestas), contador=contador,
                              dormir=self.esperas.append)

    def test_ok(self):
        mp = self.cliente(Respuesta(200, {"Cantidad": 1, "Listado": [{"CodigoExterno": "1-1-LP26"}]}))
        self.assertEqual(mp.detalle("1-1-LP26"), {"CodigoExterno": "1-1-LP26"})
        self.assertEqual(mp.contador.leer(), 1)

    def test_403_corta_sin_reintentar(self):
        mp = self.cliente(Respuesta(403, "Forbidden"))
        with self.assertRaises(ErrorAPI) as e:
            mp.listado(fecha="19102026")
        self.assertEqual((e.exception.http, e.exception.fatal), (403, True))
        self.assertEqual(mp.sesion.llamadas, 1)

    def test_ticket_invalido_203(self):
        mp = self.cliente(Respuesta(203, {"Codigo": 203, "Mensaje": "Ticket no válido."}))
        with self.assertRaises(ErrorAPI) as e:
            mp.listado(fecha="19102026")
        self.assertTrue(e.exception.fatal)
        self.assertIn("Ticket no válido", str(e.exception))

    def test_429_reintenta_con_espera_creciente_y_luego_corta(self):
        mp = self.cliente(*[Respuesta(429, "Too Many Requests")] * 3)
        with self.assertRaises(ErrorAPI) as e:
            mp.detalle("1-1-LP26")
        self.assertEqual((e.exception.http, e.exception.fatal), (429, True))
        self.assertEqual(mp.sesion.llamadas, 3)  # 1 + 2 reintentos, nunca infinito
        self.assertEqual(len(self.esperas), 2)
        self.assertLess(self.esperas[0], self.esperas[1])
        self.assertEqual(mp.respuestas[429], 3)

    def test_retry_after_con_tope(self):
        mp = self.cliente(Respuesta(429, "", {"Retry-After": "120"}), Respuesta(200, {"Listado": []}))
        mp.listado(fecha="19102026")
        self.assertEqual(self.esperas[0], 5)

    def test_5xx_y_timeout_se_recuperan(self):
        mp = self.cliente(Respuesta(503, ""), requests.Timeout("timeout url ?ticket=" + TICKET),
                          Respuesta(200, {"Listado": [{"CodigoExterno": "x"}]}))
        self.assertEqual(mp.detalle("x"), {"CodigoExterno": "x"})

    def test_peticiones_simultaneas_10500_se_reintenta(self):
        mp = self.cliente(Respuesta(200, {"Codigo": 10500, "Mensaje": "peticiones simultáneas"}),
                          Respuesta(200, {"Listado": []}))
        self.assertEqual(mp.listado(fecha="19102026"), [])

    def test_404_no_es_fatal(self):
        mp = self.cliente(Respuesta(404, "no existe"))
        with self.assertRaises(ErrorAPI) as e:
            mp.detalle("x")
        self.assertFalse(e.exception.fatal)

    def test_mensajes_nunca_traen_el_ticket(self):
        mp = self.cliente(*[requests.ConnectionError("Max retries exceeded with url: /x?ticket=" + TICKET)] * 3)
        with self.assertRaises(ErrorAPI) as e:
            mp.detalle("x")
        self.assertNotIn(TICKET, str(e.exception))

    def test_tope_diario(self):
        mp = self.cliente(*[Respuesta(200, {"Listado": []})] * 10)
        for _ in range(8):  # 80 % de 10
            mp.listado(fecha="19102026")
        with self.assertRaises(LimiteSolicitudes):
            mp.listado(fecha="19102026")


class TestEnmascarar(unittest.TestCase):
    def test_parametros_y_valores_de_entorno(self):
        with mock.patch.dict(os.environ, {"MP_TICKET": TICKET, "ANTHROPIC_API_KEY": "clave-anthropic-de-prueba"}):
            texto = enmascarar(f"GET /licitaciones.json?codigo=1&ticket={TICKET} key=abc Bearer xyz.123 clave-anthropic-de-prueba")
        self.assertNotIn(TICKET, texto)
        self.assertNotIn("clave-anthropic-de-prueba", texto)
        self.assertNotIn("abc", texto)
        self.assertNotIn("xyz.123", texto)
        self.assertIn("codigo=1", texto)


class TestSanitizar(unittest.TestCase):
    def test_lista_blanca(self):
        det = {"CodigoExterno": "1-1-LP26", "Nombre": "Obra", "NombreResponsablePago": "Persona",
               "EmailResponsableContrato": "x@y.cl",
               "Comprador": {"NombreOrganismo": "Muni", "NombreUsuario": "Persona", "RutUsuario": "1-9"},
               "Items": {"Cantidad": 1, "Listado": [{"NombreProducto": "Obra", "Adjudicacion": {"RutProveedor": "1-9"}}]}}
        limpio, descartados = sanitizar(det)
        texto = json.dumps(limpio)
        self.assertNotIn("Persona", texto)
        self.assertNotIn("1-9", texto)
        self.assertNotIn("x@y.cl", texto)
        self.assertEqual(limpio["Comprador"], {"NombreOrganismo": "Muni"})
        self.assertIn("Comprador.NombreUsuario", descartados)
        self.assertIn("Items.Listado[].Adjudicacion", descartados)


if __name__ == "__main__":
    unittest.main()
