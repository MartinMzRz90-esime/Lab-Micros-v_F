"""
//SISTEMA DE GESTIÓN PARA PRÉSTAMO DE EQUIPO DE LABORATORIO DE MICROPROCESADORES
//Capa 3: Repositorio de Datos (Python ORM) + Base de Datos (SQLite)
"""

import hashlib
import os
import sqlite3
from datetime import datetime, timedelta


# TABLAS EN SQLITE (PAG 13)

ESQUEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS usuarios (
    id_usuario      INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre_completo TEXT    NOT NULL,
    contrasena      TEXT    NOT NULL,
    identificador   TEXT    NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS alumnos (
    boleta             TEXT    PRIMARY KEY,
    id_usuario         INTEGER NOT NULL UNIQUE,
    correo_electronico TEXT    NOT NULL UNIQUE,
    estado             TEXT    NOT NULL DEFAULT 'activo',
    motivo_sancion     TEXT,
    FOREIGN KEY (id_usuario) REFERENCES usuarios(id_usuario)
);

CREATE TABLE IF NOT EXISTS administradores (
    folio      INTEGER PRIMARY KEY AUTOINCREMENT,
    id_usuario INTEGER NOT NULL UNIQUE,
    FOREIGN KEY (id_usuario) REFERENCES usuarios(id_usuario)
);

CREATE TABLE IF NOT EXISTS materiales (
    identificador_material       INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre_componente            TEXT    NOT NULL,
    descripcion_breve            TEXT,
    disponible                   BOOLEAN NOT NULL DEFAULT 1,
    numero_serie                 TEXT    NOT NULL UNIQUE,
    precio_reposicion            REAL    NOT NULL DEFAULT 0.0,
    fotografia_componente_fisico TEXT,
    estado                       TEXT    NOT NULL DEFAULT 'disponible'
);

CREATE TABLE IF NOT EXISTS pedidos (
    numero_pedido           INTEGER PRIMARY KEY AUTOINCREMENT,
    boleta_alumno           TEXT    NOT NULL,
    numero_total_materiales INTEGER NOT NULL,
    fecha_hora_solicitud    TEXT    NOT NULL,
    fecha_hora_aceptacion   TEXT,
    folio_admin_acepta      INTEGER,
    estado_pedido           TEXT    NOT NULL DEFAULT 'pendiente',
    fecha_hora_max_entrega  TEXT    NOT NULL,
    FOREIGN KEY (boleta_alumno)      REFERENCES alumnos(boleta),
    FOREIGN KEY (folio_admin_acepta) REFERENCES administradores(folio)
);

CREATE TABLE IF NOT EXISTS detalle_pedido (
    id_detalle             INTEGER PRIMARY KEY AUTOINCREMENT,
    numero_pedido          INTEGER NOT NULL,
    identificador_material INTEGER NOT NULL,
    estado_devolucion      TEXT    NOT NULL DEFAULT 'pendiente',
    observaciones          TEXT,
    folio_admin_recibe     INTEGER,
    fecha_hora_devolucion  TEXT,
    FOREIGN KEY (numero_pedido)          REFERENCES pedidos(numero_pedido),
    FOREIGN KEY (identificador_material) REFERENCES materiales(identificador_material),
    FOREIGN KEY (folio_admin_recibe)     REFERENCES administradores(folio)
);
"""


# CONEXION A LA BASE DE DATOS

class BaseDatosSQLite:
    def __init__(self, ruta_bd="laboratorio_microprocesadores.db"):
        self.ruta_bd = str(ruta_bd)
        self._inicializar_esquema()

    def conectar(self):
        conexion = sqlite3.connect(self.ruta_bd, timeout=15.0)
        conexion.row_factory = sqlite3.Row
        conexion.execute("PRAGMA foreign_keys = ON;")
        return conexion

    def _inicializar_esquema(self):
        conexion = self.conectar()
        try:
            conexion.executescript(ESQUEMA_SQL)
            conexion.commit()
        finally:
            conexion.close()


def hashear_contrasena(contrasena_plana):
    return hashlib.sha256(contrasena_plana.encode("utf-8")).hexdigest()


# CLASES DEL SISTEMA

class Usuario:
    def __init__(self, id_usuario, nombre_completo, contrasena, identificador, sesion_activa=True):
        self.id_usuario = id_usuario
        self.nombre_completo = nombre_completo
        self.contrasena = contrasena
        self.identificador = identificador
        self.sesion_activa = sesion_activa

    def cerrarSesion(self):
        self.sesion_activa = False
        return {
            "id_usuario": self.id_usuario,
            "identificador": self.identificador,
            "sesion_activa": False,
            "mensaje": "Sesión cerrada correctamente"
        }


class Alumno(Usuario):
    def __init__(self, id_usuario, nombre_completo, contrasena, identificador,
                 boleta="", correo_electronico="", estado="activo", motivo_sancion=None):
        super().__init__(id_usuario, nombre_completo, contrasena, identificador)
        self.boleta = boleta
        self.correo_electronico = correo_electronico
        self.estado = estado
        self.motivo_sancion = motivo_sancion

    def consultarPerfil(self, base_datos):
        conexion = base_datos.conectar()
        try:
            fila = conexion.execute(
                """
                SELECT u.id_usuario, u.nombre_completo, u.identificador,
                       a.boleta, a.correo_electronico, a.estado, a.motivo_sancion
                FROM alumnos a
                JOIN usuarios u ON u.id_usuario = a.id_usuario
                WHERE a.boleta = ?
                """,
                (self.boleta,)
            ).fetchone()
            if not fila:
                raise ValueError(f"Alumno con boleta {self.boleta} no encontrado.")
            self.nombre_completo = fila["nombre_completo"]
            self.correo_electronico = fila["correo_electronico"]
            self.estado = fila["estado"]
            self.motivo_sancion = fila["motivo_sancion"]
            return dict(fila)
        finally:
            conexion.close()

    def editarPerfil(self, base_datos, nuevo_nombre_completo, nuevo_correo_electronico):
        if not nuevo_nombre_completo.strip():
            raise ValueError("El nombre completo es obligatorio.")
        if not nuevo_correo_electronico.strip().endswith("@alumno.ipn.mx"):
            raise ValueError("El correo debe pertenecer al dominio @alumno.ipn.mx.")

        conexion = base_datos.conectar()
        try:
            conexion.execute(
                "UPDATE usuarios SET nombre_completo = ? WHERE id_usuario = ?",
                (nuevo_nombre_completo.strip(), self.id_usuario)
            )
            conexion.execute(
                "UPDATE alumnos SET correo_electronico = ? WHERE boleta = ?",
                (nuevo_correo_electronico.strip(), self.boleta)
            )
            conexion.commit()
        except Exception:
            conexion.rollback()
            raise
        finally:
            conexion.close()

        self.nombre_completo = nuevo_nombre_completo.strip()
        self.correo_electronico = nuevo_correo_electronico.strip()
        return self.consultarPerfil(base_datos)

    def consultarMotivoSuspension(self, base_datos):
        perfil = self.consultarPerfil(base_datos)
        return {
            "boleta": perfil["boleta"],
            "estado": perfil["estado"],
            "motivo_sancion": perfil["motivo_sancion"]
        }


class Material:
    def __init__(self, identificador_material, nombre_componente, descripcion_breve,
                 disponible, numero_serie, precio_reposicion,
                 fotografia_componente_fisico=None, estado="disponible"):
        self.identificador_material = identificador_material
        self.nombre_componente = nombre_componente
        self.descripcion_breve = descripcion_breve
        self.disponible = bool(disponible)
        self.numero_serie = numero_serie
        self.precio_reposicion = float(precio_reposicion)
        self.fotografia_componente_fisico = fotografia_componente_fisico
        self.estado = estado

    def registrarMaterial(self, base_datos):
        conexion = base_datos.conectar()
        try:
            cursor_bd = conexion.execute(
                """
                INSERT INTO materiales (
                    nombre_componente,
                    descripcion_breve,
                    disponible,
                    numero_serie,
                    precio_reposicion,
                    fotografia_componente_fisico,
                    estado
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    self.nombre_componente.strip(),
                    self.descripcion_breve.strip() if self.descripcion_breve else "",
                    1 if self.disponible else 0,
                    self.numero_serie.strip(),
                    float(self.precio_reposicion),
                    self.fotografia_componente_fisico,
                    self.estado
                )
            )
            self.identificador_material = int(cursor_bd.lastrowid)
            conexion.commit()
            return self.identificador_material
        except Exception:
            conexion.rollback()
            raise
        finally:
            conexion.close()

    def editarMaterial(self, base_datos, nombre_componente, descripcion_breve,
                       precio_reposicion, fotografia_componente_fisico=None):
        if self.identificador_material is None:
            raise ValueError("El material debe estar registrado antes de editarse.")

        conexion = base_datos.conectar()
        try:
            conexion.execute(
                """
                UPDATE materiales
                SET nombre_componente = ?,
                    descripcion_breve = ?,
                    precio_reposicion = ?,
                    fotografia_componente_fisico = ?
                WHERE identificador_material = ?
                """,
                (
                    nombre_componente.strip(),
                    descripcion_breve.strip(),
                    float(precio_reposicion),
                    fotografia_componente_fisico,
                    self.identificador_material
                )
            )
            conexion.commit()
        except Exception:
            conexion.rollback()
            raise
        finally:
            conexion.close()

        self.nombre_componente = nombre_componente.strip()
        self.descripcion_breve = descripcion_breve.strip()
        self.precio_reposicion = float(precio_reposicion)
        self.fotografia_componente_fisico = fotografia_componente_fisico

    def reservar(self, base_datos, conexion_externa=None):
        if self.identificador_material is None:
            raise ValueError("El material no tiene identificador asignado.")

        cerrar_conexion = False
        if conexion_externa is None:
            conexion = base_datos.conectar()
            cerrar_conexion = True
        else:
            conexion = conexion_externa

        try:
            fila = conexion.execute(
                "SELECT disponible, estado FROM materiales WHERE identificador_material = ?",
                (self.identificador_material,)
            ).fetchone()
            if not fila:
                raise ValueError(f"Material {self.identificador_material} no existe.")
            if not bool(fila["disponible"]):
                raise RuntimeError(f"El material {self.identificador_material} ya no está disponible.")

            conexion.execute(
                "UPDATE materiales SET disponible = 0 WHERE identificador_material = ?",
                (self.identificador_material,)
            )
            if cerrar_conexion:
                conexion.commit()
            self.disponible = False
        except Exception:
            if cerrar_conexion:
                conexion.rollback()
            raise
        finally:
            if cerrar_conexion:
                conexion.close()

    def liberar(self, base_datos, conexion_externa=None):
        if self.identificador_material is None:
            raise ValueError("El material no tiene identificador asignado.")

        cerrar_conexion = False
        if conexion_externa is None:
            conexion = base_datos.conectar()
            cerrar_conexion = True
        else:
            conexion = conexion_externa

        try:
            conexion.execute(
                "UPDATE materiales SET disponible = 1, estado = 'disponible' WHERE identificador_material = ?",
                (self.identificador_material,)
            )
            if cerrar_conexion:
                conexion.commit()
            self.disponible = True
            self.estado = "disponible"
        except Exception:
            if cerrar_conexion:
                conexion.rollback()
            raise
        finally:
            if cerrar_conexion:
                conexion.close()


