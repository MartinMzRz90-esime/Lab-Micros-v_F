"""
Capa 2 - Lógica de negocio
GestorAdministradores  (Controlador CRUD clásico)

Requisitos: F-5.0 (almacenamiento de administradores), F-5.6 (creación de
cuentas con folio automático), I-5.10, I-5.11 (gestor de administradores).

Diseño v3.1:
  - gestionarAlta() usa Administrador.crearAdministrador(): requiere un
    administrador autenticado, guarda la contraseña con hash y asigna un
    folio único.
  - Permite consultar el nombre y folio de la cuenta en sesión.
"""

import sqlite3

from .errores import ErrorConflicto, ErrorPermiso, ErrorValidacion


class GestorAdministradores:
    def __init__(self, repositorio, base_datos):
        self.repo = repositorio
        self.base_datos = base_datos

    def consultarCuentaActiva(self, administrador):
        try:
            cuenta = administrador.consultarCuentaActiva()
        except PermissionError as error:
            raise ErrorPermiso(str(error)) from None
        return {"nombreCompleto": cuenta["nombre_completo"], "folio": cuenta["folio"]}

    def listarAdministradores(self):
        return [{"nombreCompleto": a["nombre_completo"], "folio": a["folio"]}
                for a in self.repo.listarAdministradores()]

    def gestionarAlta(self, administrador, nombre_completo, contrasena):
        nombre_completo = str(nombre_completo or "").strip()
        contrasena = str(contrasena or "")
        if not nombre_completo or not contrasena:
            raise ErrorValidacion("El nombre completo y la contraseña son obligatorios.")
        if len(contrasena) < 8:
            raise ErrorValidacion("La contraseña debe tener mínimo 8 caracteres.")
        try:
            nuevo = administrador.crearAdministrador(self.base_datos, nombre_completo, contrasena)
        except PermissionError as error:
            raise ErrorPermiso(str(error)) from None
        except ValueError as error:
            raise ErrorValidacion(str(error)) from None
        except sqlite3.IntegrityError:
            raise ErrorConflicto("No se pudo asignar un folio único. Inténtalo de nuevo.") from None
        return {"nombreCompleto": nuevo.nombre_completo, "folio": nuevo.folio}
