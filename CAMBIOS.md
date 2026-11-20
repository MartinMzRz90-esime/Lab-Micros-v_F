# Registro de cambios de la fase de codificación (integración)

Base: SRS v4.0 (20/10/2026) y Diseño v3.1 (06/11/2026). **El SRS no se modificó.** Donde los documentos no coinciden o no dicen lo suficiente, se tomó una decisión de implementación que cumple el requisito (sección 4).

En el código, cada cambio a archivos existentes está marcado con el comentario `[INTEGRACIÓN]`.

## 1. Capa 3: datos (`backend/datos/capa_datos_sqlite.py`)

Solo se **agregaron** métodos de consulta al final de `RepositorioORM`, en la sección "6. Consultas adicionales para la capa 2". Ningún método existente cambió, y la prueba original del archivo (`python capa_datos_sqlite.py`) sigue pasando.

| Método nuevo | Uso en la capa 2 | Requisito |
|---|---|---|
| `obtenerAlumnoPorBoleta()` | Reconstruir al alumno desde el token | F-1.3 |
| `obtenerAdministradorPorFolio()` | Reconstruir al administrador desde el token | F-1.3 |
| `listarAdministradores()`, `contarAdministradores()` | Gestor de administradores y administrador inicial | F-5.0, I-5.11 |
| `obtenerMaterialPorId()` | Editar material | F-5.4 |
| `obtenerPedido()`, `obtenerDetallePedido()` | Aceptar, rechazar, cancelar y devolver | F-2.9, F-5.1, F-5.2 |
| `listarSolicitudesAdmin()` | Sección de préstamos | F-5.1, I-5.2 |
| `listarPiezasPrestadas()` | Pantalla de devoluciones | F-5.2, I-5.3 |

## 2. Capa 2: lógica de negocio (nueva, `backend/`)

| Archivo | Componente del diseño | Requisitos |
|---|---|---|
| `app.py` | API REST (controladores). Verifica la sesión en cada operación y entrega el frontend | Arquitectura de 3 capas |
| `logica/gestor_autenticacion.py` | GestorAutenticacion: login dual, token JWT (firma, expiración y rol), registro con validaciones, cierre de sesión con revocación | F-1.3, F-2.0–2.3, F-2.6, F-2.7, F-5.3, I-1.2, I-2.9 |
| `logica/gestor_usuarios.py` | GestorUsuarios: perfil, motivo de sanción, bloqueo, quitar sanciones, suspensión y reactivación automáticas | F-2.4, F-2.12, F-2.13, F-5.5, I-2.3, I-2.4, I-5.4, I-5.5 |
| `logica/gestor_inventario.py` | GestorInventario: catálogo, alta y edición con foto, liberación de piezas | F-4.1, F-5.4, F-6.0, I-2.7, I-2.11, I-5.6, I-5.7 |
| `logica/gestor_prestamos.py` | GestorPrestamos: crear y cancelar pedidos, préstamo activo, historial, aceptar, rechazar, devoluciones por pieza, cierre automático | F-2.5, F-2.8, F-2.9, F-3.0, F-4.0, F-4.2, F-4.3, F-4.4, F-5.1, F-5.2 |
| `logica/gestor_administradores.py` | GestorAdministradores: cuenta activa y alta con folio automático | F-5.0, F-5.6, I-5.10, I-5.11 |
| `logica/motor_reglas.py` | MotorReglas: horario de 07:00 a 21:00 h, opciones +1:30 h / +3 h, revisión cada minuto (tolerancia y vencimiento), conciliación | F-2.10, F-2.12, F-4.4, F-4.5, F-4.6 |
| `logica/gestor_eventos.py` | GestorEventos: bus pub/sub en memoria con los 6 eventos del diseño y 3 reintentos | Tabla de eventos |
| `logica/adaptadores.py` | Traducción entre el modelo de datos y el formato del frontend | — |
| `logica/errores.py` | Errores de negocio con código HTTP y mensaje para el usuario | — |
| `semilla.py` | Administrador inicial, materiales y alumno de prueba | F-5.6 (primer administrador) |
| `pruebas/test_integracion.py` | 15 pruebas automáticas de la API | — |

