"""Rutas, configuración YAML y manejo de credenciales.

Las credenciales se leen SOLO de variables de entorno (o de un .env en la raíz del repositorio,
que no se sube a git) y nunca se escriben en logs: todo mensaje pasa por `enmascarar`.
"""
import logging
import os
import re
import sys
from pathlib import Path

import yaml

from .errores import ErrorConfig

RAIZ = Path(__file__).resolve().parent.parent
CARPETA_CONFIG = RAIZ / "config"
SALIDA = RAIZ / "salida"
ESTADO = RAIZ / "estado"

# Variables cuyo valor nunca debe aparecer en un log. SUPABASE_URL no es secreta.
SECRETOS = ("MP_TICKET", "ANTHROPIC_API_KEY", "SUPABASE_KEY")
_PARAMETRO_SECRETO = re.compile(r"(?i)\b(ticket|api[_-]?key|apikey|key|token|password|secret)=([^&\s'\"]+)")
_BEARER = re.compile(r"(?i)\b(bearer)\s+[A-Za-z0-9._\-]+")


def cargar_env():
    """Carga RAIZ/.env sin pisar variables ya definidas. No busca .env en otras carpetas."""
    archivo = RAIZ / ".env"
    if not archivo.is_file():
        return
    for linea in archivo.read_text(encoding="utf-8-sig").splitlines():
        clave, _, valor = linea.strip().partition("=")
        if clave and not clave.startswith("#") and valor.strip():
            os.environ.setdefault(clave.strip(), valor.strip().strip('"').strip("'"))


def secreto(nombre):
    valor = os.environ.get(nombre, "").strip()
    if not valor:
        raise ErrorConfig(f"Falta la variable de entorno {nombre} (ver README.md y .env.example).")
    return valor


def enmascarar(texto):
    """Quita de un texto los valores de las credenciales y cualquier parámetro ticket=/key=/token=."""
    texto = str(texto)
    for nombre in SECRETOS:
        valor = os.environ.get(nombre, "").strip()
        if len(valor) >= 4:
            texto = texto.replace(valor, "***")
    texto = _PARAMETRO_SECRETO.sub(r"\1=***", texto)
    return _BEARER.sub(r"\1 ***", texto)


class FiltroSecretos(logging.Filter):
    """Enmascara el mensaje ya formateado y el traceback de cada registro de log."""

    def filter(self, record):
        mensaje = record.getMessage()
        if record.exc_info:
            mensaje += "\n" + logging.Formatter().formatException(record.exc_info)
            record.exc_info = None
            record.exc_text = None
        record.msg = enmascarar(mensaje)
        record.args = None
        return True


def configurar_logging(nivel=logging.INFO):
    for flujo in (sys.stdout, sys.stderr):
        try:
            flujo.reconfigure(encoding="utf-8")
        except AttributeError:
            pass
    manejador = logging.StreamHandler(sys.stderr)
    manejador.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%H:%M:%S"))
    manejador.addFilter(FiltroSecretos())
    raiz = logging.getLogger()
    raiz.handlers[:] = [manejador]
    raiz.setLevel(nivel)
    # urllib3 en DEBUG escribe las URLs completas (con el ticket): nunca bajar de WARNING.
    logging.getLogger("urllib3").setLevel(logging.WARNING)


def _leer_yaml(texto, origen):
    try:
        datos = yaml.safe_load(texto)
    except yaml.YAMLError as e:
        raise ErrorConfig(f"{origen} no es YAML válido: {e}") from None
    if not isinstance(datos, dict):
        raise ErrorConfig(f"{origen} debe ser un diccionario de campos")
    return datos


def cargar_yaml(ruta):
    ruta = Path(ruta)
    try:
        texto = ruta.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        raise ErrorConfig(f"No existe {ruta}") from None
    return _leer_yaml(texto, ruta.name)


def cargar_ajustes():
    return cargar_yaml(CARPETA_CONFIG / "ajustes.yaml")


def cargar_perfil(ruta=None):
    """Perfil de M5: --perfil RUTA, o la variable PERFIL_M5_YAML (secret en Actions, porque el repo
    Scripts es público), o config/perfil_m5.yaml."""
    if ruta:
        return cargar_yaml(ruta)
    contenido = os.environ.get("PERFIL_M5_YAML", "").strip()
    if contenido:
        return _leer_yaml(contenido, "la variable PERFIL_M5_YAML")
    return cargar_yaml(CARPETA_CONFIG / "perfil_m5.yaml")
