import unittest

from licitaciones.errores import ErrorConfig
from licitaciones.filtro import Filtro, normalizar

AJUSTES = {"filtro": {"prefijos_rubro_unspsc": ["7211", "7214"]}}
PERFIL = {
    "palabras_clave_incluir": ["construcción", "pavimentación", "obras civiles"],
    "tipos_de_obra_que_interesan": ["galpón"],
    "palabras_clave_excluir": ["adquisición", "diseño"],
    "tipos_de_obra_que_descartan": ["piscina"],
    "regiones_de_interes": ["Metropolitana", "O'Higgins"],
    "monto_minimo_clp": 50_000_000,
    "monto_maximo_clp": 2_000_000_000,
    "organismos_prioritarios": ["Municipalidad de Rancagua"],
}


def detalle(nombre="Construcción de sede social", descripcion="", items=(), region="Región Metropolitana de Santiago",
            monto=None, visibilidad=1, moneda="CLP", organismo="Municipalidad de Maipú"):
    return {"Nombre": nombre, "Descripcion": descripcion, "MontoEstimado": monto, "VisibilidadMonto": visibilidad,
            "Moneda": moneda, "Comprador": {"RegionUnidad": region, "NombreOrganismo": organismo},
            "Items": {"Listado": list(items)}}


class TestNormalizar(unittest.TestCase):
    def test_tildes_mayusculas_y_puntuacion(self):
        self.assertEqual(normalizar("  PAVIMENTACIÓN,  Calle O´Higgins "), "pavimentacion calle o higgins")


class TestPorNombre(unittest.TestCase):
    def setUp(self):
        self.f = Filtro(PERFIL, AJUSTES)

    def test_incluye_sin_tildes_y_plural(self):
        pasa, claves = self.f.por_nombre("CONSTRUCCION DE GALPONES MUNICIPALES")
        self.assertTrue(pasa)
        self.assertEqual(claves, ["construcción", "galpón"])

    def test_desde_inicio_de_palabra(self):
        # "reconstruccion" no empieza con "construccion"
        self.assertFalse(self.f.por_nombre("Reconstrucción de muro")[0])

    def test_exclusion_gana(self):
        pasa, motivo = self.f.por_nombre("Adquisición de materiales de construcción")
        self.assertFalse(pasa)
        self.assertIn("adquisición", motivo)

    def test_tipo_de_obra_descartado(self):
        self.assertFalse(self.f.por_nombre("Construcción de piscina temperada")[0])

    def test_sin_coincidencias(self):
        self.assertEqual(self.f.por_nombre("Servicio de aseo"), (False, "sin palabras clave en el nombre"))

    def test_perfil_vacio_es_error(self):
        with self.assertRaises(ErrorConfig):
            Filtro({"palabras_clave_incluir": [], "tipos_de_obra_que_interesan": None}, AJUSTES)


class TestPorDetalle(unittest.TestCase):
    def setUp(self):
        self.f = Filtro(PERFIL, AJUSTES)

    def test_palabra_en_descripcion(self):
        pasa, claves = self.f.por_detalle(detalle(nombre="Mejoramiento plaza", descripcion="Incluye obras civiles"))
        self.assertTrue(pasa)
        self.assertEqual(claves, ["obras civiles"])

    def test_rubro_unspsc_basta(self):
        items = [{"NombreProducto": "Servicio", "CodigoCategoria": 72141100}]
        pasa, claves = self.f.por_detalle(detalle(nombre="Mejoramiento plaza", items=items))
        self.assertTrue(pasa)
        self.assertIn("rubro construcción (UNSPSC 72)", claves)

    def test_exclusion_solo_en_nombre(self):
        # La palabra excluida en la descripción no descarta; en el nombre sí.
        self.assertTrue(self.f.por_detalle(detalle(descripcion="no incluye diseño"))[0])
        self.assertFalse(self.f.por_detalle(detalle(nombre="Diseño y construcción de sede"))[0])

    def test_region_fuera_de_perfil(self):
        pasa, motivo = self.f.por_detalle(detalle(region="Región de Magallanes y de la Antártica Chilena"))
        self.assertFalse(pasa)
        self.assertIn("región", motivo)

    def test_region_con_apostrofe_distinto(self):
        self.assertTrue(self.f.por_detalle(detalle(region="Región del Libertador General Bernardo O´Higgins"))[0])

    def test_region_vacia_no_descarta(self):
        self.assertTrue(self.f.por_detalle(detalle(region=""))[0])

    def test_monto_fuera_de_rango(self):
        self.assertFalse(self.f.por_detalle(detalle(monto=10_000_000))[0])
        self.assertFalse(self.f.por_detalle(detalle(monto=5_000_000_000))[0])
        self.assertTrue(self.f.por_detalle(detalle(monto=300_000_000))[0])

    def test_monto_no_publicado_u_otra_moneda_no_descarta(self):
        self.assertTrue(self.f.por_detalle(detalle(monto=10_000_000, visibilidad=0))[0])
        self.assertTrue(self.f.por_detalle(detalle(monto=10, moneda="UF"))[0])

    def test_organismo_prioritario(self):
        self.assertTrue(self.f.organismo_prioritario(detalle(organismo="I. MUNICIPALIDAD DE RANCAGUA")))
        self.assertFalse(self.f.organismo_prioritario(detalle()))


if __name__ == "__main__":
    unittest.main()
