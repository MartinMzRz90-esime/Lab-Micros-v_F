"""
Capa 2 - Lógica de negocio
GestorPrestamos

Requisitos: F-2.5 (pedido activo), F-2.8 (8 piezas / 4 iguales), F-2.9
(cancelación por el alumno), F-3.0 (lista de pedidos), F-4.0 (realizar
pedido), F-4.2 (cierre automático), F-4.3 (campos "pendiente"), F-4.4
(cancelación por tiempo límite), F-5.1 (aceptar/rechazar), F-5.2
(devolución por componente), I-2.5, I-2.6, I-5.2, I-5.3.

Diseño v3.1:
  - crearPedido(): revalida síncronamente el estado de la cuenta
    (GestorUsuarios), el horario (MotorReglas), el límite de piezas y que no
    exista otro pedido activo. Si una pieza no está disponible, la
    transacción completa se revierte.
  - consultarPrestamoActivo(), consultarHistorial().
  - Emite al Bus: PedidoRechazado, PedidoCancelado, ComponenteDevuelto,
    PedidoCompletado. Reacciona a ToleranciaRecogidaAgotada.
"""

from datetime import timedelta

from . import adaptadores
from .errores import ErrorConflicto, ErrorNoEncontrado, ErrorPermiso, ErrorValidacion

ESTADOS_ACTIVOS = ("pendiente", "aceptado", "vencido")
VENTANA_RECIENTES = timedelta(hours=24)  # solicitudes/devoluciones resueltas que se siguen mostrando
TEXTO_PENDIENTE = "pendiente"            # Req F-4.3


