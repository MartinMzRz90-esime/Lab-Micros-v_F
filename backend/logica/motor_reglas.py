"""
Capa 2 - Lógica de negocio
MotorReglas  (Motor de Reglas y Temporizadores)

Requisitos: F-2.10 (tiempo de préstamo: +1:30 h o +3 h), F-2.12 (suspensión
automática por retraso), F-4.4 (30 min de tolerancia para recoger),
F-4.5 (pedidos solo de 07:00 a 21:00 h), F-4.6 (después de las 20:00 h
solo la opción de 1:30 h).

Diseño v3.1:
  - validarHorarioLaboratorio(): usa exclusivamente el reloj del servidor.
  - verificarRecogida(): pedidos pendientes con más de 30 min
        -> emite ToleranciaRecogidaAgotada.
  - verificarDevolucion(): pedidos aceptados con la hora máxima vencida
        -> marca "vencido" (no se re-emite) y emite TiempoPrestamoVencido.
  - ejecutarConciliacion(): libera piezas de pedidos cerrados si algún evento falló.
  - Polling idempotente cada minuto en segundo plano.
"""

import logging
import threading
from datetime import datetime, timedelta

from .errores import ErrorValidacion

registro = logging.getLogger("lab_micros.motor")

HORA_APERTURA = 7.0
HORA_CIERRE = 21.0
HORA_LIMITE_TRES_HORAS = 20.0

OPCIONES_PRESTAMO = (
    {"id": "h1", "horas": 1.5, "nombre": "1 h 30 min"},
    {"id": "h2", "horas": 3.0, "nombre": "3 horas"},
)


class MotorReglas:
    def __init__(self, repositorio, bus_eventos, reloj=None):
        self.repo = repositorio
        self.bus = bus_eventos
        self.reloj = reloj or datetime.now
        self._detener = threading.Event()
        self._hilo = None

    def ahora(self):
        return self.reloj().replace(microsecond=0)

    # ---------------------------------------------------------------
    # Control de horarios (Req F-2.10, F-4.5, F-4.6)
    # ---------------------------------------------------------------
    @staticmethod
    def _hora_decimal(momento):
        return momento.hour + momento.minute / 60.0

    def laboratorioAbierto(self, momento=None):
        hora = self._hora_decimal(momento or self.ahora())
        return HORA_APERTURA <= hora < HORA_CIERRE

    def opcionesHorario(self, momento=None):
        """Opciones de devolución que se muestran en el carrito.
        Fuera de 07:00-21:00 no hay opciones (el botón de confirmar queda bloqueado)."""
        momento = momento or self.ahora()
        if not self.laboratorioAbierto(momento):
            return []
        opciones = []
        for opcion in OPCIONES_PRESTAMO:
            if opcion["horas"] > 1.5 and self._hora_decimal(momento) >= HORA_LIMITE_TRES_HORAS:
                continue  # Req F-4.6
            limite = momento + timedelta(hours=opcion["horas"])
            opciones.append({
                "id": opcion["id"],
                "horas": opcion["horas"],
                "etiqueta": f"{opcion['nombre']} · devolver antes de las {limite.strftime('%H:%M')} h",
                "devolverAntesDe": limite.isoformat(timespec="seconds"),
            })
        return opciones

    def duracionDeOpcion(self, id_opcion):
        for opcion in OPCIONES_PRESTAMO:
            if opcion["id"] == id_opcion:
                return opcion["horas"]
        raise ErrorValidacion("Selecciona un horario de devolución válido.")

    def validarHorarioLaboratorio(self, momento, duracion_horas):
        if not self.laboratorioAbierto(momento):
            raise ErrorValidacion("Los pedidos solo pueden realizarse de 07:00 a 21:00 h.")
        if duracion_horas > 1.5 and self._hora_decimal(momento) >= HORA_LIMITE_TRES_HORAS:
            raise ErrorValidacion("Después de las 20:00 h solo puedes elegir la opción de 1 h 30 min.")
        try:
            return self.repo.validarHorarioLaboratorio(momento, duracion_horas)
        except ValueError as error:
            raise ErrorValidacion(str(error)) from None

    # ---------------------------------------------------------------
    # Temporizadores (polling idempotente) (Req F-4.4, F-2.12)
    # ---------------------------------------------------------------
    def verificarRecogida(self, momento=None):
        eventos = self.repo.verificarRecogida(momento or self.ahora())
        for evento in eventos:
            self.bus.publicar_resultado(evento)
        return len(eventos)

    def verificarDevolucion(self, momento=None):
        # La capa 3 marca "vencido" en la misma transacción para no re-emitir.
        eventos = self.repo.verificarDevolucion(momento or self.ahora())
        for evento in eventos:
            self.bus.publicar_resultado(evento)
        return len(eventos)

    def ejecutarConciliacion(self):
        return self.repo.ejecutarConciliacion()

    def ejecutarCiclo(self):
        momento = self.ahora()
        resultado = {
            "recogidas_vencidas": self.verificarRecogida(momento),
            "prestamos_vencidos": self.verificarDevolucion(momento),
            "piezas_conciliadas": self.ejecutarConciliacion(),
        }
        if any(resultado.values()):
            registro.info("Ciclo del motor de reglas: %s", resultado)
        return resultado

    def iniciar(self, intervalo_segundos=60):
        if self._hilo and self._hilo.is_alive():
            return

        def bucle():
            while not self._detener.is_set():
                try:
                    self.ejecutarCiclo()
                except Exception:  # noqa: BLE001 - el temporizador nunca debe morir
                    registro.exception("Error en el ciclo del motor de reglas")
                self._detener.wait(intervalo_segundos)

        self._detener.clear()
        self._hilo = threading.Thread(target=bucle, name="MotorReglas", daemon=True)
        self._hilo.start()

    def detener(self):
        self._detener.set()