### Eventos implementados (tabla "Eventos" del diseño)

| Evento | Emisor | Reacción |
|---|---|---|
| ComponenteDevuelto | GestorPrestamos | GestorInventario libera la pieza |
| PedidoRechazado | GestorPrestamos | GestorInventario libera las piezas |
| PedidoCancelado | GestorPrestamos | GestorInventario libera las piezas |
| PedidoCompletado | GestorPrestamos | GestorUsuarios cambia *suspendido* a *activo* |
| ToleranciaRecogidaAgotada | MotorReglas | GestorPrestamos cancela el pedido y emite PedidoCancelado |
| TiempoPrestamoVencido | MotorReglas | GestorUsuarios suspende al alumno si está activo |

### Endpoints de la API

| Método y ruta | Rol | Gestor |
|---|---|---|
| `POST /api/auth/login`, `POST /api/auth/logout` | — / cualquiera | GestorAutenticacion |
| `POST /api/alumnos` | — | GestorAutenticacion (registro) |
| `GET, PUT /api/alumnos/me`, `GET /api/alumnos/me/motivo` | Alumno | GestorUsuarios |
| `GET /api/materiales` | Alumno | GestorInventario |
| `GET /api/horarios` | Alumno | MotorReglas |
| `POST /api/pedidos`, `GET /api/pedidos/actual`, `GET /api/pedidos/historial`, `POST /api/pedidos/{id}/cancelar` | Alumno | GestorPrestamos |
| `GET /api/admin/me`, `GET, POST /api/admin/administradores` | Admin | GestorAdministradores |
| `GET, POST /api/admin/materiales`, `PUT /api/admin/materiales/{id}` | Admin | GestorInventario |
| `GET /api/admin/pedidos`, `POST /api/admin/pedidos/{id}/aceptar`, `.../rechazar` | Admin | GestorPrestamos |
| `GET /api/admin/alumnos`, `POST /api/admin/alumnos/{boleta}/bloquear`, `.../quitar-sanciones` | Admin | GestorUsuarios |
| `GET /api/admin/devoluciones`, `POST /api/admin/devoluciones/{id}/devolver` | Admin | GestorPrestamos |

## 3. Capa 1: frontend (`frontend/`)

| # | Archivo | Tipo | Cambio | Requisito |
|---|---|---|---|---|
| 1 | `js/api/apiClient.js` | Modificado | `MODO_MOCK: false` y `API_BASE_URL: "/api"`. Se agregan `cancelarPedido`, `editarMaterial`, `obtenerAdministradores` y `crearAdministrador` (en modo real y mock) | Integración |
| 2 | `alumno/prestamos.html` | Modificado | Ruta del script corregida (`js/api/...` pasa a `../js/api/...`). Sin esto la página no cargaba | I-2.5, I-2.6 |
| 3 | `js/alumno.js` (Mis préstamos) | Modificado | Botón **Cancelar pedido** si el pedido está pendiente. La fecha de entrega muestra "Pendiente · recoger antes de..." mientras no se recoja. El color del estado depende del pedido | F-2.9, F-4.4 |
| 4 | `admin/administradores.html` | **Nuevo** | Gestor de administradores: cuenta activa (nombre y folio), lista y modal de alta | F-5.6, I-5.10, I-5.11 |
| 5 | `js/admin.js` | Modificado | Opción "Gestor de administradores" en el menú y lógica de la página nueva | I-5.1, I-5.11 |
| 6 | `js/admin.js`, `admin/inventario.html` | Modificado | Botón **Editar** por material (el número de serie queda de solo lectura) | F-5.4 |
| 7 | `js/alumno.js` (Carrito) | Modificado | *Confirmar pedido* se deshabilita si hay un pedido activo o si se está fuera de horario. El aviso de éxito muestra el número de pedido y la tolerancia de 30 min | F-2.5, F-4.4, F-4.5 |
| 8 | `js/admin.js`, `admin/devoluciones.html` | Modificado | La columna "Entrega" pasa a "Fecha del pedido" | I-5.3 |
| 9 | `css/admin.css` | Modificado | El menú del administrador pasa de 4 a 5 columnas | I-5.1 |
| 10 | `img/sin-foto.svg` | **Nuevo** | Imagen para materiales sin fotografía | I-2.7 |

