"""Precios desde órdenes de compra: filtro, lista blanca y calidad de los ítems (sin red)."""
import json
import unittest

from licitaciones.precios_oc import calidad, es_de_materiales, resumir, sanitizar, unidad_en_texto


def item(esp, cantidad=10, precio=4500, producto="Cementos", moneda="CLP"):
    return {"especificacion_comprador": esp, "producto": producto, "cantidad": cantidad, "precio_neto": precio,
            "moneda": moneda, "unidad": None}


class TestFiltro(unittest.TestCase):
    def test_materiales_si_servicios_no(self):
        self.assertTrue(es_de_materiales("ADQUISICIÓN DE MATERIALES DE CONSTRUCCIÓN PARA SEDE"))
        self.assertTrue(es_de_materiales("Compra de cemento y fierro"))
        self.assertFalse(es_de_materiales("Servicio de instalación de paneles"))
        self.assertFalse(es_de_materiales("Compra de medicamentos"))


class TestSanitizar(unittest.TestCase):
    def test_sin_contactos_ni_proveedor(self):
        oc = {"Codigo": "1-1-SE26", "Nombre": "Materiales", "CodigoEstado": 6, "Estado": "Aceptada",
              "Comprador": {"NombreOrganismo": "Muni", "NombreContacto": "Persona", "MailContacto": "a@b.cl",
                            "FonoContacto": "+56 9 1234"},
              "Proveedor": {"Nombre": "Juan Pérez", "RutSucursal": "11.111.111-1", "Region": "RM",
                            "NombreContacto": "Persona"},
              "Items": {"Listado": [{"Producto": "Cemento", "Cantidad": 2, "PrecioNeto": 4500, "Moneda": "CLP"}]}}
        texto = json.dumps(sanitizar(oc), ensure_ascii=False)
        for dato in ("Persona", "a@b.cl", "1234", "Juan Pérez", "11.111.111-1"):
            self.assertNotIn(dato, texto)
        self.assertIn("Muni", texto)


class TestCalidad(unittest.TestCase):
    def test_clases(self):
        self.assertEqual(calidad(item("Saco de cemento 25 kg")), "con_unidad")
        self.assertEqual(calidad(item("Arena intermedia")), "sin_unidad")
        self.assertEqual(calidad(item("Instalación de cerámica, global", cantidad=1)), "global")
        self.assertEqual(calidad(item("Saco", precio=0)), "sin_precio")
        self.assertEqual(calidad(item("Saco", moneda="USD")), "otra_moneda")

    def test_unidad_en_texto(self):
        self.assertEqual(unidad_en_texto(item("PLANCHA YESO CARTON 15MM")), "plancha")
        self.assertIsNone(unidad_en_texto(item("Gravilla", producto="Esparcidoras de gravilla")))

    def test_resumen_agrupa_solo_con_unidad(self):
        r = resumir([{"items": [item("Saco de cemento"), item("Saco de cemento", precio=5500), item("Arena")]}])
        self.assertEqual(r["calidad"], {"con_unidad": 2, "sin_unidad": 1})
        self.assertEqual((r["productos"][0]["n"], r["productos"][0]["mediana"]), (2, 5000))


class TestTabla(unittest.TestCase):
    def test_fila_tabla_zona_y_modelo(self):
        from licitaciones.precios_oc import COLUMNAS, fila_tabla
        f = {c: None for c in COLUMNAS}
        f.update(oc="1-1-SE26", correlativo=1, fecha_envio="2026-10-22T10:30:00", extra="no va")
        fila = fila_tabla(f, "claude-haiku-5-5")
        self.assertEqual(fila["fecha_envio"], "2026-10-22T10:30:00-03:00")
        self.assertEqual(fila["modelo"], "claude-haiku-5-5")
        self.assertNotIn("extra", fila)

    def test_nocturno_inactivo_no_hace_nada(self):
        from licitaciones.precios_oc import nocturno
        self.assertEqual(nocturno({"precios_oc": {"activo": False}}, sb=None), {"activo": False})


if __name__ == "__main__":
    unittest.main()