class DetallePedido:
    def __init__(self, id_detalle, numero_pedido, identificador_material,
                 estado_devolucion="pendiente", observaciones=None,
                 fecha_hora_devolucion=None, folio_admin_recibe=None):
        self.id_detalle = id_detalle
        self.numero_pedido = numero_pedido
        self.identificador_material = identificador_material
        self.estado_devolucion = estado_devolucion
        self.observaciones = observaciones
        self.fecha_hora_devolucion = fecha_hora_devolucion
        self.folio_admin_recibe = folio_admin_recibe

    def marcarComponenteDevuelto(self, base_datos, folio_admin_recibe,
                                 observaciones=None, fecha_hora_devolucion=None):
        if self.id_detalle is None:
            raise ValueError("El detalle de pedido no tiene id_detalle asignado.")

        marca_tiempo = fecha_hora_devolucion or datetime.now().isoformat(timespec="seconds")
        conexion = base_datos.conectar()
        try:
            conexion.execute(
                """
                UPDATE detalle_pedido
                SET estado_devolucion = 'devuelto',
                    folio_admin_recibe = ?,
                    fecha_hora_devolucion = ?,
                    observaciones = COALESCE(?, observaciones)
                WHERE id_detalle = ?
                """,
                (folio_admin_recibe, marca_tiempo, observaciones, self.id_detalle)
            )
            conexion.commit()
        except Exception:
            conexion.rollback()
            raise
        finally:
            conexion.close()

        self.estado_devolucion = "devuelto"
        self.folio_admin_recibe = folio_admin_recibe
        self.fecha_hora_devolucion = marca_tiempo
        if observaciones is not None:
            self.observaciones = observaciones

        return {
            "evento": "ComponenteDevuelto",
            "datos_evento": {"identificador_material": self.identificador_material}
        }