### 3.1 Correcciones de cumplimiento del SRS (segunda entrega, 19/11/2026)

Tras revisar el cumplimiento contra el SRS v4.0 quedaban 3 requisitos de interfaz sin cumplir (I-2.3, I-5.4 e I-5.5) y 2 con diferencias (I-5.1 e I-2.6). Solo se tocó la capa 1; el backend y la base de datos no cambiaron. Cada cambio está marcado con `[INTEGRACIÓN] Req X.X` en el código.

| # | Archivo(s) | Cambio | Requisito |
|---|---|---|---|
| 11 | `js/login.js`, `js/registro.js` | Al iniciar sesión (o al crear la cuenta) el alumno entra a **Principal alumno** (`alumno/perfil.html`) en lugar del carrito | I-2.3 |
| 12 | `alumno/perfil.html` | Título de la pantalla: "Principal alumno". El botón "ver estado de la cuenta" pasa a llamarse **razón de la suspensión o bloqueo**, como lo nombra el SRS. Se agregó el cierre `</body>` que faltaba | I-2.3 |
| 13 | `js/alumno.js` (Principal alumno) | El botón de razón muestra "No estás suspendido o bloqueado" si la cuenta está activa y, si no, el motivo registrado directamente, sin un segundo clic | I-2.3, I-2.4 |
| 14 | `admin/alumnos.html` | **Nueva ventana emergente** "Administración del alumno" con nombre, boleta, correo, estado y motivo de la sanción, y los botones **Bloquear alumno**, **Quitar sanciones** y Cerrar. El buscador queda "por nombre o boleta" | I-5.4, I-5.5 |
| 15 | `js/admin.js` (Control de alumnos) | El nombre de cada alumno es un enlace que abre esa ventana. "Bloquear alumno" abre la ventana del motivo obligatorio (I-5.9) y "Quitar sanciones" pide confirmación (I-5.8). Cada botón se deshabilita cuando no aplica (bloquear a alguien ya bloqueado, quitar sanciones a una cuenta activa). En la columna **Acciones** cada fila tiene un solo botón, **Ver información**, que abre la misma ventana (antes había botones "Sancionar" y "Quitar sanciones" en la fila); bloquear y quitar sanciones se hacen solo desde la ventana. La ventana solo muestra los datos: el SRS no contempla que el administrador edite los datos del alumno (el Req 2.4 es para que el alumno edite su propio perfil), así que no se agregó edición | I-5.4, I-5.5 |
| 16 | `js/admin.js` (menú) | "Selección de préstamos" se corrige a **Sección de préstamos**, y **Cerrar sesión** pasa a ser el sexto botón de la barra superior | I-5.1 |
| 17 | `admin/*.html` (6 páginas) | Se quitó el botón "cerrar sesión" que estaba debajo de la barra (ahora lo dibuja `admin.js` dentro de ella) | I-5.1 |
| 18 | `css/admin.css` | Barra de 6 columnas (2 filas de 3 en pantallas de menos de 560 px); estilos del enlace del alumno, de la ficha de la ventana y de los botones deshabilitados | I-5.1, I-5.4, I-5.5 |
| 19 | `js/alumno.js`, `css/alumno.css` (Historial) | El historial pasa de tarjetas a una **tabla** con las 5 columnas del SRS: número de serie, nombre, identificador de pedido, fecha y hora del pedido y fecha y hora de la devolución. En el celular la tabla se desliza hacia los lados | I-2.6 |

