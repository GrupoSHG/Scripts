"""Fichas de postulación, sin red: PDF de bases de ejemplo, respuestas de Claude simuladas y Supabase falso."""
import copy
import json
import os
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
from zoneinfo import ZoneInfo

from licitaciones import ficha_esquema as fe
from licitaciones import fichas
from licitaciones.errores import ErrorAPI

ZONA = ZoneInfo("America/Santiago")
AHORA = datetime(2026, 10, 27, 10, 0, tzinfo=ZONA)   # martes
CODIGO = "1234-56-LP26"

BASES = [
    "BASES ADMINISTRATIVAS\nLicitación Pública Conservación Escuela Básica Los Aromos\n"
    "El presupuesto oficial disponible es de $250.000.000 impuestos incluidos.\n"
    "Las consultas se recibirán a través del portal hasta el 30 de octubre de 2026.",
    "4. GARANTÍAS\nGarantía de seriedad de la oferta por un monto equivalente al 2% del presupuesto oficial,\n"
    "con vigencia mínima de 90 días corridos desde la apertura de las ofertas.\n"
    "Se aceptará boleta de garantía bancaria, vale vista o póliza de seguro.\n"
    "Garantía de fiel cumplimiento del contrato del 5% del valor del contrato.",
    "5. REQUISITOS\nEl oferente deberá estar inscrito en el Registro de Proveedores del Estado.\n"
    "Se exige inscripción en el Registro de Contratistas del MINVU categoría 2da.\n"
    "Experiencia mínima de 3 obras similares en los últimos 5 años.\n"
    "Anexo N°1 Declaración jurada simple de habilidad.\nAnexo N°2 Oferta económica.",
    "6. EVALUACIÓN Y CONTRATO\nPrecio 60%. Experiencia 30%. Plazo 10%.\n"
    "Plazo de ejecución de 120 días corridos desde el acta de entrega de terreno.\n"
    "Multa de 1 por mil del monto del contrato por cada día de atraso.\n"
    "Se retendrá el 5% de cada estado de pago.\nNo habrá reajuste del precio del contrato.",
]


def pdf_de(paginas):
    """PDF mínimo con texto real (Helvetica, WinAnsi) en cada página; página vacía = como escaneada."""
    def esc(s):
        return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    n = len(paginas)
    objetos = [b"<< /Type /Catalog /Pages 2 0 R >>",
               ("<< /Type /Pages /Kids [%s] /Count %d >>" % (" ".join(f"{4 + 2 * i} 0 R" for i in range(n)), n)).encode(),
               b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"]
    for i, texto in enumerate(paginas):
        lineas = "".join(f"({esc(l)}) Tj T* " for l in texto.split("\n")) if texto else ""
        flujo = f"BT /F1 9 Tf 12 TL 30 800 Td {lineas}ET".encode("cp1252")
        objetos.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 3 0 R >> >> "
                       f"/Contents {5 + 2 * i} 0 R >>".encode())
        objetos.append(b"<< /Length %d >>\nstream\n" % len(flujo) + flujo + b"\nendstream")
    salida, offsets = bytearray(b"%PDF-1.4\n"), []
    for k, o in enumerate(objetos, 1):
        offsets.append(len(salida))
        salida += b"%d 0 obj\n" % k + o + b"\nendobj\n"
    xref = len(salida)
    salida += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objetos) + 1)
    salida += b"".join(b"%010d 00000 n \n" % x for x in offsets)
    salida += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objetos) + 1, xref)
    return bytes(salida)


def dato(texto, pagina, cita, documento=1):
    return {"texto": texto, "documento": documento, "pagina": pagina, "cita": cita}


