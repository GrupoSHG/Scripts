"""Obras adjudicadas: filtro, adjudicatarios sin personas naturales y flujo con API y Supabase falsas (sin red)."""
import json
import unittest
from zoneinfo import ZoneInfo

from licitaciones.adjudicadas import adjudicatarios, ejecutar, es_empresa, fila, por_nombre
from licitaciones.errores import ErrorAPI

ZONA = ZoneInfo("America/Santiago")
AJUSTES = {"adjudicadas": {"activo": True, "dias": 2, "max_detalles_noche": 10},
           "horario": {"carga_masiva_desde": "00:00", "carga_masiva_hasta": "23:59", "max_detalles_fuera_de_horario": 1}}


def item(rut, nombre, cantidad, unitario, categoria="72101500"):
    return {"Correlativo": 1, "CodigoCategoria": categoria, "NombreProducto": "x",
            "Adjudicacion": {"RutProveedor": rut, "NombreProveedor": nombre, "Cantidad": cantidad,
                             "MontoUnitario": unitario}}


def detalle(codigo="1-1-LE26", items=None, estado=8):
    return {"CodigoExterno": codigo, "Nombre": "Construcción de galpón", "CodigoEstado": estado, "Tipo": "LE",
            "Moneda": "CLP", "MontoEstimado": 100.0, "VisibilidadMonto": 1,
            "Comprador": {"NombreOrganismo": "Muni", "RegionUnidad": "RM", "NombreUsuario": "Funcionario"},
            "Fechas": {"FechaAdjudicacion": "2026-10-27T20:53:13.667"},
            "Adjudicacion": {"Fecha": "2026-10-27T00:00:00", "NumeroOferentes": 3, "UrlActa": "http://acta"},
            "EmailResponsableContrato": "a@b.cl",
            "Items": {"Listado": items if items is not None else [item("76.009.662-8", "Constructora SpA", 2, 50)]}}


class TestFiltro(unittest.TestCase):
    def test_nombre(self):
        self.assertIn("galpon", por_nombre("CONSTRUCCIÓN GALPÓN MUNICIPAL"))
        self.assertTrue(por_nombre("Reposición techumbre escuela"))
        self.assertEqual(por_nombre("Diseño proyecto de construcción de veredas"), [])
        self.assertEqual(por_nombre("Compra de medicamentos"), [])

    def test_empresa_por_rut(self):
        self.assertTrue(es_empresa("76.009.662-8"))
        self.assertFalse(es_empresa("12.345.678-9"))
        self.assertFalse(es_empresa(""))


class TestFila(unittest.TestCase):
    def test_persona_natural_sin_nombre_ni_rut(self):
        g = adjudicatarios([item("12.345.678-9", "Juan Pérez", 1, 10), item("76.009.662-8", "Constructora SpA", 1, 30),
                            item("76.009.662-8", "Constructora SpA", 2, 5)])
        self.assertEqual(g[0], {"rut": "76.009.662-8", "nombre": "Constructora SpA", "monto": 40.0, "items": 2})
        self.assertEqual(g[1], {"rut": None, "nombre": "Persona natural", "monto": 10.0, "items": 1})
        self.assertNotIn("Juan", json.dumps(g, ensure_ascii=False))

    def test_campos_y_rubro(self):
        f = fila(detalle(), ["galpon"], ZONA, "2026-10-28T22:30:00-03:00")
        self.assertEqual((f["monto_adjudicado"], f["proveedor_principal"], f["numero_oferentes"]),
                         (100.0, "Constructora SpA", 3))
        self.assertTrue(f["es_obra"])
        self.assertTrue(f["fecha_adjudicacion"].startswith("2026-10-27T20:53:13"))
        texto = json.dumps(f, ensure_ascii=False)
        self.assertNotIn("a@b.cl", texto)
        self.assertNotIn("Funcionario", texto)
        sin_rubro = fila(detalle(items=[item("76.009.662-8", "X", 1, 1, categoria="46191500")]), ["mejoramiento"], ZONA, "")
        self.assertFalse(sin_rubro["es_obra"])

    def test_sin_adjudicatarios(self):
        f = fila(detalle(items=[]), ["obra"], ZONA, "")
        self.assertIsNone(f["monto_adjudicado"])
        self.assertEqual(f["adjudicatarios"], [])


class Contador:
    zona = ZONA


class MP:
    def __init__(self, listados, detalles):
        self.listados, self.detalles, self.contador, self.hechas, self.pedidos = listados, detalles, Contador(), 0, []

    def listado(self, fecha=None, estado=None):
        self.hechas += 1
        return self.listados.pop(0) if self.listados else []

    def detalle(self, codigo):
        self.hechas += 1
        self.pedidos.append(codigo)
        r = self.detalles[codigo]
        if isinstance(r, Exception):
            raise r
        return r


class Respuesta:
    def __init__(self, datos):
        self.datos = datos

    def json(self):
        return self.datos


class SB:
    def __init__(self, guardadas=()):
        self.guardadas, self.subidas = [{"codigo_externo": c} for c in guardadas], []

    def _pedir(self, metodo, **kw):
        return Respuesta(self.guardadas)

    def upsert(self, filas):
        self.subidas += filas
        return len(filas)


def lic(codigo, nombre="Construcción sede social", estado=8):
    return {"CodigoExterno": codigo, "Nombre": nombre, "CodigoEstado": estado}


class TestEjecutar(unittest.TestCase):
    def test_flujo(self):
        mp = MP([[lic("A"), lic("B"), lic("C", "Compra de alimentos"), lic("D", estado=6)], [lic("A"), lic("E")]],
                {"B": detalle("B"), "E": ErrorAPI("caída", fatal=False)})
        sb = SB(guardadas=["A"])
        r = ejecutar(AJUSTES, sb, mp=mp)
        self.assertEqual(mp.pedidos, ["B", "E"])  # A ya guardada, C no pasa el nombre, D no está adjudicada
        self.assertEqual([f["codigo_externo"] for f in sb.subidas], ["B"])
        self.assertEqual((r["listado"], r["pasan_nombre"], r["detalles"], r["errores_detalle"], r["obras"]),
                         (6, 2, 1, 1, 1))

    def test_tope_fuera_de_ventana(self):
        ajustes = {**AJUSTES, "horario": {"carga_masiva_desde": "23:59", "carga_masiva_hasta": "00:00",
                                          "max_detalles_fuera_de_horario": 1}}
        mp = MP([[lic("A"), lic("B")]], {"A": detalle("A"), "B": detalle("B")})
        r = ejecutar(ajustes, SB(), mp=mp, dias=1)
        self.assertEqual((mp.pedidos, r["pendientes"]), (["A"], 1))

    def test_error_fatal_corta(self):
        mp = MP([[lic("A")]], {"A": ErrorAPI("403", http=403)})
        with self.assertRaises(ErrorAPI):
            ejecutar(AJUSTES, SB(), mp=mp, dias=1)

    def test_inactivo(self):
        self.assertEqual(ejecutar({"adjudicadas": {"activo": False}}, sb=None), {"activo": False})


if __name__ == "__main__":
    unittest.main()