class Pedido:
    def __init__(self, numero_pedido, boleta_alumno, numero_total_materiales,
                 fecha_hora_solicitud, fecha_hora_max_entrega,
                 fecha_hora_aceptacion=None, folio_admin_acepta=None,
                 estado_pedido="pendiente"):
        self.numero_pedido = numero_pedido
        self.boleta_alumno = boleta_alumno
        self.numero_total_materiales = numero_total_materiales
        self.fecha_hora_solicitud = fecha_hora_solicitud
        self.fecha_hora_max_entrega = fecha_hora_max_entrega
        self.fecha_hora_aceptacion = fecha_hora_aceptacion
        self.folio_admin_acepta = folio_admin_acepta
        self.estado_pedido = estado_pedido

    def _obtener_materiales_asociados(self, conexion):
        filas = conexion.execute(
            "SELECT identificador_material FROM detalle_pedido WHERE numero_pedido = ?",
            (self.numero_pedido,)
        ).fetchall()
        return [int(f["identificador_material"]) for f in filas]

    def cancelarPedido(self, base_datos, boleta_solicitante):
        if self.numero_pedido is None:
            raise ValueError("El pedido no está registrado en la base de datos.")
        if self.boleta_alumno != boleta_solicitante:
            raise PermissionError("Solo el alumno dueño del pedido puede cancelarlo.")

        conexion = base_datos.conectar()
        try:
            fila = conexion.execute(
                "SELECT estado_pedido FROM pedidos WHERE numero_pedido = ?",
                (self.numero_pedido,)
            ).fetchone()
            if not fila:
                raise ValueError(f"Pedido {self.numero_pedido} no existe.")
            if fila["estado_pedido"] != "pendiente":
                raise RuntimeError("Solo se pueden cancelar pedidos en estado 'pendiente'.")

            conexion.execute(
                "UPDATE pedidos SET estado_pedido = 'cancelado' WHERE numero_pedido = ?",
                (self.numero_pedido,)
            )
            lista_materiales = self._obtener_materiales_asociados(conexion)
            conexion.commit()
            self.estado_pedido = "cancelado"
        except Exception:
            conexion.rollback()
            raise
        finally:
            conexion.close()

        return {
            "evento": "PedidoCancelado",
            "datos_evento": {
                "id_pedido": self.numero_pedido,
                "lista_id_materiales": lista_materiales
            }
        }

    def cancelarPorTiempoLimite(self, base_datos):
        if self.numero_pedido is None:
            raise ValueError("El pedido no está registrado en la base de datos.")

        conexion = base_datos.conectar()
        try:
            conexion.execute(
                "UPDATE pedidos SET estado_pedido = 'cancelado' WHERE numero_pedido = ? AND estado_pedido = 'pendiente'",
                (self.numero_pedido,)
            )
            lista_materiales = self._obtener_materiales_asociados(conexion)
            conexion.commit()
            self.estado_pedido = "cancelado"
        except Exception:
            conexion.rollback()
            raise
        finally:
            conexion.close()

        return {
            "evento": "PedidoCancelado",
            "datos_evento": {
                "id_pedido": self.numero_pedido,
                "lista_id_materiales": lista_materiales
            }
        }

    def verificarCierreAutomatico(self, base_datos):
        if self.numero_pedido is None:
            raise ValueError("El pedido no está registrado en la base de datos.")

        conexion = base_datos.conectar()
        try:
            pendientes = conexion.execute(
                """
                SELECT COUNT(*) AS faltantes
                FROM detalle_pedido
                WHERE numero_pedido = ? AND estado_devolucion != 'devuelto'
                """,
                (self.numero_pedido,)
            ).fetchone()["faltantes"]

            if int(pendientes) == 0:
                conexion.execute(
                    "UPDATE pedidos SET estado_pedido = 'finalizado' WHERE numero_pedido = ?",
                    (self.numero_pedido,)
                )
                conexion.commit()
                self.estado_pedido = "finalizado"
                return {
                    "evento": "PedidoCompletado",
                    "datos_evento": {"boleta_alumno": self.boleta_alumno}
                }
            return None
        except Exception:
            conexion.rollback()
            raise
        finally:
            conexion.close()


class Administrador(Usuario):
    def __init__(self, id_usuario, nombre_completo, contrasena, identificador, folio=None):
        super().__init__(id_usuario, nombre_completo, contrasena, identificador)
        self.folio = folio

    def aceptarPedido(self, base_datos, numero_pedido, fecha_hora_aceptacion=None):
        if self.folio is None:
            raise PermissionError("El administrador no tiene un folio válido.")

        marca_tiempo = fecha_hora_aceptacion or datetime.now().isoformat(timespec="seconds")
        conexion = base_datos.conectar()
        try:
            fila = conexion.execute(
                "SELECT estado_pedido FROM pedidos WHERE numero_pedido = ?",
                (numero_pedido,)
            ).fetchone()
            if not fila:
                raise ValueError(f"El pedido {numero_pedido} no existe.")
            if fila["estado_pedido"] != "pendiente":
                raise RuntimeError("Solo se pueden aceptar pedidos en estado 'pendiente'.")

            conexion.execute(
                """
                UPDATE pedidos
                SET estado_pedido = 'aceptado',
                    folio_admin_acepta = ?,
                    fecha_hora_aceptacion = ?
                WHERE numero_pedido = ?
                """,
                (self.folio, marca_tiempo, numero_pedido)
            )
            conexion.commit()
        except Exception:
            conexion.rollback()
            raise
        finally:
            conexion.close()

        return {
            "numero_pedido": numero_pedido,
            "estado_pedido": "aceptado",
            "folio_admin_acepta": self.folio,
            "fecha_hora_aceptacion": marca_tiempo
        }

    def rechazarPedido(self, base_datos, numero_pedido, confirmacion_visual=True):
        if not confirmacion_visual:
            raise ValueError("Se requiere confirmación visual obligatoria para rechazar el pedido.")

        conexion = base_datos.conectar()
        try:
            fila = conexion.execute(
                "SELECT estado_pedido FROM pedidos WHERE numero_pedido = ?",
                (numero_pedido,)
            ).fetchone()
            if not fila:
                raise ValueError(f"El pedido {numero_pedido} no existe.")
            if fila["estado_pedido"] != "pendiente":
                raise RuntimeError("Solo se pueden rechazar pedidos en estado 'pendiente'.")

            conexion.execute(
                "UPDATE pedidos SET estado_pedido = 'rechazado' WHERE numero_pedido = ?",
                (numero_pedido,)
            )
            filas_mat = conexion.execute(
                "SELECT identificador_material FROM detalle_pedido WHERE numero_pedido = ?",
                (numero_pedido,)
            ).fetchall()
            lista_materiales = [int(r["identificador_material"]) for r in filas_mat]
            conexion.commit()
        except Exception:
            conexion.rollback()
            raise
        finally:
            conexion.close()

        return {
            "evento": "PedidoRechazado",
            "datos_evento": {
                "id_pedido": numero_pedido,
                "lista_id_materiales": lista_materiales
            }
        }

    def bloquearAlumno(self, base_datos, boleta, motivo):
        if not motivo or not motivo.strip():
            raise ValueError("El motivo de sanción es obligatorio para bloquear a un alumno.")

        conexion = base_datos.conectar()
        try:
            cursor_bd = conexion.execute(
                "UPDATE alumnos SET estado = 'bloqueado', motivo_sancion = ? WHERE boleta = ?",
                (motivo.strip(), boleta)
            )
            if cursor_bd.rowcount == 0:
                raise ValueError(f"No existe alumno con boleta {boleta}.")
            conexion.commit()
        except Exception:
            conexion.rollback()
            raise
        finally:
            conexion.close()

        return {
            "boleta": boleta,
            "estado": "bloqueado",
            "motivo_sancion": motivo.strip()
        }

    def crearAdministrador(self, base_datos, nombre_completo, contrasena_plana, folio_asignado=None):
        if not self.sesion_activa or self.folio is None:
            raise PermissionError("Se requiere un administrador autenticado para crear otro administrador.")
        if len(contrasena_plana) < 8:
            raise ValueError("La contraseña debe tener al menos 8 caracteres.")

        contrasena_encriptada = hashear_contrasena(contrasena_plana)
        conexion = base_datos.conectar()
        try:
            if folio_asignado is None:
                fila_max = conexion.execute(
                    "SELECT COALESCE(MAX(folio), 20200000) AS max_folio FROM administradores"
                ).fetchone()
                folio_nuevo = int(fila_max["max_folio"]) + 1
            else:
                folio_nuevo = int(folio_asignado)

            cursor_usr = conexion.execute(
                "INSERT INTO usuarios (nombre_completo, contrasena, identificador) VALUES (?, ?, ?)",
                (nombre_completo.strip(), contrasena_encriptada, str(folio_nuevo))
            )
            id_usr = int(cursor_usr.lastrowid)

            conexion.execute(
                "INSERT INTO administradores (folio, id_usuario) VALUES (?, ?)",
                (folio_nuevo, id_usr)
            )
            conexion.commit()
        except Exception:
            conexion.rollback()
            raise
        finally:
            conexion.close()

        return Administrador(
            id_usuario=id_usr,
            nombre_completo=nombre_completo.strip(),
            contrasena=contrasena_encriptada,
            identificador=str(folio_nuevo),
            folio=folio_nuevo
        )

    def consultarCuentaActiva(self):
        if not self.sesion_activa:
            raise PermissionError("La sesión del administrador no está activa.")
        return {
            "id_usuario": self.id_usuario,
            "nombre_completo": self.nombre_completo,
            "folio": self.folio,
            "identificador": self.identificador
        }