def extraccion_ok():
    return {
        "tipo_de_obra": dato("conservación de escuela", 1, "Conservación Escuela Básica Los Aromos"),
        "presupuesto_oficial": dato("$250.000.000 impuestos incluidos", 1, "El presupuesto oficial disponible es de $250.000.000"),
        "fechas": {"consultas": dato("hasta el 30 de octubre de 2026", 1, "Las consultas se recibirán a través del portal"),
                   "visita_terreno": None, "cierre": None, "adjudicacion": None},
        "admisibilidad": {
            "documentos_obligatorios": [dato("Anexo N°1 Declaración jurada", 3, "Anexo N°1 Declaración jurada simple de habilidad"),
                                        dato("Anexo N°2 Oferta económica", 3, "Anexo N°2 Oferta económica")],
            "registro_proveedores": dato("inscrito en el Registro de Proveedores", 3,
                                         "deberá estar inscrito en el Registro de Proveedores del Estado"),
            "otros_registros": [dato("Registro de Contratistas MINVU 2da categoría", 3,
                                     "Registro de Contratistas del MINVU categoría 2da")],
            "experiencia_minima": dato("3 obras similares en 5 años", 3, "Experiencia mínima de 3 obras similares"),
            "capacidad_economica": None,
            "visita_terreno_obligatoria": None,
        },
        "garantias": {
            "seriedad_oferta": {"monto_o_porcentaje": dato("2% del presupuesto oficial", 2, "un monto equivalente al 2% del presupuesto oficial"),
                                "vigencia": dato("90 días corridos desde la apertura", 2, "vigencia mínima de 90 días corridos"),
                                "formatos": dato("boleta, vale vista o póliza", 2, "boleta de garantía bancaria, vale vista o póliza de seguro")},
            "fiel_cumplimiento": {"monto_o_porcentaje": dato("5% del valor del contrato", 2, "fiel cumplimiento del contrato del 5%"),
                                  "vigencia": None, "formatos": None},
        },
        "criterios_evaluacion": [
            {"criterio": "Precio", "ponderacion": "60%", "documento": 1, "pagina": 4, "cita": "Precio 60%"},
            {"criterio": "Experiencia", "ponderacion": "30%", "documento": 1, "pagina": 4, "cita": "Experiencia 30%"},
            {"criterio": "Plazo", "ponderacion": "10%", "documento": 1, "pagina": 4, "cita": "Plazo 10%"}],
        "contrato": {
            "plazo_ejecucion": dato("120 días corridos", 4, "Plazo de ejecución de 120 días corridos"),
            "multas": dato("1 por mil por día de atraso", 4, "Multa de 1 por mil del monto del contrato"),
            "retenciones": dato("5% de cada estado de pago", 4, "Se retendrá el 5% de cada estado de pago"),
            "forma_pago": None,
            "reajustes": dato("sin reajuste", 4, "No habrá reajuste del precio del contrato"),
        },
        "riesgos": [dato("sin reajuste del precio", 4, "No habrá reajuste del precio del contrato")],
    }


RECOMENDACION = {"decision": "postular", "razones": ["Calza con el perfil", "Monto adecuado", "Requisitos alcanzables"]}

PRECIOS = {"claude-haiku-5-5": {"entrada": 0.10, "salida": 0.50}, "claude-sonnet-5-5": {"entrada": 2.0, "salida": 10.0}}
AJUSTES = {
    "horario": {"zona": "America/Santiago"},
    "evaluacion": {"modelo": "claude-haiku-5-5", "tope_gasto_diario_usd": 3.0, "precios_usd_por_mtok": PRECIOS},
    "fichas": {"activo": True, "puntaje_minimo": 4, "modelo": "claude-haiku-5-5", "modelo_grande": "claude-sonnet-5-5",
               "monto_modelo_grande_clp": 1e9, "esfuerzo": "low", "max_tokens": 16000, "max_mb": 25,
               "max_caracteres_por_parte": 280000, "min_caracteres_por_pagina": 40, "max_por_corrida": 5,
               "max_pendientes_por_corrida": 20, "tope_por_corrida_usd": 1.5, "pausa_descargas_s": 0,
               "dias_habiles_alerta": 5, "feriados": ["2026-10-31", "2026-11-01", "2026-12-08"]},
}
PERFIL = {"empresa": "M5 Industrial", "regiones": ["RM"]}


