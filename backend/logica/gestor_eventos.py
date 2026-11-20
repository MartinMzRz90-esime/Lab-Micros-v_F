"""
Capa 2 - Lógica de negocio
GestorEventos (Bus de Eventos, patrón Pub/Sub local en memoria).

Diseño v3.1 - Submódulo Bus de Eventos:
  - Recibe el payload (boleta, IDs) y ejecuta los manejadores suscritos.
  - Cada manejador corre en su propia transacción (los métodos de la capa 3
    abren y confirman su propia conexión).
  - Política de 3 reintentos y registro (log) del error si el último falla.
    Si un evento se pierde, la conciliación del MotorReglas lo corrige.

Eventos del sistema (tabla "Eventos" del diseño):
  ComponenteDevuelto, PedidoRechazado, PedidoCancelado, PedidoCompletado,
  ToleranciaRecogidaAgotada, TiempoPrestamoVencido
"""

import logging
import threading
import time

registro = logging.getLogger("lab_micros.eventos")

EVENTOS_DEL_SISTEMA = (
    "ComponenteDevuelto",
    "PedidoRechazado",
    "PedidoCancelado",
    "PedidoCompletado",
    "ToleranciaRecogidaAgotada",
    "TiempoPrestamoVencido",
)


class GestorEventos:
    REINTENTOS = 3

    def __init__(self, espera_entre_reintentos=0.2):
        self._manejadores = {nombre: [] for nombre in EVENTOS_DEL_SISTEMA}
        self._candado = threading.Lock()
        self._espera = espera_entre_reintentos
        self.historial = []  # últimos eventos publicados (útil para depurar/pruebas)

    def suscribir(self, nombre_evento, manejador):
        if nombre_evento not in self._manejadores:
            raise ValueError(f"Evento desconocido: {nombre_evento}")
        with self._candado:
            self._manejadores[nombre_evento].append(manejador)

    def publicar(self, nombre_evento, datos_evento):
        """Publica un evento. Se llama DESPUÉS de confirmar la transacción emisora."""
        self.historial.append((nombre_evento, dict(datos_evento)))
        del self.historial[:-200]
        registro.info("Evento %s %s", nombre_evento, datos_evento)
        self.orquestarManejadores(nombre_evento, datos_evento)

    def publicar_resultado(self, resultado):
        """Acepta el formato que devuelve la capa 3: {"evento": ..., "datos_evento": {...}}."""
        if resultado and resultado.get("evento"):
            self.publicar(resultado["evento"], resultado.get("datos_evento", {}))

    def orquestarManejadores(self, nombre_evento, datos_evento):
        with self._candado:
            manejadores = list(self._manejadores.get(nombre_evento, []))

        for manejador in manejadores:
            for intento in range(1, self.REINTENTOS + 1):
                try:
                    manejador(dict(datos_evento))
                    break
                except Exception:  # noqa: BLE001 - se registra y se reintenta
                    if intento == self.REINTENTOS:
                        registro.exception(
                            "Manejador %s falló %d veces para %s %s. "
                            "La conciliación del MotorReglas corregirá el estado.",
                            getattr(manejador, "__qualname__", manejador),
                            self.REINTENTOS, nombre_evento, datos_evento,
                        )
                    else:
                        time.sleep(self._espera)
