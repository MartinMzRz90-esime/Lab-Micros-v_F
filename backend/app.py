"""
SISTEMA DE GESTIÓN PARA PRÉSTAMO DE EQUIPO DE LABORATORIO DE MICROPROCESADORES
Capa 2: Lógica de negocio - API REST (controladores) en Python / Flask

Arquitectura por capas (Diseño v3.1):
  Capa 1 (Presentación, JavaScript)  --HTTP/JSON-->  Capa 2 (esta API + gestores)
  Capa 2  -->  Capa 3 (Repositorio ORM + SQLite)

Ejecución:
  python app.py                 -> http://localhost:8000
  python app.py --red           -> también accesible desde otros dispositivos de la red (celular)

El mismo servidor entrega el frontend (carpeta ../frontend) y la API (/api/...).
"""

import argparse
import logging
import os
import secrets
import socket
import sys
from functools import wraps

from flask import Flask, g, jsonify, request, send_from_directory
from werkzeug.exceptions import HTTPException

DIR_BACKEND = os.path.dirname(os.path.abspath(__file__))
if DIR_BACKEND not in sys.path:
    sys.path.insert(0, DIR_BACKEND)

from datos.capa_datos_sqlite import BaseDatosSQLite, RepositorioORM  # noqa: E402  (Capa 3)
from logica.errores import ErrorNegocio, ErrorValidacion  # noqa: E402
from logica.gestor_administradores import GestorAdministradores  # noqa: E402
from logica.gestor_autenticacion import ROL_ADMIN, ROL_ALUMNO, GestorAutenticacion  # noqa: E402
from logica.gestor_eventos import GestorEventos  # noqa: E402
from logica.gestor_inventario import GestorInventario  # noqa: E402
from logica.gestor_prestamos import GestorPrestamos  # noqa: E402
from logica.gestor_usuarios import GestorUsuarios  # noqa: E402
from logica.motor_reglas import MotorReglas  # noqa: E402
from semilla import RUTA_BD_PREDETERMINADA, sembrar  # noqa: E402

CARPETA_FRONTEND = os.path.abspath(os.path.join(DIR_BACKEND, "..", "frontend"))
SUBCARPETA_FOTOS = "img/materiales"

registro = logging.getLogger("lab_micros")


