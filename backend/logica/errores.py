"""
Capa 2 - Lógica de negocio
Errores de negocio. Cada uno lleva el código HTTP que la API devolverá
y un mensaje legible que el frontend muestra tal cual al usuario.
"""


class ErrorNegocio(Exception):
    codigo_http = 400

    def __init__(self, mensaje):
        super().__init__(mensaje)
        self.mensaje = mensaje


class ErrorValidacion(ErrorNegocio):
    """Datos incompletos o con formato inválido."""
    codigo_http = 400


class ErrorAutenticacion(ErrorNegocio):
    """Credenciales inválidas o sesión expirada / cerrada."""
    codigo_http = 401


class ErrorPermiso(ErrorNegocio):
    """El usuario no tiene permitido realizar la acción (rol o estado)."""
    codigo_http = 403


class ErrorNoEncontrado(ErrorNegocio):
    codigo_http = 404


class ErrorConflicto(ErrorNegocio):
    """La acción choca con el estado actual (duplicados, pedido ya resuelto...)."""
    codigo_http = 409
