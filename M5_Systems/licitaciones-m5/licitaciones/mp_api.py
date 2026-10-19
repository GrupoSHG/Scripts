"""Cliente de la API de Mercado Público (ChileCompra).

- Timeout en cada llamada y reintentos con espera creciente SOLO ante conexión caída, timeout,
  429, 5xx y el error 10500 (peticiones simultáneas). Número de reintentos acotado.
- 403 (típico de una IP de centro de datos bloqueada) y ticket inválido (HTTP 203) cortan de inmediato.
- Cuenta las solicitudes del día (hora de Chile) y se detiene al llegar al tope configurado.
- Nunca registra la URL ni el texto de las excepciones de requests: ambos traen el ticket.
"""
import json
import logging
import random
import time
from collections import Counter
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

from .config import ESTADO, enmascarar, secreto
from .errores import ErrorAPI, LimiteSolicitudes

log = logging.getLogger("licitaciones.api")

RECURSO_LICITACIONES = "licitaciones.json"
CODIGO_PETICIONES_SIMULTANEAS = 10500


class Contador:
    """Solicitudes del día en hora de Chile, persistidas en estado/solicitudes_AAAAMMDD.json."""

    def __init__(self, ajustes, carpeta=ESTADO):
        self.zona = ZoneInfo(ajustes["horario"]["zona"])
        lim = ajustes["limites"]
        self.limite = int(lim["solicitudes_diarias"])
        self.tope = int(self.limite * lim["tope_pct"] / 100)
        self.carpeta = carpeta

    def _archivo(self):
        return self.carpeta / f"solicitudes_{datetime.now(self.zona):%Y%m%d}.json"

    def leer(self):
        try:
            return int(json.loads(self._archivo().read_text(encoding="utf-8"))["solicitudes"])
        except (FileNotFoundError, KeyError, ValueError):
            return 0

    def sumar(self):
        n = self.leer()
        if n >= self.tope:
            raise LimiteSolicitudes(f"Se llegó al tope de {self.tope} solicitudes diarias "
                                    f"({n} de {self.limite} hechas hoy). Se detiene la descarga.")
        self.carpeta.mkdir(parents=True, exist_ok=True)
        self._archivo().write_text(json.dumps({"solicitudes": n + 1}), encoding="utf-8")
        return n + 1


