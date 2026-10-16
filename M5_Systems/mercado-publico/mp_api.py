"""Cliente de la API de Mercado Público (ChileCompra) para M5 Industrial.

- El ticket se lee SIEMPRE de la variable de entorno MP_TICKET (o de un .env local,
  que no se sube a git). Nunca se escribe en logs ni en mensajes de error.
- Cada llamada tiene timeout explícito y reintentos con espera creciente ante
  errores temporales (conexión, timeout, 429, 5xx).
- Cuenta las solicitudes del día (hora de Chile) en estado/solicitudes_AAAAMMDD.json
  y se detiene al llegar al tope configurado (80 % de 10.000 por defecto).
"""
import json
import logging
import os
import random
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

CARPETA = Path(__file__).resolve().parent
log = logging.getLogger("mercado_publico")


def cargar_env():
    """Carga el primer .env que encuentre desde esta carpeta hacia arriba (sin pisar el entorno)."""
    for carpeta in [CARPETA, *CARPETA.parents][:7]:
        archivo = carpeta / ".env"
        if archivo.is_file():
            for linea in archivo.read_text(encoding="utf-8").splitlines():
                clave, _, valor = linea.strip().partition("=")
                if clave and not clave.startswith("#"):
                    os.environ.setdefault(clave.strip(), valor.strip().strip('"'))
            return


def cargar_config(ruta=None):
    with open(ruta or CARPETA / "config.json", encoding="utf-8") as f:
        return json.load(f)


class LimiteDiarioAlcanzado(Exception):
    pass


class ErrorAPI(Exception):
    pass


class Contador:
    """Solicitudes del día en hora de Chile, persistidas en un archivo JSON."""

    def __init__(self, cfg):
        self.zona = ZoneInfo(cfg["horario"]["zona"])
        lim = cfg["limites"]
        self.tope = int(lim["solicitudes_diarias"] * lim["tope_pct"] / 100)
        self.carpeta = CARPETA / "estado"
        self.carpeta.mkdir(exist_ok=True)

    def _archivo(self):
        return self.carpeta / f"solicitudes_{datetime.now(self.zona):%Y%m%d}.json"

    def leer(self):
        try:
            return json.loads(self._archivo().read_text(encoding="utf-8"))["solicitudes"]
        except (FileNotFoundError, KeyError, ValueError):
            return 0

    def sumar(self):
        n = self.leer()
        if n >= self.tope:
            raise LimiteDiarioAlcanzado(f"Se alcanzó el tope diario de {self.tope} solicitudes ({n} hechas hoy).")
        self._archivo().write_text(json.dumps({"solicitudes": n + 1}), encoding="utf-8")
        return n + 1


class MercadoPublico:
    def __init__(self, cfg=None):
        cargar_env()
        self.cfg = cfg or cargar_config()
        self.ticket = os.environ.get("MP_TICKET", "").strip()
        if not self.ticket:
            raise SystemExit("Falta la variable de entorno MP_TICKET (ver README.md).")
        api = self.cfg["api"]
        self.base = api["base"]
        self.timeout = (api["timeout_conexion_s"], api["timeout_lectura_s"])
        self.reintentos = api["reintentos"]
        self.espera_base = api["espera_base_s"]
        self.pausa = api["pausa_entre_llamadas_s"]
        self.contador = Contador(self.cfg)
        self.hechas = 0  # solicitudes de esta ejecución
        self.sesion = requests.Session()
        self.sesion.headers["User-Agent"] = "M5Industrial-Licitaciones/1.0"

    def _get(self, recurso, params):
        """GET con reintentos. No registra la URL para no exponer el ticket."""
        params = {**params, "ticket": self.ticket}
        visibles = {k: v for k, v in params.items() if k != "ticket"}
        for intento in range(self.reintentos + 1):
            self.contador.sumar()
            self.hechas += 1
            motivo = None
            try:
                r = self.sesion.get(self.base + recurso, params=params, timeout=self.timeout)
            except (requests.ConnectionError, requests.Timeout) as e:
                motivo = type(e).__name__
            else:
                if r.status_code == 200:
                    time.sleep(self.pausa)
                    try:
                        return json.loads(self._texto(r))
                    except ValueError:
                        raise ErrorAPI(f"{recurso} {visibles}: respuesta no es JSON") from None
                if r.status_code == 429 or r.status_code >= 500:
                    motivo = f"HTTP {r.status_code}"
                else:
                    # Ticket inválido llega como HTTP 203 con texto plano (ver NOTAS_API.md).
                    raise ErrorAPI(f"{recurso} {visibles}: HTTP {r.status_code} {self._mensaje(r)}")
            if intento == self.reintentos:
                raise ErrorAPI(f"{recurso} {visibles}: {motivo} tras {self.reintentos + 1} intentos")
            espera = self.espera_base * 2 ** intento + random.uniform(0, 1)
            log.warning("%s %s: %s, reintento en %.1f s", recurso, visibles, motivo, espera)
            time.sleep(espera)

    @staticmethod
    def _texto(r):
        # La API responde UTF-8; Latin-1 queda solo como respaldo si llegara otro charset.
        try:
            return r.content.decode("utf-8")
        except UnicodeDecodeError:
            return r.content.decode("latin-1")

    def _mensaje(self, r):
        texto = self._texto(r)
        try:
            texto = json.loads(texto).get("Mensaje") or texto
        except (ValueError, AttributeError):
            pass
        return texto[:200].replace(self.ticket, "***")

    # --- Endpoints -----------------------------------------------------------

    def licitaciones(self, **filtros):
        """licitaciones.json con filtros: codigo, fecha (ddmmaaaa), estado, CodigoOrganismo, CodigoProveedor."""
        return self._get("licitaciones.json", filtros)

    def ordenes_de_compra(self, **filtros):
        return self._get("ordenesdecompra.json", filtros)

    def buscar_comprador(self):
        return self._get("Empresas/BuscarComprador", {})

    def buscar_proveedor(self, rut):
        return self._get("Empresas/BuscarProveedor", {"rutempresaproveedor": rut})
