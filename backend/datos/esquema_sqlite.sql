-- Base de datos para el sistema de prestamo de laboratorio de microprocesadores

PRAGMA foreign_keys = ON;

-- 1. Tabla de usuarios (tabla base para alumnos y administradores)
CREATE TABLE IF NOT EXISTS usuarios (
    id_usuario INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre_completo TEXT NOT NULL,
    contrasena TEXT NOT NULL,
    identificador TEXT NOT NULL UNIQUE
);

-- 2. Tabla de alumnos
-- El estado puede ser: activo, suspendido o bloqueado
CREATE TABLE IF NOT EXISTS alumnos (
    boleta TEXT PRIMARY KEY,
    id_usuario INTEGER NOT NULL UNIQUE,
    correo_electronico TEXT NOT NULL UNIQUE,
    estado TEXT NOT NULL DEFAULT 'activo',
    motivo_sancion TEXT,
    FOREIGN KEY (id_usuario) REFERENCES usuarios(id_usuario)
);

-- 3. Tabla de administradores
CREATE TABLE IF NOT EXISTS administradores (
    folio INTEGER PRIMARY KEY AUTOINCREMENT,
    id_usuario INTEGER NOT NULL UNIQUE,
    FOREIGN KEY (id_usuario) REFERENCES usuarios(id_usuario)
);

-- 4. Tabla de materiales
-- Nota: en el diagrama viene tanto 'disponible' (1 o 0) como 'estado' (texto)
CREATE TABLE IF NOT EXISTS materiales (
    identificador_material INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre_componente TEXT NOT NULL,
    descripcion_breve TEXT,
    disponible INTEGER NOT NULL DEFAULT 1,
    numero_serie TEXT NOT NULL UNIQUE,
    precio_reposicion REAL NOT NULL DEFAULT 0.0,
    fotografia_componente_fisico TEXT,
    estado TEXT NOT NULL DEFAULT 'disponible'
);

-- 5. Tabla de pedidos
-- Nota: en los prototipos el pedido se ve como #PR-0247 pero en la tabla dice numerico
CREATE TABLE IF NOT EXISTS pedidos (
    numero_pedido INTEGER PRIMARY KEY AUTOINCREMENT,
    boleta_alumno TEXT NOT NULL,
    numero_total_materiales INTEGER NOT NULL,
    fecha_hora_solicitud TEXT NOT NULL,
    fecha_hora_aceptacion TEXT,
    folio_admin_acepta INTEGER,
    estado_pedido TEXT NOT NULL DEFAULT 'pendiente',
    fecha_hora_max_entrega TEXT NOT NULL,
    FOREIGN KEY (boleta_alumno) REFERENCES alumnos(boleta),
    FOREIGN KEY (folio_admin_acepta) REFERENCES administradores(folio)
);

-- 6. Tabla de detalle_pedido (guarda cada material que va dentro de un pedido)
CREATE TABLE IF NOT EXISTS detalle_pedido (
    id_detalle INTEGER PRIMARY KEY AUTOINCREMENT,
    numero_pedido INTEGER NOT NULL,
    identificador_material INTEGER NOT NULL,
    estado_devolucion TEXT NOT NULL DEFAULT 'pendiente',
    observaciones TEXT,
    folio_admin_recibe INTEGER,
    fecha_hora_devolucion TEXT,
    FOREIGN KEY (numero_pedido) REFERENCES pedidos(numero_pedido),
    FOREIGN KEY (identificador_material) REFERENCES materiales(identificador_material),
    FOREIGN KEY (folio_admin_recibe) REFERENCES administradores(folio)
);