def crear_app(ruta_bd=RUTA_BD_PREDETERMINADA, carpeta_frontend=CARPETA_FRONTEND,
              clave_secreta=None, iniciar_motor=True, reloj=None, datos_ejemplo=True):
    app = Flask(__name__, static_folder=None)
    app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024
    app.json.ensure_ascii = False
    app.json.sort_keys = False

    # ------------------------------------------------------------------
    # Ensamblado de componentes (Capa 3 -> Capa 2)
    # ------------------------------------------------------------------
    base_datos = BaseDatosSQLite(ruta_bd)
    sembrar(base_datos, datos_ejemplo=datos_ejemplo)
    repo = RepositorioORM(base_datos)

    bus = GestorEventos()
    motor = MotorReglas(repo, bus, reloj=reloj)
    auth = GestorAutenticacion(repo, clave_secreta or os.environ.get("LAB_CLAVE_SECRETA") or secrets.token_hex(32))
    usuarios = GestorUsuarios(repo, base_datos, bus)
    inventario = GestorInventario(repo, base_datos, bus,
                                  carpeta_fotos=os.path.join(carpeta_frontend, *SUBCARPETA_FOTOS.split("/")),
                                  prefijo_url_fotos=SUBCARPETA_FOTOS)
    prestamos = GestorPrestamos(repo, base_datos, bus, usuarios, motor)
    administradores = GestorAdministradores(repo, base_datos)

    app.extensions["lab_micros"] = {
        "base_datos": base_datos, "repo": repo, "bus": bus, "motor": motor, "auth": auth,
        "usuarios": usuarios, "inventario": inventario, "prestamos": prestamos,
        "administradores": administradores,
    }

    # ------------------------------------------------------------------
    # Utilidades de los controladores
    # ------------------------------------------------------------------
    def requiere_sesion(rol=None):
        """Llamada síncrona obligatoria a GestorAutenticacion.verificarSesion() en cada operación."""
        def decorador(funcion):
            @wraps(funcion)
            def envoltura(*args, **kwargs):
                cabecera = request.headers.get("Authorization", "")
                token = cabecera[7:].strip() if cabecera.lower().startswith("bearer ") else ""
                g.sesion = auth.verificarSesion(token, rol_requerido=rol)
                g.usuario = g.sesion["entidad"]
                return funcion(*args, **kwargs)
            return envoltura
        return decorador

    def cuerpo_json():
        datos = request.get_json(silent=True)
        if datos is None:
            datos = {}
        if not isinstance(datos, dict):
            raise ErrorValidacion("El cuerpo de la petición debe ser un objeto JSON.")
        return datos

    def datos_formulario():
        """Acepta multipart/form-data (con foto) o JSON."""
        if request.form or request.files:
            return request.form, request.files.get("fotografia")
        return cuerpo_json(), None

    @app.errorhandler(ErrorNegocio)
    def manejar_error_negocio(error):
        return jsonify({"mensaje": error.mensaje}), error.codigo_http

    @app.errorhandler(404)
    def manejar_404(_error):
        if request.path.startswith("/api/"):
            return jsonify({"mensaje": "Ruta de la API no encontrada."}), 404
        return "Página no encontrada", 404

    @app.errorhandler(413)
    def manejar_413(_error):
        return jsonify({"mensaje": "El archivo es demasiado grande (máximo 8 MB)."}), 413

    @app.errorhandler(Exception)
    def manejar_error_interno(error):
        if isinstance(error, HTTPException):  # 405, 400, etc. propios de Flask/Werkzeug
            if request.path.startswith("/api/"):
                return jsonify({"mensaje": error.description}), error.code
            return error.get_response()
        registro.exception("Error no controlado en %s %s", request.method, request.path)
        return jsonify({"mensaje": "Ocurrió un error interno en el servidor."}), 500

    # ------------------------------------------------------------------
    # API: Autenticación  (GestorAutenticacion)
    # ------------------------------------------------------------------
    @app.post("/api/auth/login")
    def login():
        datos = cuerpo_json()
        return jsonify(auth.iniciarSesion(datos.get("rol"), datos.get("identificador"), datos.get("contrasena")))

    @app.post("/api/auth/logout")
    @requiere_sesion()
    def logout():
        return jsonify(auth.cerrarSesion(g.sesion))

    @app.post("/api/alumnos")
    def registrar_alumno():
        alumno = auth.registrarAlumno(cuerpo_json())
        return jsonify({"mensaje": "Cuenta creada con éxito.", "boleta": alumno.boleta}), 201

    # ------------------------------------------------------------------
    # API: Portal del alumno
    # ------------------------------------------------------------------
    @app.get("/api/alumnos/me")
    @requiere_sesion(ROL_ALUMNO)
    def perfil_alumno():
        return jsonify(usuarios.consultarPerfil(g.usuario.boleta))

    @app.put("/api/alumnos/me")
    @requiere_sesion(ROL_ALUMNO)
    def editar_perfil_alumno():
        datos = cuerpo_json()
        return jsonify(usuarios.editarPerfil(g.usuario.boleta, datos.get("nombreCompleto"), datos.get("correo")))

    @app.get("/api/alumnos/me/motivo")
    @requiere_sesion(ROL_ALUMNO)
    def motivo_sancion():
        return jsonify(usuarios.consultarMotivoSuspension(g.usuario.boleta))

    @app.get("/api/materiales")
    @requiere_sesion(ROL_ALUMNO)
    def catalogo():
        termino = request.args.get("q", "")
        return jsonify(inventario.buscarMaterial(termino) if termino else inventario.listarMateriales())

    @app.get("/api/horarios")
    @requiere_sesion(ROL_ALUMNO)
    def horarios():
        return jsonify(motor.opcionesHorario())

    @app.post("/api/pedidos")
    @requiere_sesion(ROL_ALUMNO)
    def crear_pedido():
        datos = cuerpo_json()
        return jsonify(prestamos.crearPedido(g.usuario.boleta, datos.get("materiales"), datos.get("horarioId"))), 201

    @app.get("/api/pedidos/actual")
    @requiere_sesion(ROL_ALUMNO)
    def prestamo_actual():
        return jsonify(prestamos.consultarPrestamoActivo(g.usuario.boleta))

    @app.get("/api/pedidos/historial")
    @requiere_sesion(ROL_ALUMNO)
    def historial():
        return jsonify(prestamos.consultarHistorial(g.usuario.boleta))

    @app.post("/api/pedidos/<id_pedido>/cancelar")
    @requiere_sesion(ROL_ALUMNO)
    def cancelar_pedido(id_pedido):
        return jsonify(prestamos.cancelarPedido(g.usuario.boleta, id_pedido))

    # ------------------------------------------------------------------
    # API: Portal del administrador
    # ------------------------------------------------------------------
    @app.get("/api/admin/me")
    @requiere_sesion(ROL_ADMIN)
    def admin_actual():
        return jsonify(administradores.consultarCuentaActiva(g.usuario))

    @app.get("/api/admin/administradores")
    @requiere_sesion(ROL_ADMIN)
    def listar_administradores():
        return jsonify(administradores.listarAdministradores())

    @app.post("/api/admin/administradores")
    @requiere_sesion(ROL_ADMIN)
    def crear_administrador():
        datos = cuerpo_json()
        return jsonify(administradores.gestionarAlta(g.usuario, datos.get("nombreCompleto"), datos.get("contrasena"))), 201

    @app.get("/api/admin/materiales")
    @requiere_sesion(ROL_ADMIN)
    def listar_inventario():
        return jsonify(inventario.listarMateriales())

    @app.post("/api/admin/materiales")
    @requiere_sesion(ROL_ADMIN)
    def registrar_material():
        datos, foto = datos_formulario()
        return jsonify(inventario.registrarMaterial(datos.get("nombre"), datos.get("numeroSerie"),
                                                    datos.get("descripcion"), datos.get("precioReposicion"),
                                                    foto)), 201

    @app.put("/api/admin/materiales/<int:id_material>")
    @requiere_sesion(ROL_ADMIN)
    def editar_material(id_material):
        datos, foto = datos_formulario()
        return jsonify(inventario.editarMaterial(id_material, datos.get("nombre"), datos.get("descripcion"),
                                                 datos.get("precioReposicion"), foto))

    @app.get("/api/admin/pedidos")
    @requiere_sesion(ROL_ADMIN)
    def listar_solicitudes():
        return jsonify(prestamos.listarSolicitudes())

    @app.post("/api/admin/pedidos/<id_pedido>/aceptar")
    @requiere_sesion(ROL_ADMIN)
    def aceptar_pedido(id_pedido):
        return jsonify(prestamos.aceptarPedido(g.usuario, id_pedido))

    @app.post("/api/admin/pedidos/<id_pedido>/rechazar")
    @requiere_sesion(ROL_ADMIN)
    def rechazar_pedido(id_pedido):
        return jsonify(prestamos.rechazarPedido(g.usuario, id_pedido))

    @app.get("/api/admin/alumnos")
    @requiere_sesion(ROL_ADMIN)
    def listar_alumnos():
        return jsonify(usuarios.listarAlumnos(request.args.get("q", "")))

    @app.post("/api/admin/alumnos/<boleta>/bloquear")
    @requiere_sesion(ROL_ADMIN)
    def bloquear_alumno(boleta):
        return jsonify(usuarios.bloquearAlumno(g.usuario, boleta, cuerpo_json().get("motivo")))

    @app.post("/api/admin/alumnos/<boleta>/quitar-sanciones")
    @requiere_sesion(ROL_ADMIN)
    def quitar_sanciones(boleta):
        return jsonify(usuarios.quitarSanciones(boleta))

    @app.get("/api/admin/devoluciones")
    @requiere_sesion(ROL_ADMIN)
    def listar_devoluciones():
        return jsonify(prestamos.listarDevoluciones())

    @app.post("/api/admin/devoluciones/<id_detalle>/devolver")
    @requiere_sesion(ROL_ADMIN)
    def marcar_devolucion(id_detalle):
        return jsonify(prestamos.marcarDevolucion(g.usuario, id_detalle))

    # ------------------------------------------------------------------
    # Capa 1: archivos del frontend (HTML, CSS, JS, imágenes)
    # ------------------------------------------------------------------
    @app.get("/")
    def inicio():
        return send_from_directory(carpeta_frontend, "index.html")

    @app.get("/<path:ruta>")
    def archivos_frontend(ruta):
        if ruta.startswith("api/"):
            return jsonify({"mensaje": "Ruta de la API no encontrada."}), 404
        return send_from_directory(carpeta_frontend, ruta)

    if iniciar_motor:
        motor.iniciar(intervalo_segundos=60)
    return app


