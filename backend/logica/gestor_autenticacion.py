"""
Capa 2 - Lógica de negocio
GestorAutenticacion  (Módulo de Acceso y Autenticación)

Requisitos: F-1.3 (identificador de rol), F-2.0 a F-2.3 y F-2.6 (registro y
validaciones), F-2.7 y F-5.3 (cierre de sesión), I-1.2 (login dual), I-2.9
(mensaje "Número de boleta invalido").

Diseño v3.1:
  - verificarSesion(): valida firma, expiración y rol del token en CADA petición.
  - generarToken(): emite el token de acceso al iniciar sesión.
  - validarRegistro(): boleta de 10 dígitos, correo @alumno.ipn.mx,
    contraseña de mínimo 8 caracteres y campos obligatorios.
  - cerrarSesion(): descarte en el cliente + revocación en el servidor.
"""

import sqlite3
import threading
import uuid
from datetime import datetime, timedelta, timezone

import jwt

from .errores import ErrorAutenticacion, ErrorConflicto, ErrorPermiso, ErrorValidacion

ROL_ALUMNO = "alumno"
ROL_ADMIN = "administrador"
DOMINIO_CORREO = "@alumno.ipn.mx"
MENSAJE_BOLETA_INVALIDA = "Número de boleta invalido"  # texto exacto del Req I-2.9


class GestorAutenticacion:
    ALGORITMO = "HS256"

    def __init__(self, repositorio, clave_secreta, horas_expiracion=8):
        self.repo = repositorio
        self.clave_secreta = clave_secreta
        self.horas_expiracion = horas_expiracion
        self._revocados = set()          # jti de tokens cerrados (revocación en servidor)
        self._candado = threading.Lock()

    # ---------------------------------------------------------------
    # Inicio de sesión (Req I-1.2, F-1.3)
    # ---------------------------------------------------------------
    def iniciarSesion(self, rol, identificador, contrasena):
        identificador = str(identificador or "").strip()
        if not identificador or not contrasena:
            raise ErrorValidacion("Ingresa tu identificador (boleta o folio) y tu contraseña.")

        try:
            resultado = self.repo.autenticar_usuario(identificador, contrasena)
        except PermissionError:
            raise ErrorAutenticacion("Identificador o contraseña incorrectos.") from None
        except RuntimeError:
            raise ErrorAutenticacion("La cuenta no tiene un rol asignado.") from None

        rol_real = ROL_ALUMNO if resultado["rol"] == "alumno" else ROL_ADMIN
        # El login dual manda el rol según el campo usado (boleta -> alumno, folio -> admin).
        if rol and rol not in (ROL_ALUMNO, ROL_ADMIN):
            raise ErrorValidacion("Tipo de usuario inválido.")
        if rol and rol != rol_real:
            campo = "boleta" if rol_real == ROL_ALUMNO else "folio"
            raise ErrorAutenticacion(f"Esta cuenta debe iniciar sesión con su {campo}.")

        token = self.generarToken(identificador, rol_real)
        return {"token": token, "rol": rol_real}

    def generarToken(self, identificador, rol):
        ahora = datetime.now(timezone.utc)
        carga = {
            "sub": str(identificador),
            "rol": rol,
            "jti": uuid.uuid4().hex,
            "iat": ahora,
            "exp": ahora + timedelta(hours=self.horas_expiracion),
        }
        return jwt.encode(carga, self.clave_secreta, algorithm=self.ALGORITMO)

    # ---------------------------------------------------------------
    # Verificación en cada petición (firma, expiración y rol)
    # ---------------------------------------------------------------
    def verificarSesion(self, token, rol_requerido=None):
        if not token:
            raise ErrorAutenticacion("Debes iniciar sesión.")
        try:
            carga = jwt.decode(token, self.clave_secreta, algorithms=[self.ALGORITMO])
        except jwt.ExpiredSignatureError:
            raise ErrorAutenticacion("Tu sesión expiró. Inicia sesión de nuevo.") from None
        except jwt.InvalidTokenError:
            raise ErrorAutenticacion("Sesión inválida. Inicia sesión de nuevo.") from None

        with self._candado:
            if carga.get("jti") in self._revocados:
                raise ErrorAutenticacion("La sesión fue cerrada. Inicia sesión de nuevo.")

        if rol_requerido and carga.get("rol") != rol_requerido:
            raise ErrorPermiso("No tienes permiso para realizar esta acción.")

        entidad = self.obtenerEntidad(carga["rol"], carga["sub"])
        if entidad is None:
            raise ErrorAutenticacion("La cuenta ya no existe. Inicia sesión de nuevo.")
        return {"rol": carga["rol"], "identificador": carga["sub"], "jti": carga["jti"],
                "entidad": entidad}

    def obtenerEntidad(self, rol, identificador):
        if rol == ROL_ALUMNO:
            return self.repo.obtenerAlumnoPorBoleta(identificador)
        if rol == ROL_ADMIN:
            try:
                return self.repo.obtenerAdministradorPorFolio(int(identificador))
            except ValueError:
                return None
        return None

    # ---------------------------------------------------------------
    # Cierre de sesión (Req F-2.7, F-5.3)
    # ---------------------------------------------------------------
    def cerrarSesion(self, sesion):
        with self._candado:
            self._revocados.add(sesion["jti"])
        return sesion["entidad"].cerrarSesion()

    # ---------------------------------------------------------------
    # Registro de alumnos (Req F-2.0, F-2.1, F-2.2, F-2.3, F-2.6, I-2.9)
    # ---------------------------------------------------------------
    def validarRegistro(self, datos):
        campos = {
            "apellidoPaterno": "Apellido paterno",
            "apellidoMaterno": "Apellido materno",
            "nombres": "Nombre(s)",
            "boleta": "Número de boleta",
            "correo": "Correo electrónico",
            "contrasena": "Contraseña",
        }
        valores = {clave: str(datos.get(clave) or "").strip() for clave in campos}
        valores["contrasena"] = str(datos.get("contrasena") or "")

        faltantes = [nombre for clave, nombre in campos.items() if not valores[clave].strip()]
        if faltantes:  # Req F-2.3
            raise ErrorValidacion("Todos los campos son obligatorios. Falta: " + ", ".join(faltantes) + ".")

        if len(valores["boleta"]) != 10 or not valores["boleta"].isdigit():  # Req F-2.2
            raise ErrorValidacion("El número de boleta debe tener exactamente 10 dígitos.")
        if not valores["correo"].lower().endswith(DOMINIO_CORREO) or len(valores["correo"]) <= len(DOMINIO_CORREO):
            raise ErrorValidacion("El correo debe pertenecer al dominio @alumno.ipn.mx.")
        if len(valores["contrasena"]) < 8:
            raise ErrorValidacion("La contraseña debe tener mínimo 8 caracteres.")
        return valores

    def registrarAlumno(self, datos):
        valores = self.validarRegistro(datos)
        nombre_completo = " ".join([valores["nombres"], valores["apellidoPaterno"], valores["apellidoMaterno"]])
        try:
            alumno = self.repo.registrar_alumno(
                nombre_completo=nombre_completo,
                boleta=valores["boleta"],
                correo_electronico=valores["correo"],
                contrasena_plana=valores["contrasena"],
            )
        except ValueError as error:
            if "boleta" in str(error).lower():  # Req F-2.6: boleta duplicada
                raise ErrorConflicto(MENSAJE_BOLETA_INVALIDA) from None
            raise ErrorValidacion(str(error)) from None
        except sqlite3.IntegrityError:
            raise ErrorConflicto("Ese correo electrónico ya está registrado en otra cuenta.") from None
        return alumno