def a_api(extraccion):
    """Extracción en la forma que responde la API: lista plana {campo, texto, detalle, documento, pagina, cita}."""
    datos = []
    for campo in fe.CAMPOS:
        valor = extraccion
        for p in campo.split("."):
            valor = valor[p]
        for v in (valor if campo in fe.LISTAS else [valor]):
            if v is None:
                continue
            if campo == "criterios_evaluacion":
                datos.append({"campo": campo, "texto": v["criterio"], "detalle": v["ponderacion"] or "",
                              **{k: v[k] for k in ("documento", "pagina", "cita")}})
            else:
                datos.append({"campo": campo, "detalle": "", **v})
    return {"datos": datos}


class ClienteFalso:
    """Responde en orden: las respuestas de extracción y las de recomendación van en colas separadas.
    Las extracciones dadas como dict se envían en la forma de la API (a_api)."""
    def __init__(self, extracciones=(), recomendaciones=(RECOMENDACION,), tokens=20_000):
        self.colas = {"ext": list(extracciones), "rec": list(recomendaciones)}
        self.tokens, self.pedidos = tokens, []
        self.messages = self

    def count_tokens(self, **kw):
        return SimpleNamespace(input_tokens=self.tokens)

    def create(self, **kw):
        tipo = "ext" if kw["output_config"]["format"]["schema"] is fe.ESQUEMA_EXTRACCION else "rec"
        self.pedidos.append((tipo, kw))
        r = self.colas[tipo].pop(0)
        if tipo == "ext" and isinstance(r, dict):
            r = a_api(r)
        texto = r if isinstance(r, str) else json.dumps(r, ensure_ascii=False)
        return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=texto)],
                               usage=SimpleNamespace(input_tokens=self.tokens, output_tokens=1500))


class MPFalso:
    def __init__(self, cierre="2026-11-02T15:00:00", falla=None):
        self.cierre, self.falla, self.pedidos = cierre, falla, []

    def detalle(self, codigo):
        self.pedidos.append(codigo)
        if self.falla:
            raise self.falla
        return {"CodigoExterno": codigo, "Nombre": "Conservación Escuela", "NombreResponsablePago": "Persona",
                "Fechas": {"FechaPublicacion": "2026-10-20T10:00:00", "FechaFinal": "2026-10-30T15:00:00",
                           "FechaPubRespuestas": "2026-10-31T18:00:00", "FechaVisitaTerreno": None,
                           "FechaCierre": self.cierre, "FechaAdjudicacion": "2026-11-30T18:00:00"}}


class SupabaseFalso:
    def __init__(self, respuestas=None, archivos=None):
        self.respuestas, self.llamadas, self.subidas = respuestas or [], [], []
        archivos = archivos or {}
        self.sesion = SimpleNamespace(get=lambda url, timeout: SimpleNamespace(
            status_code=200, content=archivos[url.rsplit("/", 1)[-1]]))

    def _pedir(self, metodo, **kw):
        self.llamadas.append((metodo, kw))
        return SimpleNamespace(json=lambda: self.respuestas)

    def upsert(self, filas, conflicto="codigo_externo"):
        self.subidas += filas
        return len(filas)


def licitacion(codigo=CODIGO, monto=200_000_000.0):
    return {"codigo_externo": codigo, "nombre": "Conservación Escuela", "organismo": "Municipalidad", "region": "RM",
            "fecha_cierre": "2026-11-02T15:00:00-03:00", "monto_estimado": monto, "puntaje": 5, "recomendacion": "postular",
            "url_ficha": f"https://ficha/{codigo}", "tipo_de_obra": "edificación"}


