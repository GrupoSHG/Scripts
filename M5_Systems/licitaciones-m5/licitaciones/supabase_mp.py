"""Etapa 4: guardar en Supabase (m5.licitaciones_mp) por la API REST, con permisos mínimos.

- SUPABASE_URL: https://<proyecto>.supabase.co (no es secreta).
- SUPABASE_KEY: JWT con "role": "licitaciones_m5" (ver supabase/licitaciones_mp_evaluacion.sql y
  generar_clave_supabase.py). Ese rol solo puede leer, insertar y actualizar esta tabla.
- `apikey` va con la clave publicable del proyecto (pública, la misma de las páginas web), porque la
  pasarela de Supabase exige una clave del proyecto además del JWT.
- Upsert por codigo_externo. Se guardan también las que Claude recomienda descartar, solo para no
  volver a pedir su detalle ni evaluarlas; la página no las muestra.
"""
import logging
import os

import requests

from .config import enmascarar, secreto
from .errores import ErrorConfig, ErrorProceso

log = logging.getLogger("licitaciones.supabase")
TABLA = "licitaciones_mp"
LOTE = 200


class ErrorSupabase(ErrorProceso):
    codigo_salida = 7


class Supabase:
    def __init__(self, ajustes, sesion=None):
        cfg = ajustes["supabase"]
        self.url = secreto("SUPABASE_URL").rstrip("/") + "/rest/v1/" + TABLA
        self.esquema = cfg["esquema"]
        self.timeout = float(cfg.get("timeout_s", 30))
        apikey = os.environ.get("SUPABASE_APIKEY", "").strip() or cfg["apikey_publica"]
        self.sesion = sesion or requests.Session()
        self.sesion.headers.update({
            "apikey": apikey,
            "Authorization": "Bearer " + secreto("SUPABASE_KEY"),
            "Accept-Profile": self.esquema,
            "Content-Profile": self.esquema,
        })

    def _pedir(self, metodo, **kwargs):
        try:
            r = self.sesion.request(metodo, self.url, timeout=self.timeout, **kwargs)
        except (requests.ConnectionError, requests.Timeout) as e:
            raise ErrorSupabase(f"Supabase {metodo}: {type(e).__name__}") from None
        if r.status_code >= 300:
            detalle = enmascarar(r.text[:300])
            pista = (" (revisar SUPABASE_KEY: debe ser el JWT del rol licitaciones_m5, y que el SQL esté aplicado)"
                     if r.status_code in (401, 403) else "")
            raise ErrorSupabase(f"Supabase {metodo} HTTP {r.status_code}: {detalle}{pista}")
        return r

    def conocidas(self):
        """codigo_externo -> {codigo_estado, evaluado_en} de todo lo ya guardado."""
        filas, desde = {}, 0
        while True:
            r = self._pedir("GET", params={"select": "codigo_externo,codigo_estado,evaluado_en",
                                           "order": "codigo_externo"},
                            headers={"Range-Unit": "items", "Range": f"{desde}-{desde + 999}"})
            datos = r.json()
            filas.update({f["codigo_externo"]: f for f in datos})
            if len(datos) < 1000:
                return filas
            desde += 1000

    def upsert(self, filas):
        for i in range(0, len(filas), LOTE):
            self._pedir("POST", params={"on_conflict": "codigo_externo"}, json=filas[i:i + LOTE],
                        headers={"Prefer": "resolution=merge-duplicates,return=minimal"})
        return len(filas)

    def actualizar_estado(self, codigo, codigo_estado, estado, fecha_cierre, ahora):
        cambios = {"codigo_estado": codigo_estado, "estado": estado, "actualizado": ahora}
        if fecha_cierre:
            cambios["fecha_cierre"] = fecha_cierre
        self._pedir("PATCH", params={"codigo_externo": f"eq.{codigo}"}, json=cambios,
                    headers={"Prefer": "return=minimal"})


def fila(resultado, registro, modelo, ahora):
    """Fila de m5.licitaciones_mp a partir de la evaluación y el registro de la etapa 1."""
    e = resultado.get("evaluacion") or {}
    det = registro.get("detalle") or {}
    return {
        "codigo_externo": registro["codigo_externo"],
        "nombre": registro.get("nombre") or "",
        "organismo": registro.get("organismo"),
        "region": registro.get("region"),
        "comuna": registro.get("comuna"),
        "codigo_estado": registro.get("codigo_estado"),
        "estado": registro.get("estado"),
        "tipo": registro.get("tipo"),
        "fecha_publicacion": registro.get("fecha_publicacion"),
        "fecha_cierre": registro.get("fecha_cierre"),
        "monto_estimado": registro.get("monto_estimado_clp"),
        "moneda": det.get("Moneda"),
        "url_ficha": registro.get("url_ficha"),
        "palabras_clave": registro.get("coincidencias") or [],
        "actualizado": ahora,
        "puntaje": e.get("puntaje"),
        "recomendacion": e.get("recomendacion"),
        "estado_evaluacion": resultado.get("estado"),
        "motivo": e.get("motivo") or resultado.get("error"),
        "tipo_de_obra": e.get("tipo_de_obra"),
        "requisitos_clave": e.get("requisitos_clave") or [],
        "riesgos": e.get("riesgos") or [],
        "modelo_evaluacion": modelo,
        "evaluado_en": ahora,
    }


def guardar(ajustes, carpeta, sb=None, zona=None):
    """Sube evaluadas.json + descartadas_claude.json del día y actualiza el estado de las ya guardadas
    que aparecen en listado.json con otro estado. Devuelve un resumen."""
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from .descarga import leer_json

    if not (carpeta / "evaluadas.json").is_file():
        raise ErrorConfig(f"No existe {carpeta.name}/evaluadas.json: correr primero `evaluar`.")
    zona = zona or ZoneInfo(ajustes["horario"]["zona"])
    ahora = datetime.now(zona).isoformat(timespec="seconds")
    sb = sb or Supabase(ajustes)
    registros = {r["codigo_externo"]: r for r in leer_json(carpeta / "filtradas.json", [])}
    resultados = leer_json(carpeta / "evaluadas.json", []) + leer_json(carpeta / "descartadas_claude.json", [])
    modelo = (leer_json(carpeta / "costo.json", {}) or {}).get("modelo") or ajustes["evaluacion"]["modelo"]
    filas = [fila(r, registros.get(r["codigo_externo"], r), modelo, ahora) for r in resultados]
    subidas = sb.upsert(filas)

    # Estado de las ya guardadas (cerrada, adjudicada, revocada...) según el listado del día.
    conocidas = sb.conocidas()
    nuevas = {f["codigo_externo"] for f in filas}
    estados = {int(k): v for k, v in (ajustes.get("estados") or {}).items()}
    cambios = 0
    for lic in leer_json(carpeta / "listado.json", []):
        cod, est = lic.get("CodigoExterno"), lic.get("CodigoEstado")
        previa = conocidas.get(cod)
        if previa and cod not in nuevas and previa.get("codigo_estado") != est:
            from .detalle import fecha_chile
            sb.actualizar_estado(cod, est, estados.get(est), fecha_chile(lic.get("FechaCierre"), zona), ahora)
            cambios += 1
    resumen = {"subidas": subidas, "estados_actualizados": cambios, "en_tabla": len(conocidas)}
    log.info("Supabase: %d filas subidas (upsert), %d estados actualizados, %d en la tabla",
             subidas, cambios, len(conocidas))
    return resumen
