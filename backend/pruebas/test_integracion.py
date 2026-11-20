"""
Pruebas de integración Capa 1 <-> Capa 2 <-> Capa 3 a través de la API REST.

  cd backend
  python -m unittest pruebas.test_integracion -v

Usan una base de datos temporal y un reloj simulado, así que no tocan la BD
real ni hay que esperar 30 minutos para probar los temporizadores.
"""

import io
import os
import shutil
import sys
import tempfile
import unittest
import warnings
from datetime import datetime, timedelta

DIR_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, DIR_BACKEND)

from app import crear_app  # noqa: E402

ADMIN = ("20200001", "admin12345")
ALUMNO = ("2026630148", "alumno12345")


class Reloj:
    def __init__(self, inicio):
        self.momento = inicio

    def __call__(self):
        return self.momento

    def avanzar(self, **kwargs):
        self.momento += timedelta(**kwargs)


class PruebasIntegracion(unittest.TestCase):
    def setUp(self):
        warnings.simplefilter("ignore", ResourceWarning)
        self.tmp = tempfile.mkdtemp()
        frontend = os.path.join(self.tmp, "frontend")
        shutil.copytree(os.path.join(DIR_BACKEND, "..", "frontend"), frontend)
        self.reloj = Reloj(datetime(2026, 11, 17, 10, 0, 0))
        self.app = crear_app(ruta_bd=os.path.join(self.tmp, "prueba.db"), carpeta_frontend=frontend,
                             clave_secreta="clave-de-prueba-de-32-bytes-o-mas-xyz", iniciar_motor=False, reloj=self.reloj)
        self.cliente = self.app.test_client()
        self.motor = self.app.extensions["lab_micros"]["motor"]

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ---------------- utilidades ----------------
    def login(self, identificador, contrasena, rol=None):
        rol = rol or ("alumno" if len(identificador) == 10 else "administrador")
        r = self.cliente.post("/api/auth/login", json={"rol": rol, "identificador": identificador,
                                                         "contrasena": contrasena})
        self.assertEqual(r.status_code, 200, r.get_json())
        return {"Authorization": "Bearer " + r.get_json()["token"]}

    def get(self, ruta, h):
        return self.cliente.get("/api" + ruta, headers=h)

    def post(self, ruta, h=None, **json):
        return self.cliente.post("/api" + ruta, headers=h or {}, json=json)

    def materiales(self, h):
        return {m["numeroSerie"]: m for m in self.get("/materiales", h).get_json()}

    def ids(self, h, *series):
        mats = self.materiales(h)
        return [mats[s]["id"] for s in series]

    def registrar(self, boleta="2026630999", correo="nuevo@alumno.ipn.mx", **extra):
        datos = {"apellidoPaterno": "Pérez", "apellidoMaterno": "Soto", "nombres": "Luis",
                 "boleta": boleta, "correo": correo, "contrasena": "clave1234"}
        datos.update(extra)
        return self.post("/alumnos", **datos)

    # ---------------- pruebas ----------------
    def test_01_frontend_servido(self):
        self.assertEqual(self.cliente.get("/").status_code, 200)
        self.assertEqual(self.cliente.get("/alumno/carrito.html").status_code, 200)
        self.assertEqual(self.cliente.get("/admin/administradores.html").status_code, 200)
        self.assertEqual(self.cliente.get("/js/api/apiClient.js").status_code, 200)
        self.assertEqual(self.cliente.get("/api/no-existe").status_code, 404)

    def test_02_login_dual_y_roles(self):
        self.login(*ADMIN)
        self.login(*ALUMNO)
        r = self.post("/auth/login", rol="administrador", identificador="20200001", contrasena="mala1234")
        self.assertEqual(r.status_code, 401)
        r = self.post("/auth/login", rol="alumno", identificador="20200001", contrasena="admin12345")
        self.assertEqual(r.status_code, 401)  # folio usado en el campo de boleta
        h = self.login(*ALUMNO)
        self.assertEqual(self.get("/admin/alumnos", h).status_code, 403)  # alumno en ruta de admin
        self.assertEqual(self.get("/alumnos/me", {}).status_code, 401)    # sin token

    def test_03_registro_y_validaciones(self):
        self.assertEqual(self.registrar().status_code, 201)
        r = self.registrar(correo="otro@alumno.ipn.mx")
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.get_json()["mensaje"], "Número de boleta invalido")       # Req I-2.9
        self.assertEqual(self.registrar(boleta="123", correo="x@alumno.ipn.mx").status_code, 400)
        self.assertEqual(self.registrar(boleta="2026630998", correo="x@gmail.com").status_code, 400)
        self.assertEqual(self.registrar(boleta="2026630997", correo="y@alumno.ipn.mx", contrasena="123").status_code, 400)
        self.assertEqual(self.registrar(boleta="2026630996", correo="z@alumno.ipn.mx", nombres="").status_code, 400)
        self.assertEqual(self.registrar(boleta="2026630995", correo="nuevo@alumno.ipn.mx").status_code, 409)
        self.login("2026630999", "clave1234")

    def test_04_perfil(self):
        h = self.login(*ALUMNO)
        p = self.get("/alumnos/me", h).get_json()
        self.assertEqual(p["estado"], "Activa")
        self.assertFalse(p["tienePedidoActivo"])
        r = self.cliente.put("/api/alumnos/me", headers=h, json={"nombreCompleto": "Daniela H.", "correo": "dh@alumno.ipn.mx"})
        self.assertEqual(r.get_json()["nombreCompleto"], "Daniela H.")
        r = self.cliente.put("/api/alumnos/me", headers=h, json={"nombreCompleto": "D", "correo": "dh@gmail.com"})
        self.assertEqual(r.status_code, 400)

    def test_05_horarios(self):
        h = self.login(*ALUMNO)
        self.assertEqual(len(self.get("/horarios", h).get_json()), 2)      # 10:00 -> +1:30 y +3 h
        self.reloj.momento = datetime(2026, 11, 17, 20, 30)
        opciones = self.get("/horarios", h).get_json()
        self.assertEqual([o["id"] for o in opciones], ["h1"])                # Req F-4.6
        r = self.post("/pedidos", h, materiales=self.ids(h, "PB830-2025-000101"), horarioId="h2")
        self.assertEqual(r.status_code, 400)
        self.reloj.momento = datetime(2026, 11, 17, 22, 0)
        self.assertEqual(self.get("/horarios", h).get_json(), [])           # Req F-4.5
        r = self.post("/pedidos", h, materiales=self.ids(h, "PB830-2025-000101"), horarioId="h1")
        self.assertEqual(r.status_code, 400)

    def test_06_limites_y_pedido_activo(self):
        ha = self.login(*ADMIN)
        h = self.login(*ALUMNO)
        mats = list(self.materiales(h).values())
        nueve = [m["id"] for m in mats[:9]]
        self.assertEqual(self.post("/pedidos", h, materiales=nueve, horarioId="h1").status_code, 400)
        cinco_iguales = [m["id"] for m in mats if m["nombre"] == "Multímetro digital"]
        self.assertEqual(len(cinco_iguales), 5)
        r = self.post("/pedidos", h, materiales=cinco_iguales, horarioId="h1")
        self.assertEqual(r.status_code, 400)
        self.assertIn("4 piezas iguales", r.get_json()["mensaje"])
        self.assertTrue(all(m["disponible"] for m in self.materiales(h).values()))  # nada quedó reservado

        r = self.post("/pedidos", h, materiales=self.ids(h, "FL117-2024-008745", "DS1054Z-2023-000219"), horarioId="h2")
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.get_json()["idPedido"], "PR-0001")
        self.assertFalse(self.materiales(h)["FL117-2024-008745"]["disponible"])   # Req F-4.1
        self.assertTrue(self.get("/alumnos/me", h).get_json()["tienePedidoActivo"])
        r = self.post("/pedidos", h, materiales=self.ids(h, "PB830-2025-000101"), horarioId="h1")
        self.assertEqual(r.status_code, 409)                                       # Req F-2.5

        # Otro alumno no puede pedir una pieza reservada
        self.registrar()
        h2 = self.login("2026630999", "clave1234")
        r = self.post("/pedidos", h2, materiales=self.ids(h2, "FL117-2024-008745"), horarioId="h1")
        self.assertEqual(r.status_code, 409)

        sol = self.get("/admin/pedidos", ha).get_json()
        self.assertEqual(sol[0]["folioAdminAcepta"], "pendiente")                  # Req F-4.3

    def test_07_cancelacion_por_alumno(self):
        ha = self.login(*ADMIN)
        h = self.login(*ALUMNO)
        self.post("/pedidos", h, materiales=self.ids(h, "PB830-2025-000101"), horarioId="h1")
        actual = self.get("/pedidos/actual", h).get_json()
        self.assertTrue(actual["puedeCancelar"])
        self.assertEqual(self.post("/pedidos/PR-0001/cancelar", h).status_code, 200)   # Req F-2.9
        self.assertIsNone(self.get("/pedidos/actual", h).get_json())
        self.assertTrue(self.materiales(h)["PB830-2025-000101"]["disponible"])

        self.post("/pedidos", h, materiales=self.ids(h, "PB830-2025-000101"), horarioId="h1")
        self.post("/admin/pedidos/PR-0002/aceptar", ha)
        self.assertEqual(self.post("/pedidos/PR-0002/cancelar", h).status_code, 409)

    def test_08_tolerancia_de_recogida(self):
        h = self.login(*ALUMNO)
        self.post("/pedidos", h, materiales=self.ids(h, "PB830-2025-000101"), horarioId="h1")
        self.reloj.avanzar(minutes=29)
        self.motor.ejecutarCiclo()
        self.assertIsNotNone(self.get("/pedidos/actual", h).get_json())
        self.reloj.avanzar(minutes=2)
        self.motor.ejecutarCiclo()                                                  # Req F-4.4
        self.assertIsNone(self.get("/pedidos/actual", h).get_json())
        self.assertTrue(self.materiales(h)["PB830-2025-000101"]["disponible"])

    def test_09_vencimiento_suspension_y_devolucion(self):
        ha = self.login(*ADMIN)
        h = self.login(*ALUMNO)
        self.post("/pedidos", h, materiales=self.ids(h, "FL117-2024-008745", "DP832-2022-004410"), horarioId="h1")
        self.assertEqual(self.post("/admin/pedidos/PR-0001/aceptar", ha).status_code, 200)
        self.assertEqual(self.post("/admin/pedidos/PR-0001/aceptar", ha).status_code, 409)
        self.assertEqual(self.get("/pedidos/actual", h).get_json()["estado"], "En préstamo")

        self.reloj.avanzar(hours=1, minutes=31)
        self.motor.ejecutarCiclo()                                                  # Req F-2.12
        perfil = self.get("/alumnos/me", h).get_json()
        self.assertEqual(perfil["estado"], "Suspendida")
        self.assertIn("PR-0001", perfil["motivoSancion"])
        piezas = self.get("/admin/devoluciones", ha).get_json()
        self.assertEqual({p["estado"] for p in piezas}, {"Vencido"})

        r = self.post("/admin/devoluciones/%d/devolver" % piezas[0]["idDetalle"], ha)
        self.assertFalse(r.get_json()["pedidoCompletado"])
        self.assertEqual(self.get("/alumnos/me", h).get_json()["estado"], "Suspendida")
        r = self.post("/admin/devoluciones/%d/devolver" % piezas[1]["idDetalle"], ha)
        self.assertTrue(r.get_json()["pedidoCompletado"])                           # Req F-4.2
        self.assertEqual(self.post("/admin/devoluciones/%d/devolver" % piezas[1]["idDetalle"], ha).status_code, 409)
        self.assertEqual(self.get("/alumnos/me", h).get_json()["estado"], "Activa")  # Req F-2.13
        self.assertTrue(self.materiales(h)["DP832-2022-004410"]["disponible"])
        historial = self.get("/pedidos/historial", h).get_json()
        self.assertEqual(len(historial), 2)
        self.assertTrue(all(x["fechaDevolucion"] for x in historial))

    def test_10_rechazo(self):
        ha = self.login(*ADMIN)
        h = self.login(*ALUMNO)
        self.post("/pedidos", h, materiales=self.ids(h, "ARD-UNO-2024-000501"), horarioId="h1")
        self.assertEqual(self.post("/admin/pedidos/PR-0001/rechazar", ha).status_code, 200)
        self.assertTrue(self.materiales(h)["ARD-UNO-2024-000501"]["disponible"])
        self.assertEqual(self.get("/admin/pedidos", ha).get_json()[0]["estado"], "Rechazado")
        self.assertEqual(self.get("/pedidos/historial", h).get_json(), [])

    def test_11_bloqueo_tiene_prioridad(self):
        ha = self.login(*ADMIN)
        h = self.login(*ALUMNO)
        self.assertEqual(self.post("/admin/alumnos/2026630148/bloquear", ha, motivo=" ").status_code, 400)
        self.post("/pedidos", h, materiales=self.ids(h, "PB830-2025-000102"), horarioId="h1")
        self.post("/admin/pedidos/PR-0001/aceptar", ha)
        r = self.post("/admin/alumnos/2026630148/bloquear", ha, motivo="Sonda dañada")
        self.assertEqual(r.get_json()["estado"], "Bloqueada")
        self.reloj.avanzar(hours=2)
        self.motor.ejecutarCiclo()
        self.assertEqual(self.get("/alumnos/me", h).get_json()["estado"], "Bloqueada")   # no pasa a suspendido
        pieza = self.get("/admin/devoluciones", ha).get_json()[0]
        self.post("/admin/devoluciones/%d/devolver" % pieza["idDetalle"], ha)
        perfil = self.get("/alumnos/me", h).get_json()
        self.assertEqual(perfil["estado"], "Bloqueada")                                  # sigue bloqueado
        self.assertEqual(perfil["motivoSancion"], "Sonda dañada")
        r = self.post("/pedidos", h, materiales=self.ids(h, "PB830-2025-000103"), horarioId="h1")
        self.assertEqual(r.status_code, 403)
        self.post("/admin/alumnos/2026630148/quitar-sanciones", ha)
        self.assertEqual(self.get("/alumnos/me", h).get_json()["estado"], "Activa")

    def test_12_gestor_de_administradores(self):
        ha = self.login(*ADMIN)
        self.assertEqual(self.get("/admin/me", ha).get_json(), {"nombreCompleto": "Ana López Ortega", "folio": 20200001})
        r = self.post("/admin/administradores", ha, nombreCompleto="Juan Pérez", contrasena="staff12345")
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.get_json()["folio"], 20200002)
        self.assertEqual(self.post("/admin/administradores", ha, nombreCompleto="X", contrasena="1").status_code, 400)
        self.login("20200002", "staff12345")
        self.assertEqual(len(self.get("/admin/administradores", ha).get_json()), 2)

    def test_13_inventario_alta_y_edicion(self):
        ha = self.login(*ADMIN)
        datos = {"nombre": "Fuente conmutada", "numeroSerie": "FC-001", "descripcion": "12 V 5 A",
                 "precioReposicion": "350", "fotografia": (io.BytesIO(b"\xff\xd8\xff fake"), "foto.jpg")}
        r = self.cliente.post("/api/admin/materiales", headers=ha, data=datos, content_type="multipart/form-data")
        self.assertEqual(r.status_code, 201, r.get_json())
        nuevo = r.get_json()
        self.assertTrue(nuevo["imagen"].startswith("/img/materiales/"))
        self.assertEqual(self.cliente.get(nuevo["imagen"]).status_code, 200)
        datos["fotografia"] = (io.BytesIO(b"x"), "foto.jpg")
        r = self.cliente.post("/api/admin/materiales", headers=ha, data=datos, content_type="multipart/form-data")
        self.assertEqual(r.status_code, 409)
        r = self.cliente.put("/api/admin/materiales/%d" % nuevo["id"], headers=ha,
                             data={"nombre": "Fuente conmutada", "descripcion": "12 V 10 A", "precioReposicion": "420"},
                             content_type="multipart/form-data")
        self.assertEqual(r.status_code, 200, r.get_json())
        self.assertEqual(r.get_json()["descripcion"], "12 V 10 A")
        self.assertEqual(r.get_json()["imagen"], nuevo["imagen"])  # conserva la foto

    def test_14_cierre_de_sesion(self):
        h = self.login(*ALUMNO)
        self.assertEqual(self.post("/auth/logout", h).status_code, 200)
        self.assertEqual(self.get("/alumnos/me", h).status_code, 401)

    def test_15_conciliacion(self):
        h = self.login(*ALUMNO)
        repo = self.app.extensions["lab_micros"]["repo"]
        material = repo.obtenerMaterialPorId(self.ids(h, "PB830-2025-000103")[0])
        material.reservar(self.app.extensions["lab_micros"]["base_datos"])  # reserva "huérfana"
        self.assertFalse(self.materiales(h)["PB830-2025-000103"]["disponible"])
        self.motor.ejecutarCiclo()
        self.assertTrue(self.materiales(h)["PB830-2025-000103"]["disponible"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