# REPOSITORIO ORM

class RepositorioORM:
    def __init__(self, base_datos):
        self.base_datos = base_datos

    # 1. Acceso y autenticacion
    def registrar_alumno(self, nombre_completo, boleta, correo_electronico, contrasena_plana):
        if not all([nombre_completo.strip(), boleta.strip(), correo_electronico.strip(), contrasena_plana]):
            raise ValueError("Todos los campos son obligatorios.")
        if len(boleta.strip()) != 10 or not boleta.strip().isdigit():
            raise ValueError("boleta inválida")
        if not correo_electronico.strip().endswith("@alumno.ipn.mx"):
            raise ValueError("El correo electrónico debe terminar en @alumno.ipn.mx.")
        if len(contrasena_plana) < 8:
            raise ValueError("La contraseña debe tener un mínimo de 8 caracteres.")

        contrasena_encriptada = hashear_contrasena(contrasena_plana)
        conexion = self.base_datos.conectar()
        try:
            duplicado = conexion.execute(
                "SELECT 1 FROM alumnos WHERE boleta = ? OR EXISTS (SELECT 1 FROM usuarios WHERE identificador = ?)",
                (boleta.strip(), boleta.strip())
            ).fetchone()
            if duplicado:
                raise ValueError("boleta inválida")

            cursor_usuario = conexion.execute(
                "INSERT INTO usuarios (nombre_completo, contrasena, identificador) VALUES (?, ?, ?)",
                (nombre_completo.strip(), contrasena_encriptada, boleta.strip())
            )
            id_usuario = int(cursor_usuario.lastrowid)

            conexion.execute(
                "INSERT INTO alumnos (boleta, id_usuario, correo_electronico, estado, motivo_sancion) VALUES (?, ?, ?, 'activo', NULL)",
                (boleta.strip(), id_usuario, correo_electronico.strip())
            )
            conexion.commit()
        except Exception:
            conexion.rollback()
            raise
        finally:
            conexion.close()

        return Alumno(
            id_usuario=id_usuario,
            nombre_completo=nombre_completo.strip(),
            contrasena=contrasena_encriptada,
            identificador=boleta.strip(),
            boleta=boleta.strip(),
            correo_electronico=correo_electronico.strip(),
            estado="activo",
            motivo_sancion=None
        )

    def autenticar_usuario(self, identificador, contrasena_plana):
        contrasena_encriptada = hashear_contrasena(contrasena_plana)
        conexion = self.base_datos.conectar()
        try:
            fila_u = conexion.execute(
                "SELECT * FROM usuarios WHERE identificador = ? AND contrasena = ?",
                (str(identificador).strip(), contrasena_encriptada)
            ).fetchone()
            if not fila_u:
                raise PermissionError("Credenciales inválidas.")

            fila_alumno = conexion.execute(
                "SELECT * FROM alumnos WHERE id_usuario = ?",
                (fila_u["id_usuario"],)
            ).fetchone()
            if fila_alumno:
                entidad = Alumno(
                    id_usuario=fila_u["id_usuario"],
                    nombre_completo=fila_u["nombre_completo"],
                    contrasena=fila_u["contrasena"],
                    identificador=fila_u["identificador"],
                    boleta=fila_alumno["boleta"],
                    correo_electronico=fila_alumno["correo_electronico"],
                    estado=fila_alumno["estado"],
                    motivo_sancion=fila_alumno["motivo_sancion"]
                )
                return {"rol": "alumno", "entidad": entidad}

            fila_admin = conexion.execute(
                "SELECT * FROM administradores WHERE id_usuario = ?",
                (fila_u["id_usuario"],)
            ).fetchone()
            if fila_admin:
                entidad_admin = Administrador(
                    id_usuario=fila_u["id_usuario"],
                    nombre_completo=fila_u["nombre_completo"],
                    contrasena=fila_u["contrasena"],
                    identificador=fila_u["identificador"],
                    folio=int(fila_admin["folio"])
                )
                return {"rol": "administrador", "entidad": entidad_admin}

            raise RuntimeError("El usuario no tiene un rol asignado en alumnos ni administradores.")
        finally:
            conexion.close()

    # 2. Usuarios y sanciones
    def revalidarEstado(self, boleta, conexion_externa=None):
        cerrar = False
        if conexion_externa is None:
            conexion = self.base_datos.conectar()
            cerrar = True
        else:
            conexion = conexion_externa

        try:
            fila = conexion.execute(
                "SELECT estado FROM alumnos WHERE boleta = ?",
                (boleta,)
            ).fetchone()
            if not fila:
                raise ValueError(f"Alumno {boleta} no encontrado.")
            return str(fila["estado"])
        finally:
            if cerrar:
                conexion.close()

    def aplicarSuspension(self, boleta, motivo="Tiempo de préstamo vencido"):
        conexion = self.base_datos.conectar()
        try:
            cursor_bd = conexion.execute(
                """
                UPDATE alumnos
                SET estado = 'suspendido',
                    motivo_sancion = COALESCE(motivo_sancion, ?)
                WHERE boleta = ? AND estado = 'activo'
                """,
                (motivo, boleta)
            )
            conexion.commit()
            return cursor_bd.rowcount > 0
        except Exception:
            conexion.rollback()
            raise
        finally:
            conexion.close()

    def reactivarPorDevolucionTotal(self, boleta):
        conexion = self.base_datos.conectar()
        try:
            cursor_bd = conexion.execute(
                "UPDATE alumnos SET estado = 'activo', motivo_sancion = NULL WHERE boleta = ? AND estado = 'suspendido'",
                (boleta,)
            )
            conexion.commit()
            return cursor_bd.rowcount > 0
        except Exception:
            conexion.rollback()
            raise
        finally:
            conexion.close()

    def quitarSanciones(self, boleta):
        conexion = self.base_datos.conectar()
        try:
            conexion.execute(
                "UPDATE alumnos SET estado = 'activo', motivo_sancion = NULL WHERE boleta = ?",
                (boleta,)
            )
            conexion.commit()
        except Exception:
            conexion.rollback()
            raise
        finally:
            conexion.close()

    def buscar_alumnos_directorio(self, termino=""):
        patron = f"%{termino.strip()}%"
        conexion = self.base_datos.conectar()
        try:
            filas = conexion.execute(
                """
                SELECT a.boleta, u.nombre_completo, a.correo_electronico,
                       a.estado, a.motivo_sancion
                FROM alumnos a
                JOIN usuarios u ON u.id_usuario = a.id_usuario
                WHERE u.nombre_completo LIKE ? OR a.boleta LIKE ? OR a.correo_electronico LIKE ?
                ORDER BY u.nombre_completo ASC
                """,
                (patron, patron, patron)
            ).fetchall()
            return [dict(f) for f in filas]
        finally:
            conexion.close()

    # 3. Inventario
    def listarMateriales(self, solo_disponibles=False):
        consulta_sql = "SELECT * FROM materiales"
        if solo_disponibles:
            consulta_sql += " WHERE disponible = 1"
        consulta_sql += " ORDER BY nombre_componente ASC, identificador_material ASC"

        conexion = self.base_datos.conectar()
        try:
            filas = conexion.execute(consulta_sql).fetchall()
            return [self._fila_a_material(f) for f in filas]
        finally:
            conexion.close()

    def buscarMaterial(self, termino):
        patron = f"%{termino.strip()}%"
        conexion = self.base_datos.conectar()
        try:
            filas = conexion.execute(
                """
                SELECT * FROM materiales
                WHERE nombre_componente LIKE ?
                   OR numero_serie LIKE ?
                   OR CAST(identificador_material AS TEXT) = ?
                ORDER BY nombre_componente ASC
                """,
                (patron, patron, termino.strip())
            ).fetchall()
            return [self._fila_a_material(f) for f in filas]
        finally:
            conexion.close()

    def procesarLiberacion(self, lista_id_materiales):
        conexion = self.base_datos.conectar()
        try:
            for id_mat in lista_id_materiales:
                conexion.execute(
                    "UPDATE materiales SET disponible = 1, estado = 'disponible' WHERE identificador_material = ?",
                    (id_mat,)
                )
            conexion.commit()
        except Exception:
            conexion.rollback()
            raise
        finally:
            conexion.close()

    def _fila_a_material(self, fila):
        return Material(
            identificador_material=int(fila["identificador_material"]),
            nombre_componente=fila["nombre_componente"],
            descripcion_breve=fila["descripcion_breve"] or "",
            disponible=bool(fila["disponible"]),
            numero_serie=fila["numero_serie"],
            precio_reposicion=float(fila["precio_reposicion"]),
            fotografia_componente_fisico=fila["fotografia_componente_fisico"],
            estado=fila["estado"]
        )

    # 4. Prestamos
    def crearPedido(self, boleta_alumno, lista_id_materiales, duracion_horas=1.5, ahora=None, validar_horario=True):
        if not lista_id_materiales:
            raise ValueError("El pedido debe incluir al menos un material.")
        if len(lista_id_materiales) > 8:
            raise ValueError("Se excede el límite máximo de 8 piezas por pedido.")
        if len(set(lista_id_materiales)) != len(lista_id_materiales):
            raise ValueError("No se puede repetir el mismo identificador físico en un pedido.")

        reloj = ahora or datetime.now()
        if validar_horario:
            duracion_horas = self.validarHorarioLaboratorio(reloj, duracion_horas)

        fecha_solicitud = reloj.isoformat(timespec="seconds")
        fecha_max_entrega = (reloj + timedelta(hours=duracion_horas)).isoformat(timespec="seconds")

        conexion = self.base_datos.conectar()
        try:
            estado_alumno = self.revalidarEstado(boleta_alumno, conexion_externa=conexion)
            if estado_alumno != "activo":
                raise PermissionError(f"El alumno {boleta_alumno} no puede solicitar préstamos.")

            pedido_activo = conexion.execute(
                """
                SELECT numero_pedido FROM pedidos
                WHERE boleta_alumno = ?
                  AND estado_pedido IN ('pendiente', 'aceptado', 'vencido')
                """,
                (boleta_alumno,)
            ).fetchone()
            if pedido_activo:
                raise RuntimeError("El alumno ya cuenta con un pedido activo.")

            conteo_por_nombre = {}
            for id_mat in lista_id_materiales:
                fila_mat = conexion.execute(
                    "SELECT * FROM materiales WHERE identificador_material = ?",
                    (id_mat,)
                ).fetchone()
                if not fila_mat:
                    raise ValueError(f"El material con ID {id_mat} no existe.")
                mat_obj = self._fila_a_material(fila_mat)
                nombre_min = mat_obj.nombre_componente.lower()
                conteo_por_nombre[nombre_min] = conteo_por_nombre.get(nombre_min, 0) + 1
                if conteo_por_nombre[nombre_min] > 4:
                    raise ValueError(f"Se excede el límite de 4 piezas iguales para '{mat_obj.nombre_componente}'.")
                mat_obj.reservar(self.base_datos, conexion_externa=conexion)

            cursor_ped = conexion.execute(
                """
                INSERT INTO pedidos (
                    boleta_alumno,
                    numero_total_materiales,
                    fecha_hora_solicitud,
                    fecha_hora_aceptacion,
                    folio_admin_acepta,
                    estado_pedido,
                    fecha_hora_max_entrega
                ) VALUES (?, ?, ?, NULL, NULL, 'pendiente', ?)
                """,
                (boleta_alumno, len(lista_id_materiales), fecha_solicitud, fecha_max_entrega)
            )
            num_pedido = int(cursor_ped.lastrowid)

            for id_mat in lista_id_materiales:
                conexion.execute(
                    """
                    INSERT INTO detalle_pedido (
                        numero_pedido,
                        identificador_material,
                        estado_devolucion,
                        observaciones,
                        folio_admin_recibe,
                        fecha_hora_devolucion
                    ) VALUES (?, ?, 'pendiente', NULL, NULL, NULL)
                    """,
                    (num_pedido, id_mat)
                )
            conexion.commit()
        except Exception:
            conexion.rollback()
            raise
        finally:
            conexion.close()

        return Pedido(
            numero_pedido=num_pedido,
            boleta_alumno=boleta_alumno,
            numero_total_materiales=len(lista_id_materiales),
            fecha_hora_solicitud=fecha_solicitud,
            fecha_hora_max_entrega=fecha_max_entrega,
            estado_pedido="pendiente"
        )

    def consultarPrestamoActivo(self, boleta_alumno):
        conexion = self.base_datos.conectar()
        try:
            fila_p = conexion.execute(
                """
                SELECT * FROM pedidos
                WHERE boleta_alumno = ?
                  AND estado_pedido IN ('pendiente', 'aceptado', 'vencido')
                ORDER BY numero_pedido DESC
                LIMIT 1
                """,
                (boleta_alumno,)
            ).fetchone()
            if not fila_p:
                return None

            detalles = conexion.execute(
                """
                SELECT dp.*, m.nombre_componente, m.numero_serie, m.fotografia_componente_fisico
                FROM detalle_pedido dp
                JOIN materiales m ON m.identificador_material = dp.identificador_material
                WHERE dp.numero_pedido = ?
                """,
                (fila_p["numero_pedido"],)
            ).fetchall()

            resultado = dict(fila_p)
            resultado["detalles"] = [dict(d) for d in detalles]
            return resultado
        finally:
            conexion.close()

    def consultarHistorial(self, boleta_alumno):
        conexion = self.base_datos.conectar()
        try:
            filas = conexion.execute(
                """
                SELECT p.numero_pedido, p.boleta_alumno, p.fecha_hora_solicitud,
                       p.fecha_hora_aceptacion, p.fecha_hora_max_entrega, p.estado_pedido,
                       dp.id_detalle, dp.identificador_material, dp.estado_devolucion,
                       dp.fecha_hora_devolucion, dp.observaciones,
                       m.nombre_componente, m.numero_serie
                FROM pedidos p
                JOIN detalle_pedido dp ON dp.numero_pedido = p.numero_pedido
                JOIN materiales m ON m.identificador_material = dp.identificador_material
                WHERE p.boleta_alumno = ?
                ORDER BY p.fecha_hora_solicitud DESC, p.numero_pedido DESC
                """,
                (boleta_alumno,)
            ).fetchall()
            return [dict(f) for f in filas]
        finally:
            conexion.close()

    def buscar_devoluciones_pendientes(self, termino=""):
        patron = f"%{termino.strip()}%"
        conexion = self.base_datos.conectar()
        try:
            filas = conexion.execute(
                """
                SELECT dp.id_detalle, dp.numero_pedido, dp.identificador_material,
                       dp.estado_devolucion, m.nombre_componente, m.numero_serie,
                       p.boleta_alumno, u.nombre_completo AS nombre_alumno,
                       p.fecha_hora_solicitud, p.fecha_hora_aceptacion, p.fecha_hora_max_entrega
                FROM detalle_pedido dp
                JOIN pedidos p    ON p.numero_pedido = dp.numero_pedido
                JOIN materiales m ON m.identificador_material = dp.identificador_material
                JOIN alumnos a    ON a.boleta = p.boleta_alumno
                JOIN usuarios u   ON u.id_usuario = a.id_usuario
                WHERE dp.estado_devolucion = 'pendiente'
                  AND p.estado_pedido IN ('aceptado', 'vencido')
                  AND (
                      m.nombre_componente LIKE ?
                      OR m.numero_serie LIKE ?
                      OR CAST(dp.identificador_material AS TEXT) = ?
                      OR p.boleta_alumno LIKE ?
                      OR u.nombre_completo LIKE ?
                  )
                ORDER BY p.fecha_hora_max_entrega ASC
                """,
                (patron, patron, termino.strip(), patron, patron)
            ).fetchall()
            return [dict(f) for f in filas]
        finally:
            conexion.close()

    # 5. Motor de reglas y temporizadores
    def validarHorarioLaboratorio(self, reloj_servidor, duracion_solicitada_horas):
        hora_decimal = reloj_servidor.hour + (reloj_servidor.minute / 60.0)
        if hora_decimal < 7.0 or hora_decimal >= 21.0:
            raise ValueError("El laboratorio opera únicamente en horario hábil de 07:00 a 21:00 h.")
        if duracion_solicitada_horas not in (1.5, 3.0):
            raise ValueError("Las duraciones de préstamo válidas son 1.5 horas o 3.0 horas.")
        if hora_decimal >= 20.0:
            return 1.5
        return duracion_solicitada_horas

    def verificarRecogida(self, reloj_servidor=None):
        ahora = reloj_servidor or datetime.now()
        limite = (ahora - timedelta(minutes=30)).isoformat(timespec="seconds")
        eventos = []

        conexion = self.base_datos.conectar()
        try:
            pedidos_expirados = conexion.execute(
                "SELECT numero_pedido, boleta_alumno FROM pedidos WHERE estado_pedido = 'pendiente' AND fecha_hora_solicitud <= ?",
                (limite,)
            ).fetchall()

            for ped in pedidos_expirados:
                mats = conexion.execute(
                    "SELECT identificador_material FROM detalle_pedido WHERE numero_pedido = ?",
                    (ped["numero_pedido"],)
                ).fetchall()
                eventos.append({
                    "evento": "ToleranciaRecogidaAgotada",
                    "datos_evento": {
                        "id_pedido": int(ped["numero_pedido"]),
                        "boleta_alumno": ped["boleta_alumno"],
                        "lista_id_materiales": [int(m["identificador_material"]) for m in mats]
                    }
                })
            return eventos
        finally:
            conexion.close()

    def verificarDevolucion(self, reloj_servidor=None):
        ahora_iso = (reloj_servidor or datetime.now()).isoformat(timespec="seconds")
        eventos = []

        conexion = self.base_datos.conectar()
        try:
            vencidos = conexion.execute(
                "SELECT numero_pedido, boleta_alumno FROM pedidos WHERE estado_pedido = 'aceptado' AND fecha_hora_max_entrega < ?",
                (ahora_iso,)
            ).fetchall()

            for ped in vencidos:
                conexion.execute(
                    "UPDATE pedidos SET estado_pedido = 'vencido' WHERE numero_pedido = ?",
                    (ped["numero_pedido"],)
                )
                eventos.append({
                    "evento": "TiempoPrestamoVencido",
                    "datos_evento": {
                        "id_pedido": int(ped["numero_pedido"]),
                        "boleta_alumno": ped["boleta_alumno"]
                    }
                })
            conexion.commit()
            return eventos
        except Exception:
            conexion.rollback()
            raise
        finally:
            conexion.close()

    def ejecutarConciliacion(self):
        conexion = self.base_datos.conectar()
        try:
            cursor_bd = conexion.execute(
                """
                UPDATE materiales
                SET disponible = 1,
                    estado = 'disponible'
                WHERE disponible = 0
                  AND identificador_material NOT IN (
                      SELECT dp.identificador_material
                      FROM detalle_pedido dp
                      JOIN pedidos p ON p.numero_pedido = dp.numero_pedido
                      WHERE p.estado_pedido IN ('pendiente', 'aceptado', 'vencido')
                        AND dp.estado_devolucion = 'pendiente'
                  )
                """
            )
            conexion.commit()
            return int(cursor_bd.rowcount)
        except Exception:
            conexion.rollback()
            raise
        finally:
            conexion.close()

    # ------------------------------------------------------------------
    # [INTEGRACIÓN] 6. Consultas adicionales para la capa 2
    # Solo lectura. No modifican ningún método anterior de la capa 3.
    # ------------------------------------------------------------------
    def obtenerAlumnoPorBoleta(self, boleta):
        conexion = self.base_datos.conectar()
        try:
            fila = conexion.execute(
                """
                SELECT u.id_usuario, u.nombre_completo, u.contrasena, u.identificador,
                       a.boleta, a.correo_electronico, a.estado, a.motivo_sancion
                FROM alumnos a
                JOIN usuarios u ON u.id_usuario = a.id_usuario
                WHERE a.boleta = ?
                """,
                (str(boleta).strip(),)
            ).fetchone()
            if not fila:
                return None
            return Alumno(
                id_usuario=fila["id_usuario"],
                nombre_completo=fila["nombre_completo"],
                contrasena=fila["contrasena"],
                identificador=fila["identificador"],
                boleta=fila["boleta"],
                correo_electronico=fila["correo_electronico"],
                estado=fila["estado"],
                motivo_sancion=fila["motivo_sancion"]
            )
        finally:
            conexion.close()

    def obtenerAdministradorPorFolio(self, folio):
        conexion = self.base_datos.conectar()
        try:
            fila = conexion.execute(
                """
                SELECT u.id_usuario, u.nombre_completo, u.contrasena, u.identificador, ad.folio
                FROM administradores ad
                JOIN usuarios u ON u.id_usuario = ad.id_usuario
                WHERE ad.folio = ?
                """,
                (int(folio),)
            ).fetchone()
            if not fila:
                return None
            return Administrador(
                id_usuario=fila["id_usuario"],
                nombre_completo=fila["nombre_completo"],
                contrasena=fila["contrasena"],
                identificador=fila["identificador"],
                folio=int(fila["folio"])
            )
        finally:
            conexion.close()

    def listarAdministradores(self):
        conexion = self.base_datos.conectar()
        try:
            filas = conexion.execute(
                """
                SELECT ad.folio, u.nombre_completo
                FROM administradores ad
                JOIN usuarios u ON u.id_usuario = ad.id_usuario
                ORDER BY ad.folio ASC
                """
            ).fetchall()
            return [dict(f) for f in filas]
        finally:
            conexion.close()

    def contarAdministradores(self):
        conexion = self.base_datos.conectar()
        try:
            return int(conexion.execute("SELECT COUNT(*) FROM administradores").fetchone()[0])
        finally:
            conexion.close()

    def obtenerMaterialPorId(self, identificador_material):
        conexion = self.base_datos.conectar()
        try:
            fila = conexion.execute(
                "SELECT * FROM materiales WHERE identificador_material = ?",
                (int(identificador_material),)
            ).fetchone()
            return self._fila_a_material(fila) if fila else None
        finally:
            conexion.close()

    def obtenerPedido(self, numero_pedido):
        conexion = self.base_datos.conectar()
        try:
            fila = conexion.execute(
                "SELECT * FROM pedidos WHERE numero_pedido = ?",
                (int(numero_pedido),)
            ).fetchone()
            if not fila:
                return None
            return Pedido(
                numero_pedido=int(fila["numero_pedido"]),
                boleta_alumno=fila["boleta_alumno"],
                numero_total_materiales=int(fila["numero_total_materiales"]),
                fecha_hora_solicitud=fila["fecha_hora_solicitud"],
                fecha_hora_max_entrega=fila["fecha_hora_max_entrega"],
                fecha_hora_aceptacion=fila["fecha_hora_aceptacion"],
                folio_admin_acepta=fila["folio_admin_acepta"],
                estado_pedido=fila["estado_pedido"]
            )
        finally:
            conexion.close()

    def obtenerDetallePedido(self, id_detalle):
        conexion = self.base_datos.conectar()
        try:
            fila = conexion.execute(
                "SELECT * FROM detalle_pedido WHERE id_detalle = ?",
                (int(id_detalle),)
            ).fetchone()
            if not fila:
                return None
            return DetallePedido(
                id_detalle=int(fila["id_detalle"]),
                numero_pedido=int(fila["numero_pedido"]),
                identificador_material=int(fila["identificador_material"]),
                estado_devolucion=fila["estado_devolucion"],
                observaciones=fila["observaciones"],
                fecha_hora_devolucion=fila["fecha_hora_devolucion"],
                folio_admin_recibe=fila["folio_admin_recibe"]
            )
        finally:
            conexion.close()

    def listarSolicitudesAdmin(self, desde_iso):
        """Pedidos pendientes (todos) y pedidos resueltos desde 'desde_iso' (Req 5.1)."""
        conexion = self.base_datos.conectar()
        try:
            pedidos = conexion.execute(
                """
                SELECT p.*, u.nombre_completo AS nombre_alumno,
                       ua.nombre_completo AS nombre_admin_acepta
                FROM pedidos p
                JOIN alumnos a  ON a.boleta = p.boleta_alumno
                JOIN usuarios u ON u.id_usuario = a.id_usuario
                LEFT JOIN administradores ad ON ad.folio = p.folio_admin_acepta
                LEFT JOIN usuarios ua ON ua.id_usuario = ad.id_usuario
                WHERE p.estado_pedido = 'pendiente'
                   OR (p.estado_pedido != 'cancelado' AND p.fecha_hora_solicitud >= ?)
                ORDER BY p.fecha_hora_solicitud ASC
                """,
                (desde_iso,)
            ).fetchall()

            resultado = []
            for p in pedidos:
                materiales = conexion.execute(
                    """
                    SELECT m.identificador_material, m.nombre_componente, m.numero_serie
                    FROM detalle_pedido dp
                    JOIN materiales m ON m.identificador_material = dp.identificador_material
                    WHERE dp.numero_pedido = ?
                    ORDER BY dp.id_detalle ASC
                    """,
                    (p["numero_pedido"],)
                ).fetchall()
                fila = dict(p)
                fila["materiales"] = [dict(m) for m in materiales]
                resultado.append(fila)
            return resultado
        finally:
            conexion.close()

    def listarPiezasPrestadas(self, desde_iso):
        """Piezas por devolver de pedidos entregados, más las devueltas desde 'desde_iso' (Req 5.2)."""
        conexion = self.base_datos.conectar()
        try:
            filas = conexion.execute(
                """
                SELECT dp.id_detalle, dp.numero_pedido, dp.identificador_material,
                       dp.estado_devolucion, dp.fecha_hora_devolucion, dp.folio_admin_recibe,
                       m.nombre_componente, m.numero_serie,
                       p.boleta_alumno, p.estado_pedido, u.nombre_completo AS nombre_alumno,
                       p.fecha_hora_solicitud, p.fecha_hora_aceptacion, p.fecha_hora_max_entrega
                FROM detalle_pedido dp
                JOIN pedidos p    ON p.numero_pedido = dp.numero_pedido
                JOIN materiales m ON m.identificador_material = dp.identificador_material
                JOIN alumnos a    ON a.boleta = p.boleta_alumno
                JOIN usuarios u   ON u.id_usuario = a.id_usuario
                WHERE (dp.estado_devolucion = 'pendiente' AND p.estado_pedido IN ('aceptado', 'vencido'))
                   OR (dp.estado_devolucion = 'devuelto' AND dp.fecha_hora_devolucion >= ?)
                ORDER BY p.fecha_hora_max_entrega ASC, dp.id_detalle ASC
                """,
                (desde_iso,)
            ).fetchall()
            return [dict(f) for f in filas]
        finally:
            conexion.close()