class MercadoPublico:
    def __init__(self, ajustes, ticket=None, sesion=None, contador=None, dormir=time.sleep):
        api = ajustes["api"]
        self.ticket = ticket or secreto("MP_TICKET")
        self.base = api["base"]
        self.timeout = (api["timeout_conexion_s"], api["timeout_lectura_s"])
        self.reintentos = int(api["reintentos"])
        self.espera_base = float(api["espera_base_s"])
        self.espera_maxima = float(api["espera_maxima_s"])
        self.pausa = float(api["pausa_entre_llamadas_s"])
        self.contador = contador or Contador(ajustes)
        self.dormir = dormir
        self.hechas = 0                 # solicitudes de esta ejecución, incluidos los reintentos
        self.respuestas = Counter()     # código HTTP (o tipo de error de red) -> veces
        self.sesion = sesion or requests.Session()
        self.sesion.headers["User-Agent"] = "M5Industrial-Licitaciones/1.0"

    # --- Endpoints -----------------------------------------------------------

    def listado(self, fecha=None, estado=None):
        """Listado por fecha (ddmmaaaa: licitaciones con movimiento ese día) y/o estado ('activas', ...)."""
        params = {k: v for k, v in (("fecha", fecha), ("estado", estado)) if v}
        return self._get(RECURSO_LICITACIONES, params).get("Listado") or []

    def detalle(self, codigo):
        listado = self._get(RECURSO_LICITACIONES, {"codigo": codigo}).get("Listado") or []
        return listado[0] if listado else None

    # --- HTTP ----------------------------------------------------------------

    def _get(self, recurso, params):
        visibles = dict(params)  # lo que se puede mostrar en un log: nunca incluye el ticket
        params = {**params, "ticket": self.ticket}
        motivo = None
        for intento in range(self.reintentos + 1):
            self.contador.sumar()
            self.hechas += 1
            espera_api = None
            try:
                r = self.sesion.get(self.base + recurso, params=params, timeout=self.timeout)
            except (requests.ConnectionError, requests.Timeout) as e:
                motivo = type(e).__name__
                self.respuestas[motivo] += 1
            else:
                self.respuestas[r.status_code] += 1
                if r.status_code == 200:
                    datos = self._json(r, recurso, visibles)
                    codigo = datos.get("Codigo") if "Listado" not in datos else None
                    if codigo is None:
                        self.dormir(self.pausa)
                        return datos
                    if codigo != CODIGO_PETICIONES_SIMULTANEAS:
                        raise ErrorAPI(f"{recurso} {visibles}: la API respondió Codigo {codigo}: "
                                       f"{self._mensaje(datos)}", http=200, fatal=False)
                    motivo = f"Codigo {codigo} (peticiones simultáneas)"
                elif r.status_code == 403:
                    raise ErrorAPI(f"{recurso} {visibles}: HTTP 403 Prohibido. La API rechazó la solicitud; "
                                   "si corre en GitHub Actions lo más probable es un bloqueo de la IP del centro "
                                   f"de datos. Mensaje: {self._mensaje_respuesta(r)}. No se reintenta.", http=403)
                elif r.status_code in (203, 401):
                    raise ErrorAPI(f"{recurso} {visibles}: HTTP {r.status_code}, ticket rechazado: "
                                   f"{self._mensaje_respuesta(r)}. Revisar el secret MP_TICKET.", http=r.status_code)
                elif r.status_code == 429 or r.status_code >= 500:
                    motivo = f"HTTP {r.status_code}"
                    espera_api = _retry_after(r)
                else:
                    raise ErrorAPI(f"{recurso} {visibles}: HTTP {r.status_code} {self._mensaje_respuesta(r)}",
                                   http=r.status_code, fatal=False)
            if intento == self.reintentos:
                break
            espera = min(self.espera_maxima,
                         espera_api if espera_api is not None else self.espera_base * 2 ** intento + random.uniform(0, 1))
            log.warning("%s %s: %s, reintento %d de %d en %.1f s",
                        recurso, visibles, motivo, intento + 1, self.reintentos, espera)
            self.dormir(espera)
        # 429 persistente: seguir pidiendo solo empeora el bloqueo, así que corta la corrida.
        persistente_429 = motivo == "HTTP 429"
        raise ErrorAPI(f"{recurso} {visibles}: {motivo} tras {self.reintentos + 1} intentos"
                       + (" (límite de solicitudes por IP o por ticket; se detiene la corrida)" if persistente_429 else ""),
                       http=429 if persistente_429 else None, fatal=persistente_429)

    @staticmethod
    def _texto(r):
        # La API responde UTF-8; Latin-1 queda solo como respaldo.
        try:
            return r.content.decode("utf-8-sig")
        except UnicodeDecodeError:
            return r.content.decode("latin-1")

    def _json(self, r, recurso, visibles):
        try:
            datos = json.loads(self._texto(r))
        except ValueError:
            raise ErrorAPI(f"{recurso} {visibles}: HTTP 200 pero la respuesta no es JSON", http=200, fatal=False) from None
        if not isinstance(datos, dict):
            raise ErrorAPI(f"{recurso} {visibles}: respuesta JSON con forma inesperada", http=200, fatal=False)
        return datos

    def _mensaje(self, datos):
        return enmascarar(str(datos.get("Mensaje") or datos)[:200]).replace(self.ticket, "***")

    def _mensaje_respuesta(self, r):
        texto = self._texto(r)
        try:
            texto = json.loads(texto).get("Mensaje") or texto
        except (ValueError, AttributeError):
            pass
        return enmascarar(str(texto)[:200]).replace(self.ticket, "***")


def _retry_after(r):
    try:
        return float(r.headers.get("Retry-After"))
    except (TypeError, ValueError):
        return None
