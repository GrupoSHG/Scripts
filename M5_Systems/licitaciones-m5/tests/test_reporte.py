"""Reporte diario sin red: secciones, ventana de cierre, descartadas fuera y HTML escapado."""
import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from licitaciones.reporte import armar, generar, html_reporte, texto

ZONA = ZoneInfo("America/Santiago")
AHORA = datetime(2026, 10, 19, 23, 0, tzinfo=ZONA)
AJUSTES = {"horario": {"zona": "America/Santiago"}, "reporte": {"dias_cierre": 7, "max_mejores": 2}}


def evaluada(codigo, puntaje, rec, dias, nombre=None, estado="ok"):
    return {"codigo_externo": codigo, "nombre": nombre or f"Obra {codigo}", "organismo": "Muni", "region": "RM",
            "fecha_cierre": (AHORA + timedelta(days=dias)).isoformat(), "monto_estimado_clp": 1000000.0,
            "url_ficha": f"https://ficha/{codigo}", "estado": estado, "error": "no es JSON" if estado != "ok" else None,
            "evaluacion": None if estado != "ok" else {"puntaje": puntaje, "recomendacion": rec, "motivo": "m",
                                                        "riesgos": ["bases no revisadas"]}}


class SupabaseFalso:
    def __init__(self, filas):
        self.filas = filas
        self.pedidos = []

    def cierran_entre(self, desde, hasta):
        self.pedidos.append((desde, hasta))
        return self.filas


class TestReporte(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.carpeta = Path(self.tmp.name)
        hoy = [evaluada("a", 5, "postular", 3), evaluada("b", 3, "revisar", 20), evaluada("c", 4, "revisar", 1),
               evaluada("m", None, None, 2, estado="revisar_manualmente")]
        (self.carpeta / "evaluadas.json").write_text(json.dumps(hoy), encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_secciones_solo_con_lo_del_dia(self):
        d = armar(AJUSTES, self.carpeta, ahora=AHORA)
        self.assertEqual([x["codigo"] for x in d["mejores"]], ["a", "c"])          # por puntaje, máx. 2
        self.assertEqual([x["codigo"] for x in d["cierran"]], ["c", "m", "a"])     # ≤ 7 días, por fecha; "b" (20 días) no
        self.assertEqual([x["codigo"] for x in d["manual"]], ["m"])
        self.assertEqual(d["fuente_cierre"], "las evaluadas hoy")

    def test_cierran_suma_supabase_sin_descartadas(self):
        filas = [{"codigo_externo": "s1", "nombre": "De la tabla", "fecha_cierre": (AHORA + timedelta(days=5)).isoformat(),
                  "monto_estimado": None, "url_ficha": "u", "puntaje": None, "recomendacion": None},
                 {"codigo_externo": "s2", "nombre": "Descartada", "fecha_cierre": (AHORA + timedelta(days=4)).isoformat(),
                  "url_ficha": "u", "puntaje": 1, "recomendacion": "descartar"},
                 {"codigo_externo": "a", "nombre": "Repetida", "fecha_cierre": (AHORA + timedelta(days=3)).isoformat(),
                  "url_ficha": "u", "puntaje": 5, "recomendacion": "postular"}]
        sb = SupabaseFalso(filas)
        d = armar(AJUSTES, self.carpeta, sb=sb, ahora=AHORA)
        codigos = [x["codigo"] for x in d["cierran"]]
        self.assertNotIn("s1", codigos)                       # sin evaluar: va a la lista compacta
        self.assertEqual([x["codigo"] for x in d["sin_evaluar"]], ["s1"])
        self.assertIn("s1", html_reporte(d))
        self.assertNotIn("s2", codigos)
        self.assertEqual(codigos.count("a"), 1)
        self.assertEqual(d["fuente_cierre"], "todas las guardadas en Supabase")
        self.assertEqual(len(sb.pedidos), 1)

    def test_html_escapa_y_enlaza(self):
        hoy = [evaluada("x", 5, "postular", 2, nombre='<script>alert("x")</script> & obra')]
        (self.carpeta / "evaluadas.json").write_text(json.dumps(hoy), encoding="utf-8")
        h = html_reporte(armar(AJUSTES, self.carpeta, ahora=AHORA))
        self.assertNotIn("<script>alert", h)
        self.assertIn("&lt;script&gt;", h)
        self.assertIn('href="https://ficha/x"', h)
        self.assertIn("prefers-color-scheme:dark", h)

    def test_texto(self):
        t = texto(armar(AJUSTES, self.carpeta, ahora=AHORA))
        self.assertIn("MEJORES DEL DÍA (2)", t)
        self.assertIn("[5] postular · a · Obra a", t)
        self.assertIn("[?] revisar a mano · m", t)
        self.assertIn("https://ficha/a", t)

    def test_generar_escribe_archivos_sin_supabase(self):
        ruta_html, ruta_txt, _ = generar(AJUSTES, self.carpeta, usar_supabase=False)
        self.assertTrue(ruta_html.is_file() and ruta_txt.is_file())


if __name__ == "__main__":
    unittest.main()
