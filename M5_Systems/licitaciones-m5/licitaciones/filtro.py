"""Filtro barato (sin IA) a partir de config/perfil_m5.yaml.

Dos pasadas: por NOMBRE sobre el listado (que no trae más), y fina sobre el detalle
(descripción, ítems, rubro UNSPSC, región y monto). Solo lo que pasa ambas va a la etapa 2.
"""
import re
import unicodedata

from .errores import ErrorConfig


def normalizar(texto):
    """Minúsculas, sin tildes y sin puntuación: "O´Higgins" -> "o higgins"."""
    texto = unicodedata.normalize("NFKD", str(texto or "").lower())
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9ñ]+", " ", texto)).strip()


def _patrones(lista):
    # Desde el inicio de palabra: "edificio" también encuentra "edificios".
    return [(p, re.compile(r"\b" + re.escape(normalizar(p)))) for p in lista or [] if normalizar(p)]


class Filtro:
    def __init__(self, perfil, ajustes):
        self.incluir = _patrones((perfil.get("palabras_clave_incluir") or []) +
                                 (perfil.get("tipos_de_obra_que_interesan") or []))
        self.excluir = _patrones((perfil.get("palabras_clave_excluir") or []) +
                                 (perfil.get("tipos_de_obra_que_descartan") or []))
        if not self.incluir:
            raise ErrorConfig("config/perfil_m5.yaml no tiene palabras_clave_incluir ni tipos_de_obra_que_interesan: "
                              "sin ellas el filtro no deja pasar nada. Completar el perfil.")
        self.regiones = [normalizar(r) for r in perfil.get("regiones_de_interes") or [] if normalizar(r)]
        self.monto_min = perfil.get("monto_minimo_clp")
        self.monto_max = perfil.get("monto_maximo_clp")
        self.prefijos = tuple(str(p) for p in (ajustes.get("filtro") or {}).get("prefijos_rubro_unspsc") or ())
        self.organismos = [normalizar(o) for o in perfil.get("organismos_prioritarios") or [] if normalizar(o)]

    def _excluida(self, texto_normalizado):
        return next((p for p, rx in self.excluir if rx.search(texto_normalizado)), None)

    def por_nombre(self, nombre):
        """(pasa, coincidencias o motivo de descarte) usando solo el nombre del listado."""
        t = normalizar(nombre)
        excl = self._excluida(t)
        if excl:
            return False, f"excluida por '{excl}' en el nombre"
        claves = [p for p, rx in self.incluir if rx.search(t)]
        return (True, claves) if claves else (False, "sin palabras clave en el nombre")

    def por_detalle(self, det):
        """(pasa, coincidencias o motivo de descarte) con el detalle completo de la licitación."""
        nombre = det.get("Nombre") or ""
        excl = self._excluida(normalizar(nombre))
        if excl:
            return False, f"excluida por '{excl}' en el nombre"

        items = (det.get("Items") or {}).get("Listado") or []
        texto = normalizar(" ".join([nombre, det.get("Descripcion") or ""] +
                                    [f"{i.get('NombreProducto') or ''} {i.get('Descripcion') or ''} {i.get('Categoria') or ''}"
                                     for i in items]))
        claves = [p for p, rx in self.incluir if rx.search(texto)]
        if self.prefijos and any(str(i.get("CodigoCategoria") or "").startswith(self.prefijos) for i in items):
            claves.append("rubro construcción (UNSPSC 72)")
        if not claves:
            return False, "sin palabras clave ni rubro de construcción en el detalle"

        # Región y monto descartan solo si la licitación trae el dato.
        region = normalizar((det.get("Comprador") or {}).get("RegionUnidad"))
        if self.regiones and region and not any(r in region for r in self.regiones):
            return False, f"región fuera del perfil ({(det.get('Comprador') or {}).get('RegionUnidad')})"
        monto = monto_publicado_clp(det)
        if monto is not None:
            if self.monto_min is not None and monto < self.monto_min:
                return False, f"monto {monto:,.0f} bajo el mínimo".replace(",", ".")
            if self.monto_max is not None and monto > self.monto_max:
                return False, f"monto {monto:,.0f} sobre el máximo".replace(",", ".")
        return True, claves

    def organismo_prioritario(self, det):
        nombre = normalizar((det.get("Comprador") or {}).get("NombreOrganismo"))
        return bool(nombre) and any(o in nombre for o in self.organismos)


def monto_publicado_clp(det):
    """Monto estimado solo si el organismo lo publica (VisibilidadMonto = 1) y está en pesos."""
    monto = det.get("MontoEstimado")
    if not monto or det.get("VisibilidadMonto") != 1:
        return None
    if (det.get("Moneda") or "CLP").upper() != "CLP":
        return None
    try:
        return float(monto)
    except (TypeError, ValueError):
        return None