def _ip_local():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except OSError:
        return None


def main():
    parser = argparse.ArgumentParser(description="Servidor del sistema de préstamo del laboratorio.")
    parser.add_argument("--puerto", type=int, default=8000)
    parser.add_argument("--red", action="store_true",
                        help="Permite entrar desde otros dispositivos de la misma red (p. ej. un celular).")
    parser.add_argument("--simular-hora", metavar="HH:MM",
                        help="Solo para pruebas: el reloj del servidor arranca en esa hora de hoy y avanza "
                             "normalmente (útil para probar fuera del horario de 07:00 a 21:00 h).")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")
    reloj = None
    if args.simular_hora:
        from datetime import datetime
        try:
            hora, minuto = (int(x) for x in args.simular_hora.split(":"))
            inicio_simulado = datetime.now().replace(hour=hora, minute=minuto, second=0, microsecond=0)
        except ValueError:
            parser.error("--simular-hora debe tener el formato HH:MM, por ejemplo 10:00")
        inicio_real = datetime.now()

        def reloj():
            return inicio_simulado + (datetime.now() - inicio_real)

        print(f"  [PRUEBAS] Reloj simulado: el servidor cree que son las {args.simular_hora}")
    app = crear_app(reloj=reloj)
    host = "0.0.0.0" if args.red else "127.0.0.1"

    print("\n  Sistema de préstamo - Laboratorio de Microprocesadores")
    print(f"  Abre en tu navegador:  http://localhost:{args.puerto}")
    if args.red and _ip_local():
        print(f"  Desde tu celular:      http://{_ip_local()}:{args.puerto}")
    print("  Administrador inicial: folio 20200001 / admin12345")
    print("  Alumno de prueba:      boleta 2026630148 / alumno12345")
    print("  Detener el servidor:   Ctrl + C\n")
    app.run(host=host, port=args.puerto, threaded=True, use_reloader=False)


if __name__ == "__main__":
    main()