class GestorPrestamos:
    def __init__(self, repositorio, base_datos, bus_eventos, gestor_usuarios, motor_reglas):
        self.repo = repositorio
        self.base_datos = base_datos
        self.bus = bus_eventos
        self.usuarios = gestor_usuarios
        self.motor = motor_reglas
        bus_eventos.suscribir("ToleranciaRecogidaAgotada", self.alAgotarseTolerancia)

    def _pedido(self, id_pedido):
        pedido = self.repo.obtenerPedido(adaptadores.id_pedido_numero(id_pedido))
        if pedido is None:
            raise ErrorNoEncontrado("Pedido no encontrado.")
        return pedido

    # ---------------------------------------------------------------
    # Portal del alumno
    # ---------------------------------------------------------------
    def crearPedido(self, boleta, materiales, id_horario):
        if not isinstance(materiales, list) or not materiales:
            raise ErrorValidacion("Agrega al menos un material a tu pedido.")
        ids = [adaptadores.entero(m, "Material") for m in materiales]
        if not id_horario:
            raise ErrorValidacion("Selecciona un horario de devolución.")

        momento = self.motor.ahora()
        self.usuarios.revalidarEstado(boleta)                                   # cuenta activa
        duracion = self.motor.duracionDeOpcion(id_horario)
        duracion = self.motor.validarHorarioLaboratorio(momento, duracion)      # Req F-4.5, F-4.6

        try:
            pedido = self.repo.crearPedido(
                boleta_alumno=boleta,
                lista_id_materiales=ids,
                duracion_horas=duracion,
                ahora=momento,
                validar_horario=False,  # ya validado arriba por el MotorReglas
            )
        except PermissionError:
            self.usuarios.revalidarEstado(boleta)
            raise ErrorPermiso("Tu cuenta no está activa. No puedes solicitar materiales.") from None
        except RuntimeError as error:
            if "pedido activo" in str(error):
                raise ErrorConflicto("Ya tienes un pedido activo. Debes cancelarlo o devolverlo "
                                     "antes de hacer otro.") from None
            raise ErrorConflicto("Alguna pieza ya no está disponible. Actualiza el catálogo e "
                                 "inténtalo de nuevo.") from None
        except ValueError as error:
            mensaje = str(error)
            if "8 piezas" in mensaje:
                mensaje = "Solo puedes solicitar un máximo de 8 piezas por pedido."
            elif "4 piezas iguales" in mensaje:
                mensaje = "Solo puedes solicitar un máximo de 4 piezas iguales por pedido."
            elif "no existe" in mensaje:
                mensaje = "Alguno de los materiales seleccionados no existe."
            raise ErrorValidacion(mensaje) from None

        return {
            "idPedido": adaptadores.id_pedido_texto(pedido.numero_pedido),
            "estado": "Pendiente de recoger",
            "fechaPedido": pedido.fecha_hora_solicitud,
            "devolucionPrevista": pedido.fecha_hora_max_entrega,
            "toleranciaRecogida": (self.motor.ahora() + timedelta(minutes=30)).isoformat(timespec="seconds"),
        }

    def cancelarPedido(self, boleta, id_pedido):  # Req F-2.9
        pedido = self._pedido(id_pedido)
        try:
            resultado = pedido.cancelarPedido(self.base_datos, boleta)
        except PermissionError:
            raise ErrorPermiso("Solo el alumno dueño del pedido puede cancelarlo.") from None
        except RuntimeError:
            raise ErrorConflicto("El administrador ya confirmó este pedido; ya no se puede cancelar.") from None
        self.bus.publicar_resultado(resultado)  # PedidoCancelado -> Inventario libera
        return {"idPedido": adaptadores.id_pedido_texto(pedido.numero_pedido), "estado": "Cancelado"}

    def consultarPrestamoActivo(self, boleta):  # Req I-2.5
        datos = self.repo.consultarPrestamoActivo(boleta)
        if not datos:
            return None
        estado = datos["estado_pedido"]
        return {
            "idPedido": adaptadores.id_pedido_texto(datos["numero_pedido"]),
            "estado": adaptadores.ESTADO_PRESTAMO_ALUMNO.get(estado, estado),
            "estadoClave": estado,
            "puedeCancelar": estado == "pendiente",
            "fechaPedido": datos["fecha_hora_solicitud"],
            "fechaEntrega": datos["fecha_hora_aceptacion"],  # null mientras siga pendiente
            "devolucionPrevista": datos["fecha_hora_max_entrega"],
            "limiteRecogida": (adaptadores.fecha(datos["fecha_hora_solicitud"]) + timedelta(minutes=30))
            .isoformat(timespec="seconds") if estado == "pendiente" else None,
            "materiales": [
                {
                    "nombre": d["nombre_componente"],
                    "modelo": self._modelo(d["identificador_material"]),
                    "numeroSerie": d["numero_serie"],
                    "imagen": adaptadores.url_imagen(d["fotografia_componente_fisico"]),
                    "devuelto": d["estado_devolucion"] == "devuelto",
                }
                for d in datos["detalles"]
            ],
        }

    def _modelo(self, identificador_material):
        material = self.repo.obtenerMaterialPorId(identificador_material)
        return (material.descripcion_breve or "") if material else ""

    def consultarHistorial(self, boleta):  # Req I-2.6: materiales que se le han prestado
        filas = self.repo.consultarHistorial(boleta)
        historial = []
        for f in filas:
            if f["fecha_hora_aceptacion"] is None:
                continue  # pedidos cancelados/rechazados/pendientes: el material nunca se prestó
            historial.append({
                "idPedido": adaptadores.id_pedido_texto(f["numero_pedido"]),
                "nombre": f["nombre_componente"],
                "modelo": self._modelo(f["identificador_material"]),
                "numeroSerie": f["numero_serie"],
                "fechaPedido": f["fecha_hora_solicitud"],
                "fechaDevolucion": f["fecha_hora_devolucion"],
            })
        return historial

    # ---------------------------------------------------------------
    # Portal del administrador: solicitudes (Req F-5.1, I-5.2)
    # ---------------------------------------------------------------
    def listarSolicitudes(self):
        desde = (self.motor.ahora() - VENTANA_RECIENTES).isoformat(timespec="seconds")
        solicitudes = []
        for p in self.repo.listarSolicitudesAdmin(desde):
            aceptado = p["folio_admin_acepta"] is not None
            solicitudes.append({
                "idPedido": adaptadores.id_pedido_texto(p["numero_pedido"]),
                "alumno": p["nombre_alumno"],
                "boleta": p["boleta_alumno"],
                "materiales": [
                    {"id": m["identificador_material"], "nombre": m["nombre_componente"],
                     "numeroSerie": m["numero_serie"]}
                    for m in p["materiales"]
                ],
                "numeroTotalMateriales": p["numero_total_materiales"],
                "fechaSolicitud": p["fecha_hora_solicitud"],
                "horarioEntrega": "devolver antes de las " + adaptadores.hora_corta(p["fecha_hora_max_entrega"]) + " h",
                "fechaMaxEntrega": p["fecha_hora_max_entrega"],
                "estado": adaptadores.ESTADO_SOLICITUD.get(p["estado_pedido"], p["estado_pedido"]),
                "estadoClave": p["estado_pedido"],
                # Req F-4.3: mientras nadie acepte, estos campos se muestran como "pendiente"
                "folioAdminAcepta": p["folio_admin_acepta"] if aceptado else TEXTO_PENDIENTE,
                "nombreAdminAcepta": p["nombre_admin_acepta"] if aceptado else TEXTO_PENDIENTE,
                "fechaAceptacion": p["fecha_hora_aceptacion"] if aceptado else None,
            })
        return solicitudes

    def aceptarPedido(self, administrador, id_pedido):
        pedido = self._pedido(id_pedido)
        try:
            administrador.aceptarPedido(self.base_datos, pedido.numero_pedido,
                                        fecha_hora_aceptacion=self.motor.ahora().isoformat(timespec="seconds"))
        except RuntimeError:
            raise ErrorConflicto("El pedido ya fue resuelto o cancelado.") from None
        return {"idPedido": adaptadores.id_pedido_texto(pedido.numero_pedido), "estado": "Aceptado"}

    def rechazarPedido(self, administrador, id_pedido):
        pedido = self._pedido(id_pedido)
        try:
            # La confirmación visual obligatoria (Req I-5.8) la muestra la capa 1 antes de llamar.
            resultado = administrador.rechazarPedido(self.base_datos, pedido.numero_pedido, confirmacion_visual=True)
        except RuntimeError:
            raise ErrorConflicto("El pedido ya fue resuelto o cancelado.") from None
        self.bus.publicar_resultado(resultado)  # PedidoRechazado -> Inventario libera
        return {"idPedido": adaptadores.id_pedido_texto(pedido.numero_pedido), "estado": "Rechazado"}

    # ---------------------------------------------------------------
    # Portal del administrador: devoluciones (Req F-5.2, F-4.2, I-5.3)
    # ---------------------------------------------------------------
    def listarDevoluciones(self):
        desde = (self.motor.ahora() - VENTANA_RECIENTES).isoformat(timespec="seconds")
        piezas = []
        for d in self.repo.listarPiezasPrestadas(desde):
            if d["estado_devolucion"] == "devuelto":
                estado = "Devuelto"
            elif d["estado_pedido"] == "vencido":
                estado = "Vencido"
            else:
                estado = "En préstamo"
            piezas.append({
                "idDetalle": d["id_detalle"],
                "idPedido": adaptadores.id_pedido_texto(d["numero_pedido"]),
                "idMaterial": d["identificador_material"],
                "material": d["nombre_componente"],
                "numeroSerie": d["numero_serie"],
                "alumno": d["nombre_alumno"],
                "boleta": d["boleta_alumno"],
                "fechaPedido": d["fecha_hora_solicitud"],
                "fechaEntrega": d["fecha_hora_aceptacion"],
                "devolucionPrevista": d["fecha_hora_max_entrega"],
                "estado": estado,
                "fechaDevolucion": d["fecha_hora_devolucion"],
                "folioAdminRecibe": d["folio_admin_recibe"],
            })
        return piezas

    def marcarDevolucion(self, administrador, id_detalle):
        detalle = self.repo.obtenerDetallePedido(adaptadores.entero(id_detalle, "Pieza"))
        if detalle is None:
            raise ErrorNoEncontrado("Pieza no encontrada.")
        if detalle.estado_devolucion == "devuelto":
            raise ErrorConflicto("Esa pieza ya fue marcada como devuelta.")
        pedido = self.repo.obtenerPedido(detalle.numero_pedido)
        if pedido.estado_pedido not in ("aceptado", "vencido"):
            raise ErrorConflicto("Solo se pueden devolver piezas de pedidos entregados al alumno.")

        evento_pieza = detalle.marcarComponenteDevuelto(
            self.base_datos, folio_admin_recibe=administrador.folio,
            fecha_hora_devolucion=self.motor.ahora().isoformat(timespec="seconds"))
        self.bus.publicar_resultado(evento_pieza)          # ComponenteDevuelto -> Inventario libera

        evento_cierre = pedido.verificarCierreAutomatico(self.base_datos)  # Req F-4.2
        self.bus.publicar_resultado(evento_cierre)         # PedidoCompletado -> Usuarios reactiva
        return {
            "idPedido": adaptadores.id_pedido_texto(pedido.numero_pedido),
            "pedidoCompletado": evento_cierre is not None,
        }

    # ---------------------------------------------------------------
    # Manejador del Bus: ToleranciaRecogidaAgotada (Req F-4.4)
    # ---------------------------------------------------------------
    def alAgotarseTolerancia(self, datos):
        pedido = self.repo.obtenerPedido(datos["id_pedido"])
        if pedido is None or pedido.estado_pedido != "pendiente":
            return  # el administrador lo aceptó/rechazó antes; no se libera nada
        resultado = pedido.cancelarPorTiempoLimite(self.base_datos)
        self.bus.publicar_resultado(resultado)  # PedidoCancelado -> Inventario libera