# PRUEBA DE VERIFICACION

def _ejecutar_pruebas_verificacion():
    ruta_prueba = "test_laboratorio.db"
    if os.path.exists(ruta_prueba):
        os.remove(ruta_prueba)

    base_datos = BaseDatosSQLite(ruta_prueba)
    repo = RepositorioORM(base_datos)

    # 1. Crear administrador inicial en BD
    conexion = base_datos.conectar()
    cursor_ini = conexion.execute(
        "INSERT INTO usuarios (nombre_completo, contrasena, identificador) VALUES (?, ?, ?)",
        ("Ana López Ortega", hashear_contrasena("admin12345"), "20200001")
    )
    conexion.execute(
        "INSERT INTO administradores (folio, id_usuario) VALUES (?, ?)",
        (20200001, cursor_ini.lastrowid)
    )
    conexion.commit()
    conexion.close()

    sesion_admin = repo.autenticar_usuario("20200001", "admin12345")
    assert sesion_admin["rol"] == "administrador"
    admin = sesion_admin["entidad"]
    nuevo_admin = admin.crearAdministrador(base_datos, "Juan Pérez", "staff12345")
    assert nuevo_admin.folio == 20200002

    # 2. Registrar alumno
    alumno = repo.registrar_alumno(
        nombre_completo="Daniela Hernández López",
        boleta="2026630148",
        correo_electronico="daniela.hl@alumno.ipn.mx",
        contrasena_plana="alumno12345"
    )
    assert alumno.boleta == "2026630148"

    try:
        repo.registrar_alumno("Otro Alumno", "2026630148", "otro@alumno.ipn.mx", "alumno12345")
        raise AssertionError("Debió lanzar error por boleta duplicada.")
    except ValueError as error_boleta:
        assert str(error_boleta) == "boleta inválida"

    # 3. Registrar materiales
    m1 = Material(None, "Multímetro digital Fluke 117", "Multímetro digital True RMS", True, "FL117-2024-008745", 4500.00, "fluke117.jpg")
    m2 = Material(None, "Osciloscopio digital Rigol DS1054Z", "Osciloscopio 4 canales 50 MHz", True, "DS1054Z-2023-000219", 9800.00, "ds1054z.jpg")
    id_m1 = m1.registrarMaterial(base_datos)
    id_m2 = m2.registrarMaterial(base_datos)

    # 4. Crear pedido
    hora_prueba = datetime(2026, 11, 10, 10, 0, 0)
    pedido = repo.crearPedido(
        boleta_alumno=alumno.boleta,
        lista_id_materiales=[id_m1, id_m2],
        duracion_horas=3.0,
        ahora=hora_prueba
    )
    assert pedido.estado_pedido == "pendiente"
    assert len(repo.listarMateriales(solo_disponibles=True)) == 0

    # 5. Administrador acepta el pedido
    admin.aceptarPedido(base_datos, pedido.numero_pedido, fecha_hora_aceptacion="2026-11-10T10:10:00")
    activo = repo.consultarPrestamoActivo(alumno.boleta)
    assert activo is not None and activo["estado_pedido"] == "aceptado"

    # 6. Simular vencimiento de tiempo de entrega
    eventos_vencidos = repo.verificarDevolucion(datetime(2026, 11, 10, 14, 0, 0))
    assert len(eventos_vencidos) == 1
    assert eventos_vencidos[0]["evento"] == "TiempoPrestamoVencido"
    repo.aplicarSuspension(alumno.boleta)
    assert repo.revalidarEstado(alumno.boleta) == "suspendido"

    # 7. Devolver componentes y verificar cierre automatico
    detalles = activo["detalles"]
    for d in detalles:
        detalle_obj = DetallePedido(
            id_detalle=d["id_detalle"],
            numero_pedido=d["numero_pedido"],
            identificador_material=d["identificador_material"]
        )
        ev_comp = detalle_obj.marcarComponenteDevuelto(base_datos, folio_admin_recibe=admin.folio)
        repo.procesarLiberacion([ev_comp["datos_evento"]["identificador_material"]])

    ev_cierre = pedido.verificarCierreAutomatico(base_datos)
    assert ev_cierre is not None and ev_cierre["evento"] == "PedidoCompletado"
    repo.reactivarPorDevolucionTotal(alumno.boleta)
    assert repo.revalidarEstado(alumno.boleta) == "activo"
    assert len(repo.listarMateriales(solo_disponibles=True)) == 2

    if os.path.exists(ruta_prueba):
        os.remove(ruta_prueba)

    print("Verificación SQLite + Repositorio ORM exitosa: las 6 tablas y reglas operan sin errores.")


if __name__ == "__main__":
    _ejecutar_pruebas_verificacion()