def meta(id_, ruta="bases.pdf", bytes_=1000):
    return {"id": id_, "codigo_externo": CODIGO, "ruta": ruta, "nombre_archivo": ruta, "bytes": bytes_}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        for p in (mock.patch.dict(os.environ, {"SUPABASE_URL": "https://x.supabase.co"}),
                  mock.patch("licitaciones.evaluacion.ESTADO", Path(self.tmp.name)),
                  mock.patch("licitaciones.evaluacion.Presupuesto.__init__.__defaults__", (Path(self.tmp.name),)),
                  mock.patch.object(fichas, "CARPETA", Path(self.tmp.name) / "fichas")):
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(self.tmp.cleanup)
        self.pdf = pdf_de(BASES)

    def generar(self, cliente, metas=None, archivos=None, mp=None, lic=None):
        sb_bases = SupabaseFalso(archivos={"bases.pdf": self.pdf, **(archivos or {})})
        gastos, corrida = {}, {"usd": 0.0}
        gasto = lambda m: gastos.setdefault(m, fichas.Gasto(AJUSTES, m, 1.5, corrida))
        return fichas.generar(lic or licitacion(), [meta(1)] if metas is None else metas, AJUSTES, PERFIL, cliente,
                              mp or MPFalso(), sb_bases, gasto, AHORA)


class TestPDF(unittest.TestCase):
    def test_lee_texto_por_pagina(self):
        paginas = fichas.leer_pdf(pdf_de(BASES))
        self.assertEqual(len(paginas), 4)
        self.assertIn("2% del presupuesto oficial", paginas[1])
        self.assertIn("GARANTÍAS", paginas[1])

    def test_rechaza_lo_que_no_es_pdf(self):
        with self.assertRaises(ValueError):
            fichas.leer_pdf(b"MZ\x90\x00 ejecutable")

    def test_escaneado(self):
        cfg = AJUSTES["fichas"]
        self.assertTrue(fichas.documento(1, "x", fichas.leer_pdf(pdf_de(["", "", ""])), cfg)["escaneado"])
        self.assertFalse(fichas.documento(1, "x", fichas.leer_pdf(pdf_de(BASES)), cfg)["escaneado"])

    def test_partes_largas_con_encabezado(self):
        docs = [{"n": 1, "nombre": "a.pdf", "escaneado": False, "error": None}]
        trozos = fichas.partes(docs, {1: BASES}, 400)
        self.assertGreater(len(trozos), 1)
        self.assertTrue(all(t.startswith("[DOCUMENTO 1: a.pdf]") for t in trozos))
        self.assertIn("[PÁGINA 4]", trozos[-1])


class TestEsquemaYCitas(unittest.TestCase):
    def test_valida_extraccion(self):
        fe.ExtraccionBases.model_validate(extraccion_ok())
        malo = extraccion_ok()
        malo["garantias"]["seriedad_oferta"]["monto_o_porcentaje"]["pagina"] = 0
        with self.assertRaises(Exception):
            fe.ExtraccionBases.model_validate(malo)

    def test_esquema_sin_uniones(self):
        # La salida estructurada rechaza (HTTP 400) esquemas con más de 16 parámetros anyOf / tipo lista;
        # visto en el dry-run real del 27/10/2026 con 22.
        texto = json.dumps([fe.ESQUEMA_EXTRACCION, fe.ESQUEMA_RECOMENDACION])
        self.assertNotIn('"anyOf"', texto)
        self.assertNotIn('"type": [', texto)

    def test_desde_api(self):
        self.assertEqual(fe.desde_api(a_api(extraccion_ok())), extraccion_ok())
        self.assertEqual(fe.desde_api({"datos": []}), fe.vacia())
        doble = a_api(extraccion_ok())
        doble["datos"].append({"campo": "contrato.multas", "texto": "otra", "detalle": "", "documento": 1, "pagina": 1,
                               "cita": "xxx"})
        self.assertEqual(fe.desde_api(doble)["contrato"]["multas"]["texto"], "1 por mil por día de atraso")   # la primera
        self.assertEqual(set(fe.vacia()), set(fe.ExtraccionBases.model_fields))

    def test_citas(self):
        paginas = {(1, i): t for i, t in enumerate(BASES, 1)}
        self.assertEqual(fe.verificar_citas(extraccion_ok(), paginas), [])
        e = extraccion_ok()
        e["contrato"]["multas"]["cita"] = "multa del 10% diario"                     # inventada
        e["admisibilidad"]["otros_registros"][0]["pagina"] = 1                         # página equivocada
        e["garantias"]["seriedad_oferta"]["vigencia"]["cita"] = "VIGENCIA  mínima de 90 dias corridos"  # mayúsculas, espacios, sin tilde
        self.assertEqual(sorted(fe.verificar_citas(e, paginas)), ["admisibilidad.otros_registros[0]", "contrato.multas"])

    def test_cita_que_cruza_de_pagina(self):
        paginas = {(1, 1): "texto con la garantía de", (1, 2): "seriedad de la oferta al 2%"}
        e = {"x": dato("2%", 1, "la garantía de seriedad de la oferta")}
        self.assertEqual(fe.verificar_citas(e, paginas), [])


