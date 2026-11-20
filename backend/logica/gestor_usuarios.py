"""
Capa 2 - Lógica de negocio
GestorUsuarios  (Gestor de Usuarios y Sanciones)

Requisitos: F-2.1, F-2.4 (edición de perfil), F-2.12 (suspensión automática),
F-2.13 (anulación de la suspensión por entrega), F-5.5 (bloqueos),
I-2.3, I-2.4, I-2.8, I-2.10 (estado y motivo), I-5.4, I-5.5 (control de alumnos).

Diseño v3.1:
  - revalidarEstado(), quitarSanciones(), aplicarSuspension().
  - Reacciona a TiempoPrestamoVencido (suspende) y PedidoCompletado (reactiva).
  - La suspensión solo se aplica si el estado actual es "activo"
    (jerarquía Bloqueado > Suspendido).
"""

import sqlite3

from . import adaptadores
from .errores import ErrorConflicto, ErrorNoEncontrado, ErrorPermiso, ErrorValidacion

DOMINIO_CORREO = "@alumno.ipn.mx"


class GestorUsuarios:
    def __init__(self, repositorio, base_datos, bus_eventos):
        self.repo = repositorio
        self.base_datos = base_datos
        self.bus = bus_eventos
        bus_eventos.suscribir("TiempoPrestamoVencido", self.alVencerPrestamo)
        bus_eventos.suscribir("PedidoCompletado", self.alCompletarPedido)

    # ---------------------------------------------------------------
    # Perfil del alumno (Req F-2.4, I-2.3)
    # ---------------------------------------------------------------
    def _alumno(self, boleta):
        alumno = self.repo.obtenerAlumnoPorBoleta(boleta)
        if alumno is None:
            raise ErrorNoEncontrado("Alumno no encontrado.")
        return alumno

    def consultarPerfil(self, boleta):
        alumno = self._alumno(boleta)
        alumno.consultarPerfil(self.base_datos)
        tiene_activo = self.repo.consultarPrestamoActivo(boleta) is not None
        return adaptadores.alumno_a_dto(alumno, tiene_activo)

    def editarPerfil(self, boleta, nombre_completo, correo):
        nombre_completo = str(nombre_completo or "").strip()
        correo = str(correo or "").strip()
        if not nombre_completo or not correo:
            raise ErrorValidacion("El nombre y el correo son obligatorios.")
        if not correo.lower().endswith(DOMINIO_CORREO):
            raise ErrorValidacion("El correo debe pertenecer al dominio @alumno.ipn.mx.")

        alumno = self._alumno(boleta)
        try:
            alumno.editarPerfil(self.base_datos, nombre_completo, correo)
        except sqlite3.IntegrityError:
            raise ErrorConflicto("Ese correo electrónico ya está registrado en otra cuenta.") from None
        except ValueError as error:
            raise ErrorValidacion(str(error)) from None
        return self.consultarPerfil(boleta)

    def consultarMotivoSuspension(self, boleta):
        datos = self._alumno(boleta).consultarMotivoSuspension(self.base_datos)
        datos["estado"] = adaptadores.ESTADO_ALUMNO.get(datos["estado"], datos["estado"])
        return datos

    # ---------------------------------------------------------------
    # Revalidación síncrona usada por GestorPrestamos al crear pedidos
    # ---------------------------------------------------------------
    def revalidarEstado(self, boleta):
        try:
            estado = self.repo.revalidarEstado(boleta)
        except ValueError:
            raise ErrorNoEncontrado("Alumno no encontrado.") from None
        if estado == "suspendido":
            raise ErrorPermiso("Estás suspendido. No puedes solicitar materiales mientras tu cuenta "
                               "permanezca en este estado.")
        if estado == "bloqueado":
            raise ErrorPermiso("Estás bloqueado. No puedes solicitar materiales. Consulta con el "
                               "administrador para revisar tu caso.")
        return estado

    # ---------------------------------------------------------------
    # Control de alumnos (Req F-5.5, I-5.4, I-5.5)
    # ---------------------------------------------------------------
    def listarAlumnos(self, termino=""):
        filas = self.repo.buscar_alumnos_directorio(termino or "")
        return [adaptadores.fila_directorio_a_dto(f) for f in filas]

    def bloquearAlumno(self, administrador, boleta, motivo):
        if not str(motivo or "").strip():
            raise ErrorValidacion("El motivo es obligatorio para aplicar un bloqueo.")
        try:
            administrador.bloquearAlumno(self.base_datos, boleta, str(motivo))
        except ValueError as error:
            if "No existe" in str(error):
                raise ErrorNoEncontrado("Alumno no encontrado.") from None
            raise ErrorValidacion(str(error)) from None
        return self._dto_directorio(boleta)

    def quitarSanciones(self, boleta):
        self._alumno(boleta)
        self.repo.quitarSanciones(boleta)
        return self._dto_directorio(boleta)

    def _dto_directorio(self, boleta):
        alumno = self._alumno(boleta)
        return {
            "nombre": alumno.nombre_completo,
            "boleta": alumno.boleta,
            "correo": alumno.correo_electronico,
            "estado": adaptadores.ESTADO_ALUMNO.get(alumno.estado, alumno.estado),
            "motivoSancion": alumno.motivo_sancion,
        }

    # ---------------------------------------------------------------
    # Manejadores del Bus de Eventos
    # ---------------------------------------------------------------
    def aplicarSuspension(self, boleta, motivo):
        """Suspende solo si el alumno está activo (Bloqueado > Suspendido)."""
        return self.repo.aplicarSuspension(boleta, motivo)

    def alVencerPrestamo(self, datos):  # TiempoPrestamoVencido -> Req F-2.12
        id_texto = adaptadores.id_pedido_texto(datos["id_pedido"])
        motivo = (f"Suspensión automática: el pedido {id_texto} no se devolvió antes de la "
                  f"hora máxima de entrega.")
        self.aplicarSuspension(datos["boleta_alumno"], motivo)

    def alCompletarPedido(self, datos):  # PedidoCompletado -> Req F-2.13
        # Solo cambia "suspendido" a "activo"; un alumno bloqueado sigue bloqueado.
        self.repo.reactivarPorDevolucionTotal(datos["boleta_alumno"])
