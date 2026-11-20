"""
Capa 2 - Lógica de negocio
GestorInventario

Requisitos: F-4.1 (cambio de disponibilidad), F-5.4 (editar material),
F-6.0 (almacenamiento de materiales), I-2.7, I-2.11 (catálogo con
disponibilidad), I-5.6, I-5.7 (inventario y alta de componentes).

Diseño v3.1:
  - buscarMaterial(), listarMateriales(), procesarLiberacion().
  - La reserva es síncrona dentro de la transacción de crearPedido (capa 3).
  - La liberación es asíncrona vía el Bus: reacciona a ComponenteDevuelto,
    PedidoRechazado y PedidoCancelado.
"""

import os
import sqlite3
import uuid

from werkzeug.utils import secure_filename

from datos.capa_datos_sqlite import Material

from . import adaptadores
from .errores import ErrorConflicto, ErrorNoEncontrado, ErrorValidacion

EXTENSIONES_FOTO = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
TAMANO_MAXIMO_FOTO = 5 * 1024 * 1024  # 5 MB


class GestorInventario:
    def __init__(self, repositorio, base_datos, bus_eventos, carpeta_fotos, prefijo_url_fotos):
        self.repo = repositorio
        self.base_datos = base_datos
        self.carpeta_fotos = carpeta_fotos
        self.prefijo_url_fotos = prefijo_url_fotos.strip("/")
        bus_eventos.suscribir("ComponenteDevuelto", self.alDevolverComponente)
        bus_eventos.suscribir("PedidoRechazado", self.alLiberarPedido)
        bus_eventos.suscribir("PedidoCancelado", self.alLiberarPedido)

    # ---------------------------------------------------------------
    # Consultas (catálogo del alumno e inventario del administrador)
    # ---------------------------------------------------------------
    def listarMateriales(self):
        return [adaptadores.material_a_dto(m) for m in self.repo.listarMateriales()]

    def buscarMaterial(self, termino):
        return [adaptadores.material_a_dto(m) for m in self.repo.buscarMaterial(termino or "")]

    # ---------------------------------------------------------------
    # Alta y edición (Req F-5.4, F-6.0, I-5.7)
    # ---------------------------------------------------------------
    def _validar(self, nombre, descripcion, precio):
        nombre = str(nombre or "").strip()
        descripcion = str(descripcion or "").strip()
        if not nombre:
            raise ErrorValidacion("El nombre del componente es obligatorio.")
        if not descripcion:
            raise ErrorValidacion("La descripción breve es obligatoria.")
        try:
            precio = float(precio)
        except (TypeError, ValueError):
            raise ErrorValidacion("Ingresa un precio de reposición válido.") from None
        if precio <= 0:
            raise ErrorValidacion("El precio de reposición debe ser mayor a 0.")
        return nombre, descripcion, precio

    def _guardar_foto(self, archivo):
        """Guarda la foto subida y devuelve la ruta relativa que se almacena en la BD."""
        if archivo is None or not getattr(archivo, "filename", ""):
            return None
        extension = os.path.splitext(secure_filename(archivo.filename))[1].lower()
        if extension not in EXTENSIONES_FOTO:
            raise ErrorValidacion("La fotografía debe ser una imagen JPG, PNG, GIF o WEBP.")
        contenido = archivo.read()
        if len(contenido) > TAMANO_MAXIMO_FOTO:
            raise ErrorValidacion("La fotografía no debe pesar más de 5 MB.")
        os.makedirs(self.carpeta_fotos, exist_ok=True)
        nombre_archivo = uuid.uuid4().hex + extension
        with open(os.path.join(self.carpeta_fotos, nombre_archivo), "wb") as destino:
            destino.write(contenido)
        return f"{self.prefijo_url_fotos}/{nombre_archivo}"

    def registrarMaterial(self, nombre, numero_serie, descripcion, precio, archivo_foto=None):
        nombre, descripcion, precio = self._validar(nombre, descripcion, precio)
        numero_serie = str(numero_serie or "").strip()
        if not numero_serie:
            raise ErrorValidacion("El número de serie es obligatorio.")

        ruta_foto = self._guardar_foto(archivo_foto)
        material = Material(None, nombre, descripcion, True, numero_serie, precio, ruta_foto)
        try:
            material.registrarMaterial(self.base_datos)
        except sqlite3.IntegrityError:
            raise ErrorConflicto("Ya existe un material con ese número de serie.") from None
        return adaptadores.material_a_dto(material)

    def editarMaterial(self, identificador, nombre, descripcion, precio, archivo_foto=None):
        material = self.repo.obtenerMaterialPorId(identificador)
        if material is None:
            raise ErrorNoEncontrado("Material no encontrado.")
        nombre, descripcion, precio = self._validar(nombre, descripcion, precio)
        ruta_foto = self._guardar_foto(archivo_foto) or material.fotografia_componente_fisico
        # editarMaterial() cambia nombre, descripción, precio y foto; nunca la disponibilidad.
        material.editarMaterial(self.base_datos, nombre, descripcion, precio, ruta_foto)
        return adaptadores.material_a_dto(material)

    # ---------------------------------------------------------------
    # Manejadores del Bus de Eventos (liberación de piezas)
    # ---------------------------------------------------------------
    def procesarLiberacion(self, lista_id_materiales):
        if lista_id_materiales:
            self.repo.procesarLiberacion([int(i) for i in lista_id_materiales])

    def alDevolverComponente(self, datos):  # ComponenteDevuelto -> Req F-5.2 / F-6.0
        self.procesarLiberacion([datos["identificador_material"]])

    def alLiberarPedido(self, datos):  # PedidoRechazado / PedidoCancelado -> Req F-5.1 / F-2.9 / F-4.4
        self.procesarLiberacion(datos.get("lista_id_materiales", []))
