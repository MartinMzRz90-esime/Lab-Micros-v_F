"""
Datos iniciales del sistema.

  python semilla.py              -> carga los datos solo si la BD está vacía
  python semilla.py --reiniciar  -> borra la BD y la vuelve a crear con los datos de ejemplo

Crea:
  - El administrador inicial (necesario porque el Req F-5.6 exige que un
    administrador con sesión activa dé de alta a los demás).
  - Materiales de ejemplo para el laboratorio.
  - Un alumno de prueba.
"""

import argparse
import os
import sys

DIR_BACKEND = os.path.dirname(os.path.abspath(__file__))
if DIR_BACKEND not in sys.path:
    sys.path.insert(0, DIR_BACKEND)

from datos.capa_datos_sqlite import (  # noqa: E402
    BaseDatosSQLite, Material, RepositorioORM, hashear_contrasena,
)

RUTA_BD_PREDETERMINADA = os.path.join(DIR_BACKEND, "datos", "laboratorio_microprocesadores.db")

ADMIN_INICIAL = {"folio": 20200001, "nombre": "Ana López Ortega", "contrasena": "admin12345"}
ALUMNO_PRUEBA = {"nombre": "Daniela Hernández López", "boleta": "2026630148",
                 "correo": "daniela.hl@alumno.ipn.mx", "contrasena": "alumno12345"}

# (nombre, descripción/modelo, número de serie, precio, fotografía)
MATERIALES = [
    ("Multímetro digital", "Fluke 117", "FL117-2024-008745", 6500, "img/multimetro.jpg"),
    ("Multímetro digital", "Fluke 117", "FL117-2024-008746", 6500, "img/multimetro.jpg"),
    ("Multímetro digital", "Fluke 117", "FL117-2024-008747", 6500, "img/multimetro.jpg"),
    ("Multímetro digital", "Fluke 117", "FL117-2024-008748", 6500, "img/multimetro.jpg"),
    ("Multímetro digital", "Fluke 117", "FL117-2024-008749", 6500, "img/multimetro.jpg"),
    ("Osciloscopio digital", "Rigol DS1054Z", "DS1054Z-2023-000219", 7800, None),
    ("Osciloscopio digital", "Rigol DS1054Z", "DS1054Z-2023-000220", 7800, None),
    ("Fuente de poder DC", "Rigol DP832", "DP832-2022-004410", 12500, None),
    ("Generador de funciones", "Rigol DG1022Z", "DG1022Z-2023-001873", 5900, None),
    ("Tarjeta de desarrollo", "STM32 Nucleo-F103RB", "NUC-F103-2025-000312", 450, None),
    ("Tarjeta de desarrollo", "STM32 Nucleo-F103RB", "NUC-F103-2025-000313", 450, None),
    ("Protoboard", "830 puntos", "PB830-2025-000101", 120, None),
    ("Protoboard", "830 puntos", "PB830-2025-000102", 120, None),
    ("Protoboard", "830 puntos", "PB830-2025-000103", 120, None),
    ("Arduino UNO", "Rev3 ATmega328P", "ARD-UNO-2024-000501", 550, None),
    ("Arduino UNO", "Rev3 ATmega328P", "ARD-UNO-2024-000502", 550, None),
]


def crear_admin_inicial(base_datos):
    conexion = base_datos.conectar()
    try:
        cursor = conexion.execute(
            "INSERT INTO usuarios (nombre_completo, contrasena, identificador) VALUES (?, ?, ?)",
            (ADMIN_INICIAL["nombre"], hashear_contrasena(ADMIN_INICIAL["contrasena"]), str(ADMIN_INICIAL["folio"])),
        )
        conexion.execute("INSERT INTO administradores (folio, id_usuario) VALUES (?, ?)",
                         (ADMIN_INICIAL["folio"], cursor.lastrowid))
        conexion.commit()
    finally:
        conexion.close()


def sembrar(base_datos, datos_ejemplo=True):
    """Crea el admin inicial si no hay administradores y, si se pide, los datos de ejemplo
    (solo cuando la tabla correspondiente está vacía). Devuelve lo que se creó."""
    repo = RepositorioORM(base_datos)
    creado = []
    if repo.contarAdministradores() == 0:
        crear_admin_inicial(base_datos)
        creado.append("administrador inicial")

    if datos_ejemplo:
        if not repo.listarMateriales():
            for nombre, descripcion, serie, precio, foto in MATERIALES:
                Material(None, nombre, descripcion, True, serie, precio, foto).registrarMaterial(base_datos)
            creado.append(f"{len(MATERIALES)} materiales")
        if not repo.buscar_alumnos_directorio(""):
            repo.registrar_alumno(ALUMNO_PRUEBA["nombre"], ALUMNO_PRUEBA["boleta"],
                                  ALUMNO_PRUEBA["correo"], ALUMNO_PRUEBA["contrasena"])
            creado.append("alumno de prueba")
    return creado


def main():
    parser = argparse.ArgumentParser(description="Carga los datos iniciales del sistema.")
    parser.add_argument("--reiniciar", action="store_true", help="Borra la base de datos y la vuelve a crear.")
    parser.add_argument("--bd", default=RUTA_BD_PREDETERMINADA, help="Ruta del archivo SQLite.")
    args = parser.parse_args()

    if args.reiniciar and os.path.exists(args.bd):
        os.remove(args.bd)
        print(f"Base de datos eliminada: {args.bd}")

    creado = sembrar(BaseDatosSQLite(args.bd))
    print("Datos creados: " + (", ".join(creado) if creado else "ninguno (la BD ya tenía datos)"))
    print(f"Administrador: folio {ADMIN_INICIAL['folio']} / contraseña {ADMIN_INICIAL['contrasena']}")
    print(f"Alumno:        boleta {ALUMNO_PRUEBA['boleta']} / contraseña {ALUMNO_PRUEBA['contrasena']}")


if __name__ == "__main__":
    main()