class TestCalculos(unittest.TestCase):
    def test_parsers(self):
        self.assertEqual(fichas.porcentaje("equivalente al 2,5% del presupuesto"), 2.5)
        self.assertEqual(fichas.porcentaje("cinco por ciento"), None)
        self.assertEqual(fichas.monto_clp("$250.000.000 impuestos incluidos"), 250_000_000)
        self.assertIsNone(fichas.monto_clp("Monto $5% del valor TOTAL NETO del contrato"))   # bases reales 3836-36-LP26
        self.assertEqual(fichas.monto_clp("$ 1500000"), 1_500_000)
        self.assertEqual(fichas.monto_uf("por UF 1.250,5"), 1250.5)
        self.assertEqual(fichas.plazo("120 días corridos"), {"cantidad": 120, "unidad": "días", "tipo": "corridos"})
        self.assertEqual(fichas.plazo("6 meses")["unidad"], "meses")

    def test_dias_habiles_con_feriados(self):
        feriados = {date(2026, 10, 31), date(2026, 11, 1)}
        # mar 27 -> lun 2: mié, jue, vie, lun = 4 (sábado y domingo fuera)
        self.assertEqual(fichas.dias_habiles(date(2026, 10, 27), date(2026, 11, 2), feriados), 4)
        self.assertEqual(fichas.dias_habiles(date(2026, 12, 7), date(2026, 12, 9), {date(2026, 12, 8)}), 1)
        self.assertEqual(fichas.dias_habiles(date(2026, 12, 9), date(2026, 12, 7), set()), 0)

    def test_garantias_y_alerta(self):
        fechas = {"cierre": "2026-11-02T15:00:00-03:00", "fin_consultas": "2026-10-30T15:00:00-03:00"}
        c = fichas.calcular(extraccion_ok(), fechas, 200_000_000.0, date(2026, 10, 27), {date(2026, 10, 31)}, 5)
        s = c["garantias"]["seriedad_oferta"]
        self.assertEqual((s["porcentaje"], s["monto_referencial_clp"]), (2.0, 4_000_000))
        self.assertEqual(s["vigencia"]["cantidad"], 90)
        self.assertEqual(c["garantias"]["fiel_cumplimiento"]["monto_referencial_clp"], 10_000_000)
        self.assertEqual((c["dias_habiles_cierre"], c["alerta_cierre"]), (4, True))
        self.assertEqual(c["suma_ponderaciones_pct"], 100)
        self.assertIsNone(c["aviso_ponderaciones"])
        lejos = fichas.calcular(None, {"cierre": "2026-11-20T15:00:00-03:00"}, None, date(2026, 10, 27), set(), 5)
        self.assertFalse(lejos["alerta_cierre"])
        self.assertIsNone(lejos["garantias"]["seriedad_oferta"]["monto_referencial_clp"])


