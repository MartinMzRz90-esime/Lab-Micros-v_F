"""
Capa 2 - Lógica de negocio
Adaptadores: traducen los datos de la capa 3 (nombres de columnas del modelo
de datos) al formato que espera la capa 1 (camelCase y etiquetas legibles),
y viceversa. Así el frontend no necesita conocer el esquema SQLite.
"""

import re
from datetime import datetime

from .errores import ErrorValidacion

ESTADO_ALUMNO = {
    "activo": "Activa",
    "suspendido": "Suspendida",
    "bloqueado": "Bloqueada",
}

# Estado del pedido tal como lo ve el administrador en "Sección de préstamos"
ESTADO_SOLICITUD = {
    "pendiente": "Pendiente",
    "aceptado": "Aceptado",
    "vencido": "Aceptado",
    "finalizado": "Aceptado",
    "rechazado": "Rechazado",
    "cancelado": "Cancelado",
}

# Estado del pedido tal como lo ve el alumno en "Mis préstamos"
ESTADO_PRESTAMO_ALUMNO = {
    "pendiente": "Pendiente de recoger",
    "aceptado": "En préstamo",
    "vencido": "Vencido",
}

IMAGEN_SIN_FOTO = "/img/sin-foto.svg"


def id_pedido_texto(numero_pedido):
    """1 -> 'PR-0001' (formato usado en los prototipos)."""
    return f"PR-{int(numero_pedido):04d}"


def id_pedido_numero(texto):
    """'PR-0247' o '247' -> 247."""
    coincidencia = re.fullmatch(r"\s*(?:PR-)?0*(\d+)\s*", str(texto), flags=re.IGNORECASE)
    if not coincidencia:
        raise ErrorValidacion("Identificador de pedido inválido.")
    return int(coincidencia.group(1))


def entero(valor, nombre_campo):
    try:
        return int(str(valor).strip())
    except (TypeError, ValueError):
        raise ErrorValidacion(f"{nombre_campo} inválido.") from None


def url_imagen(ruta):
    if not ruta:
        return IMAGEN_SIN_FOTO
    ruta = str(ruta)
    if ruta.startswith(("http://", "https://", "/")):
        return ruta
    return "/" + ruta


def fecha(iso):
    return datetime.fromisoformat(iso)


def hora_corta(iso):
    return datetime.fromisoformat(iso).strftime("%H:%M")


def material_a_dto(material):
    return {
        "id": material.identificador_material,
        "nombre": material.nombre_componente,
        "modelo": material.descripcion_breve or "",
        "descripcion": material.descripcion_breve or "",
        "numeroSerie": material.numero_serie,
        "precioReposicion": material.precio_reposicion,
        "imagen": url_imagen(material.fotografia_componente_fisico),
        "fotografia": material.fotografia_componente_fisico,
        "disponible": bool(material.disponible),
        "estado": material.estado,
    }


def alumno_a_dto(alumno, tiene_pedido_activo=False):
    return {
        "nombreCompleto": alumno.nombre_completo,
        "boleta": alumno.boleta,
        "correo": alumno.correo_electronico,
        "estado": ESTADO_ALUMNO.get(alumno.estado, alumno.estado),
        "motivoSancion": alumno.motivo_sancion,
        "tienePedidoActivo": bool(tiene_pedido_activo),
    }


def fila_directorio_a_dto(fila):
    return {
        "nombre": fila["nombre_completo"],
        "boleta": fila["boleta"],
        "correo": fila["correo_electronico"],
        "estado": ESTADO_ALUMNO.get(fila["estado"], fila["estado"]),
        "motivoSancion": fila["motivo_sancion"],
    }
