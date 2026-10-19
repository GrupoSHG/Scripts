"""Supabase con una sesión falsa (sin red) y el JWT de generar_clave_supabase.py."""
import base64
import hashlib
import hmac
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from licitaciones.supabase_mp import ErrorSupabase, Supabase, fila, guardar

AJUSTES = {"supabase": {"esquema": "m5", "timeout_s": 5, "apikey_publica": "clave-publica"},
           "horario": {"zona": "America/Santiago"}, "evaluacion": {"modelo": "claude-haiku-5-5"},
           "estados": {5: "Publicada", 8: "Adjudicada"}}
ENTORNO = {"SUPABASE_URL": "https://proyecto.supabase.co", "SUPABASE_KEY": "jwt-de-prueba-123456"}
REGISTRO = {"codigo_externo": "1-1-LP26", "nombre": "Obra", "organismo": "Muni", "region": "RM", "comuna": "X",
            "codigo_estado": 5, "estado": "Publicada", "tipo": "LP", "fecha_publicacion": None,
            "fecha_cierre": "2026-11-18T15:00:00-03:00", "monto_estimado_clp": 1000.0, "url_ficha": "u",
            "coincidencias": ["obra"], "detalle": {"Moneda": "CLP"}}
EVAL = {"codigo_externo": "1-1-LP26", "estado": "ok", "error": None,
        "evaluacion": {"puntaje": 4, "recomendacion": "revisar", "motivo": "m", "tipo_de_obra": "edificación",
                       "monto_estimado_clp": 1000, "fecha_cierre": None, "requisitos_clave": [], "riesgos": ["r"]}}


class Respuesta:
    def __init__(self, status=200, datos=None):
        self.status_code = status
        self.datos = datos if datos is not None else []
        self.text = json.dumps(self.datos)

    def json(self):
        return self.datos


class Sesion:
    def __init__(self, *respuestas):
        self.headers = {}
        self.pedidos = []
        self.respuestas = list(respuestas)

    def request(self, metodo, url, timeout, **kw):
        self.pedidos.append((metodo, url, kw))
        return self.respuestas.pop(0) if self.respuestas else Respuesta()


class TestSupabase(unittest.TestCase):
    def cliente(self, *respuestas):
        with mock.patch.dict(os.environ, ENTORNO):
            return Supabase(AJUSTES, sesion=Sesion(*respuestas))

    def test_encabezados(self):
        sb = self.cliente()
        h = sb.sesion.headers
        self.assertEqual(h["apikey"], "clave-publica")
        self.assertEqual(h["Authorization"], "Bearer jwt-de-prueba-123456")
        self.assertEqual((h["Accept-Profile"], h["Content-Profile"]), ("m5", "m5"))
        self.assertEqual(sb.url, "https://proyecto.supabase.co/rest/v1/licitaciones_mp")

    def test_fila(self):
        f = fila(EVAL, REGISTRO, "claude-haiku-5-5", "2026-10-19T13:00:00-03:00")
        self.assertEqual((f["puntaje"], f["recomendacion"], f["monto_estimado"], f["palabras_clave"]),
                         (4, "revisar", 1000.0, ["obra"]))
        self.assertNotIn("detalle", f)
        self.assertNotIn("fecha_captura", f)  # la conserva el default de la tabla en la primera inserción

    def test_fila_revision_manual(self):
        f = fila({"codigo_externo": "1-1-LP26", "estado": "revisar_manualmente", "evaluacion": None,
                  "error": "no es JSON"}, REGISTRO, "m", "t")
        self.assertEqual((f["puntaje"], f["estado_evaluacion"], f["motivo"]), (None, "revisar_manualmente", "no es JSON"))

    def test_error_401_sin_exponer_la_clave(self):
        sb = self.cliente(Respuesta(401, {"message": "JWT invalid jwt-de-prueba-123456"}))
        with mock.patch.dict(os.environ, ENTORNO), self.assertRaises(ErrorSupabase) as e:
            sb.upsert([{"codigo_externo": "x"}])
        self.assertIn("401", str(e.exception))
        self.assertNotIn("jwt-de-prueba-123456", str(e.exception))

    def test_guardar_sube_y_actualiza_estados(self):
        with tempfile.TemporaryDirectory() as tmp:
            c = Path(tmp)
            (c / "filtradas.json").write_text(json.dumps([REGISTRO]), encoding="utf-8")
            (c / "evaluadas.json").write_text(json.dumps([EVAL]), encoding="utf-8")
            (c / "descartadas_claude.json").write_text("[]", encoding="utf-8")
            (c / "listado.json").write_text(json.dumps([
                {"CodigoExterno": "1-1-LP26", "CodigoEstado": 5},             # recién subida: no se toca
                {"CodigoExterno": "9-9-LP26", "CodigoEstado": 8, "FechaCierre": None},  # ya guardada, cambió
                {"CodigoExterno": "7-7-LP26", "CodigoEstado": 8}]), encoding="utf-8")  # no está en la tabla
            sb = self.cliente(Respuesta(201), Respuesta(200, [{"codigo_externo": "1-1-LP26", "codigo_estado": 5},
                                                                {"codigo_externo": "9-9-LP26", "codigo_estado": 5}]))
            resumen = guardar(AJUSTES, c, sb=sb)
        self.assertEqual(resumen, {"subidas": 1, "estados_actualizados": 1, "en_tabla": 2})
        metodo, _, kw = sb.sesion.pedidos[0]
        self.assertEqual((metodo, kw["params"]["on_conflict"]), ("POST", "codigo_externo"))
        metodo, _, kw = sb.sesion.pedidos[2]
        self.assertEqual((metodo, kw["params"], kw["json"]["codigo_estado"], kw["json"]["estado"]),
                         ("PATCH", {"codigo_externo": "eq.9-9-LP26"}, 8, "Adjudicada"))


class TestGenerarClave(unittest.TestCase):
    def test_jwt_hs256_con_rol_minimo(self):
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        import generar_clave_supabase as g
        secret = "x" * 40
        token = g.firmar(secret, 1)
        cab, cuerpo, firma = token.split(".")
        relleno = lambda s: s + "=" * (-len(s) % 4)
        datos = json.loads(base64.urlsafe_b64decode(relleno(cuerpo)))
        self.assertEqual((datos["role"], datos["ref"], datos["iss"]), ("licitaciones_m5", g.PROYECTO, "supabase"))
        esperada = hmac.new(secret.encode(), f"{cab}.{cuerpo}".encode(), hashlib.sha256).digest()
        self.assertEqual(base64.urlsafe_b64decode(relleno(firma)), esperada)


if __name__ == "__main__":
    unittest.main()