class TestGenerar(Base):
    def test_ficha_completa_con_pagina_y_cita(self):
        cliente = ClienteFalso([extraccion_ok()])
        f = self.generar(cliente)
        self.assertEqual(f["estado"], "lista", f["errores"])
        self.assertEqual(f["recomendacion"]["decision"], "postular")
        self.assertTrue(f["calculos"]["alerta_cierre"])
        self.assertNotIn("NombreResponsablePago", json.dumps(f))           # lista blanca del detalle
        # Checklist: fechas de la API y fuente (documento, página y cita) de cada ítem de las bases.
        tareas = {t["tarea"]: t for t in f["checklist"]}
        self.assertEqual(tareas["Enviar consultas por el foro de Mercado Público"]["fecha_limite"][:10], "2026-10-30")
        garantia = tareas["Garantía de seriedad de la oferta"]
        self.assertEqual((garantia["fuente"]["pagina"], garantia["fecha_limite"][:10]), (2, "2026-11-02"))
        self.assertTrue(all(t["fuente"] == "API Mercado Público" or t["fuente"]["cita"] for t in f["checklist"]))
        self.assertIn("Documento: Anexo N°2 Oferta económica", tareas)
        md = fichas.markdown(f)
        self.assertIn(fichas.AVISO, md)
        self.assertIn("CIERRA EN 4 DÍAS HÁBILES", md)
        self.assertIn("≈ $4.000.000", md)
        self.assertIn("pág. 2", md)
        self.assertIn("**No aparece en las bases.**", md)                 # capacidad económica: null, no se inventa
        self.assertEqual([t for t, _ in cliente.pedidos], ["ext", "rec"])
        self.assertIn("[PÁGINA 2]", cliente.pedidos[0][1]["messages"][0]["content"])

    def test_cita_inventada_se_reintenta_y_se_descarta(self):
        mala = extraccion_ok()
        mala["contrato"]["multas"] = dato("multa 10% diario", 4, "multa del 10% diario")
        cliente = ClienteFalso([mala, copy.deepcopy(mala)])
        f = self.generar(cliente)
        self.assertEqual([t for t, _ in cliente.pedidos], ["ext", "ext", "rec"])
        self.assertIn("contrato.multas", cliente.pedidos[1][1]["messages"][0]["content"])   # el reintento dice cuál
        self.assertEqual(f["estado"], "revision_manual")
        self.assertIsNone(f["extraccion"]["contrato"]["multas"])
        self.assertEqual(f["datos_descartados_por_cita"][0]["campo"], "contrato.multas")
        self.assertIn("Revisar a mano", fichas.markdown(f))

    def test_cita_corregida_en_el_reintento(self):
        mala = extraccion_ok()
        mala["admisibilidad"]["documentos_obligatorios"].append(dato("Anexo 9", 3, "Anexo N°9 inventado"))
        f = self.generar(ClienteFalso([mala, extraccion_ok()]))
        self.assertEqual(f["estado"], "lista")
        self.assertEqual(len(f["extraccion"]["admisibilidad"]["documentos_obligatorios"]), 2)

    def test_esquema_invalido_dos_veces(self):
        cliente = ClienteFalso(["no es json", json.dumps({"tipo_de_obra": None})])
        f = self.generar(cliente)
        self.assertEqual(f["estado"], "revision_manual")
        self.assertIsNone(f["extraccion"])
        self.assertIsNone(f["recomendacion"])
        self.assertEqual([t for t, _ in cliente.pedidos], ["ext", "ext"])

    def test_sin_pdf_adjuntos_pendientes(self):
        cliente = ClienteFalso()
        f = self.generar(cliente, metas=[])
        self.assertEqual(f["estado"], "adjuntos_pendientes")
        self.assertEqual(cliente.pedidos, [])
        md = fichas.markdown(f)
        self.assertIn("ADJUNTOS PENDIENTES", md)
        self.assertIn("https://ficha/", md)
        self.assertIn("Ingresar la oferta en Mercado Público", md)

    def test_plazo_vencido_en_checklist(self):
        f = self.generar(ClienteFalso(), metas=[], mp=MPFalso())
        consultas = next(t for t in f["checklist"] if t["tarea"].startswith("Enviar consultas"))
        self.assertFalse(consultas["vencida"])
        with mock.patch.object(MPFalso, "detalle", lambda s, c: {"Fechas": {"FechaFinal": "2026-10-21T23:29:00",
                                                                            "FechaCierre": "2026-11-05T11:00:00"}}):
            f = self.generar(ClienteFalso(), metas=[])
        consultas = next(t for t in f["checklist"] if t["tarea"].startswith("Enviar consultas"))
        self.assertEqual((consultas["vencida"], consultas["nota"]), (True, "PLAZO VENCIDO"))

    def test_pdf_escaneado_no_va_a_claude(self):
        cliente = ClienteFalso()
        f = self.generar(cliente, metas=[meta(2, "scan.pdf")], archivos={"scan.pdf": pdf_de(["", ""])})
        self.assertEqual(f["estado"], "escaneado")
        self.assertEqual(cliente.pedidos, [])
        self.assertIn("PDF ESCANEADO", fichas.markdown(f))

    def test_pdf_muy_pesado_no_se_descarga(self):
        f = self.generar(ClienteFalso(), metas=[meta(3, "grande.pdf", bytes_=26 * 1024 * 1024)])
        self.assertEqual(f["estado"], "error")
        self.assertIn("25 MB", f["documentos"][0]["error"])

    def test_bases_largas_en_partes_se_combinan(self):
        ajustes = copy.deepcopy(AJUSTES)
        ajustes["fichas"]["max_caracteres_por_parte"] = 700
        primera, segunda = extraccion_ok(), extraccion_ok()
        primera["contrato"]["plazo_ejecucion"] = None
        segunda["tipo_de_obra"] = None
        cliente = ClienteFalso([primera, segunda, extraccion_ok(), extraccion_ok()])
        with mock.patch.dict(AJUSTES, ajustes):
            f = self.generar(cliente)
        self.assertGreater(f["partes"], 1)
        self.assertIsNotNone(f["extraccion"]["contrato"]["plazo_ejecucion"])   # viene de la segunda parte
        self.assertIsNotNone(f["extraccion"]["tipo_de_obra"])                  # de la primera
        self.assertEqual(len(f["extraccion"]["admisibilidad"]["documentos_obligatorios"]), 2)   # sin repetir

    def test_modelo_grande_para_montos_altos(self):
        f = self.generar(ClienteFalso([extraccion_ok()]), lic=licitacion(monto=2e9))
        self.assertEqual(f["modelo"], "claude-sonnet-5-5")

    def test_api_caida_usa_datos_de_supabase(self):
        f = self.generar(ClienteFalso([extraccion_ok()]), mp=MPFalso(falla=ErrorAPI("HTTP 500", fatal=False)))
        self.assertEqual(f["datos"]["fechas"]["cierre"], "2026-11-02T15:00:00-03:00")
        self.assertTrue(any("Mercado Público" in e for e in f["errores"]))


