"""Errores del proceso. Cada uno define el código de salida, para que GitHub Actions falle de forma visible."""


class ErrorProceso(Exception):
    codigo_salida = 1


class ErrorConfig(ErrorProceso):
    """Falta una variable de entorno, un archivo de configuración es inválido o la ejecución no corresponde."""
    codigo_salida = 1


class ErrorAPI(ErrorProceso):
    """Error de la API de Mercado Público. `fatal` = no tiene sentido seguir pidiendo (403, ticket, 429)."""
    codigo_salida = 2

    def __init__(self, mensaje, http=None, fatal=True):
        super().__init__(mensaje)
        self.http = http
        self.fatal = fatal


class LimiteSolicitudes(ErrorProceso):
    """Se llegó al tope de solicitudes diarias del ticket (80 % por defecto)."""
    codigo_salida = 3