## 4. Decisiones de implementación (huecos o diferencias entre SRS y diseño)

| # | Situación en los documentos | Solución en el código |
|---|---|---|
| 1 | Estados del pedido distintos: SRS 3.0 (*pendiente, aceptado, devuelto*), SRS 4.2 (*finalizado*) y diseño (*cancelado, rechazado, vencido*) | Estados internos: `pendiente, aceptado, vencido, finalizado, cancelado, rechazado`. La interfaz muestra etiquetas legibles |
| 2 | Req 2.8: "máximo 8 diferentes o 4 iguales" | Máximo 8 piezas por pedido y máximo 4 con el mismo nombre de componente (validado en el frontend y en el backend) |
| 3 | Req 4.3 pide guardar el texto "pendiente", pero `folio_admin_acepta` es numérico y llave foránea | Se guarda `NULL` y la capa 2 responde "pendiente" en esos campos |
| 4 | Material tiene `disponible` y `estado` | `disponible` es la fuente de verdad para la reserva. `estado` se conserva como lo maneja la capa 3 |
| 5 | Req I-2.8 muestra la causa de la suspensión, pero ningún requisito define el texto | `motivo_sancion` se llena en automático: "Suspensión automática: el pedido PR-XXXX no se devolvió antes de la hora máxima de entrega." |
| 6 | Qué es un "pedido activo" (Req 2.5) | Un pedido en estado pendiente, aceptado o vencido |
| 7 | Req 5.6 exige un administrador autenticado para crear otro, así que alguien tiene que existir desde el inicio | `semilla.py` crea el administrador inicial (folio 20200001) cuando no hay ninguno |
| 8 | Fotografía del material definida como texto | El archivo se guarda en `frontend/img/materiales/` y en la BD se almacena la ruta |
| 9 | Numeración repetida en el SRS (dos 2.1–2.10 y dos 5.1–5.6) | Se usan los prefijos del diseño: Req-F (funcional) e Req-I (interfaz) |
| 10 | Los mockups mostraban franjas fijas ("10:00 a 11:00 h"), pero el Req 2.10 pide +1:30 h o +3 h | `/api/horarios` devuelve esas dos opciones con la hora calculada; después de las 20:00 solo +1:30, y fuera de 07:00–21:00 ninguna |
| 11 | Historial (I-2.6): "materiales que se le han prestado" | Solo se listan los pedidos que el administrador entregó; los cancelados y rechazados no aparecen |
| 12 | Sección de préstamos (Req 5.1): "solicitudes recientes" | Todas las pendientes, más las resueltas en las últimas 24 h. Las canceladas no se muestran |
| 13 | El diseño describe el bus como "asíncrono" | Los manejadores corren en memoria justo después de confirmar la transacción emisora, con 3 reintentos. Si alguno falla, la conciliación del MotorReglas corrige el estado en el siguiente ciclo |

## 5. Verificación realizada

- 15 pruebas automáticas de la API (`pruebas/test_integracion.py`): todas pasan.
- El `apiClient.js` real se ejecutó contra el servidor en marcha (registro, pedidos, cancelación, aceptación, devoluciones, bloqueos, alta y edición de material con foto, alta de administradores): todo correcto.
- Recorrido de la interfaz en Chrome sin ventana (headless), en vista móvil y de escritorio: login, carrito, pedido, Mis préstamos, aceptación, devoluciones, inventario, edición y gestor de administradores, sin errores de JavaScript.
- Sintaxis de todos los archivos `.js` verificada.
- Segunda entrega (19/11/2026): las 15 pruebas automáticas siguen pasando, y un recorrido automático en Chrome (vista móvil y de escritorio) comprobó los cambios 11 a 19: inicio de sesión y registro abren Principal alumno; botón de razón con cuenta activa y bloqueada; ventana del alumno con bloquear (motivo obligatorio) y quitar sanciones; buscador por boleta; barra del administrador con "Sección de préstamos" y "Cerrar sesión"; historial en tabla. Sin errores de JavaScript.