class TestProcesar(Base):
    def correr(self, cliente, lics, bases, dry_run=False, mp=None, previas=()):
        sb_lic, sb_bases, sb_fichas = SupabaseFalso(lics), SupabaseFalso(bases, {"bases.pdf": self.pdf}), SupabaseFalso(list(previas))
        return fichas.procesar(AJUSTES, PERFIL, cliente=cliente, mp=mp or MPFalso(), sb_lic=sb_lic, sb_bases=sb_bases,
                               sb_fichas=None if dry_run else sb_fichas, dry_run=dry_run, ahora=AHORA), sb_fichas

    def test_guarda_en_supabase_y_local(self):
        (resumen, generadas), sb = self.correr(ClienteFalso([extraccion_ok()]), [licitacion(), licitacion("9-9-LE26")], [meta(1)])
        self.assertEqual((resumen["generadas"], resumen["por_estado"]), (2, {"lista": 1, "adjuntos_pendientes": 1}))
        self.assertEqual(resumen["alerta_cierre"], 2)
        self.assertEqual([f["codigo_externo"] for f in sb.subidas], [CODIGO, "9-9-LE26"])   # primero las con PDF
        self.assertEqual(sb.subidas[0]["recomendacion"], "postular")
        self.assertTrue((fichas.CARPETA / CODIGO / "ficha.md").is_file())
        costos = (fichas.CARPETA / "costos.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(costos), 2)
        self.assertGreater(json.loads(costos[0])["costo_usd"], 0)

    def test_no_repite_si_los_pdf_no_cambiaron(self):
        previas = [{"codigo_externo": CODIGO, "estado": "lista", "bases_ids": [1]}]
        (resumen, _), _ = self.correr(ClienteFalso(), [licitacion()], [meta(1)], previas=previas)
        self.assertEqual(resumen["candidatas"], 0)
        previas = [{"codigo_externo": CODIGO, "estado": "adjuntos_pendientes", "bases_ids": []}]
        (resumen, _), _ = self.correr(ClienteFalso([extraccion_ok()]), [licitacion()], [meta(1)], previas=previas)
        self.assertEqual(resumen["por_estado"], {"lista": 1})                 # llegó el PDF: se rehace

    def test_tope_de_corrida_detiene_sin_fallar(self):
        cliente = ClienteFalso([extraccion_ok()], tokens=3_000_000)          # peor caso US$ 0,31 x ... > 1,5 con sonnet
        with mock.patch.dict(AJUSTES["fichas"], {"tope_por_corrida_usd": 0.05}):
            (resumen, generadas), sb = self.correr(cliente, [licitacion()], [meta(1)])
        self.assertIn("Tope de gasto de la corrida", resumen["interrumpida"])
        self.assertEqual((resumen["generadas"], sb.subidas, cliente.pedidos), (0, [], []))

    def test_error_en_una_licitacion_no_detiene_las_demas(self):
        class MPRaro(MPFalso):
            def detalle(self, codigo):
                if codigo == CODIGO:
                    raise RuntimeError("inesperado")
                return super().detalle(codigo)
        (resumen, _), sb = self.correr(ClienteFalso(), [licitacion(), licitacion("9-9-LE26")], [], mp=MPRaro())
        self.assertEqual((resumen["errores"], resumen["generadas"]), (1, 1))
        self.assertEqual([f["codigo_externo"] for f in sb.subidas], ["9-9-LE26"])

    def test_seccion_del_reporte(self):
        from licitaciones.reporte import armar, html_reporte, texto
        (resumen, generadas), _ = self.correr(ClienteFalso([extraccion_ok()]), [licitacion()], [meta(1)])
        carpeta = Path(self.tmp.name) / "dia"
        carpeta.mkdir()
        (carpeta / "fichas_nuevas.json").write_text(
            json.dumps(fichas.para_reporte(generadas, {"url_ficha": "https://m5/licitaciones.html?ficha={}"})), encoding="utf-8")
        datos = armar({"horario": {"zona": "America/Santiago"}}, carpeta, ahora=AHORA)
        txt, html = texto(datos), html_reporte(datos)
        self.assertIn("LICITACIONES CON FICHA NUEVA (1)", txt)
        self.assertIn(f"¡CIERRA EN 4 DÍAS HÁBILES! POSTULAR · {CODIGO} · Municipalidad · cierre 02-11-2026 15:00", txt)
        self.assertIn(f"https://m5/licitaciones.html?ficha={CODIGO}", txt)
        self.assertIn("cierra en 4 días hábiles", html)
        self.assertIn("confirmar montos, plazos y garantías", html)

    def test_dry_run_no_guarda_nada(self):
        (resumen, generadas), sb = self.correr(ClienteFalso([extraccion_ok()]), [licitacion(), licitacion("9-9-LE26")],
                                               [meta(1)], dry_run=True)
        self.assertEqual(len(generadas), 1)
        self.assertEqual(sb.subidas, [])
        self.assertFalse(fichas.CARPETA.exists())
        self.assertFalse(list(Path(self.tmp.name).glob("gasto_claude_*.json")))
        self.assertIn(fichas.AVISO, generadas[0][1])


if __name__ == "__main__":
    unittest.main()
