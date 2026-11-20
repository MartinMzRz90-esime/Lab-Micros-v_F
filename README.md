# Sistema de gestión para préstamo de equipo del laboratorio de microprocesadores

ESIME Culhuacán · Proyecto integrado: capa 1 (frontend), capa 2 (lógica de negocio) y capa 3 (datos).

```
lab_micros/
├── frontend/                 Capa 1 - Presentación (HTML, CSS, JavaScript)
├── backend/
│   ├── app.py                Capa 2 - API REST (controladores) + servidor del frontend
│   ├── logica/               Capa 2 - Gestores del diseño v3.1
│   ├── datos/                Capa 3 - Repositorio ORM + SQLite
│   ├── semilla.py            Datos iniciales (administrador, materiales, alumno de prueba)
│   ├── pruebas/              Pruebas automáticas de integración
│   └── requirements.txt
├── README.md                 Este archivo
└── CAMBIOS.md                Lista de cambios y trazabilidad con el SRS
```

## 1. Requisitos

- **Python 3.10 o superior.** Para comprobarlo, abre una terminal y escribe `python --version`. En Windows también puedes usar `py --version`.
  Si no lo tienes, descárgalo de python.org. En Windows, durante la instalación marca la casilla **"Add Python to PATH"**.
- Un navegador web (Chrome, Edge o Firefox).

## 2. Instalación (solo la primera vez)

Abre una terminal **dentro de la carpeta `backend`**:

- **Windows:** abre la carpeta `lab_micros\backend` en el Explorador, escribe `cmd` en la barra de direcciones y presiona Enter.
- **macOS / Linux:** `cd ruta/a/lab_micros/backend`

Después instala las dos dependencias:

```bash
pip install -r requirements.txt
```

> Si `pip` no se reconoce, usa `python -m pip install -r requirements.txt` (o `py -m pip ...` en Windows).

## 3. Ejecutar el sistema

Desde la carpeta `backend`:

```bash
python app.py
```

Después abre en el navegador: **http://localhost:8000**

El servidor entrega el frontend y la API al mismo tiempo. Para detenerlo presiona `Ctrl + C` en la terminal.

**Importante:** no abras los `.html` con doble clic. Siempre entra por `http://localhost:8000`, porque si no, el frontend no puede hablar con la API.

### Cuentas de prueba

La primera vez que arranca, el sistema crea estos datos automáticamente:

| Rol | Campo en el login | Identificador | Contraseña |
|---|---|---|---|
| Administrador | Folio | `20200001` | `admin12345` |
| Alumno | Boleta | `2026630148` | `alumno12345` |

También hay 16 materiales de ejemplo. Puedes registrar más alumnos desde la pantalla de registro.

### Opciones útiles

| Comando | Para qué sirve |
|---|---|
| `python app.py --simular-hora 10:00` | Probar **fuera del horario de 07:00 a 21:00 h**. El servidor cree que son las 10:00 y el reloj avanza normal. Sin esto, de noche el carrito no deja hacer pedidos (Req 4.5). |
| `python app.py --red` | Probar desde **tu celular** conectado a la misma red Wi-Fi. La terminal muestra la dirección (por ejemplo `http://192.168.1.50:8000`). Si no carga, permite Python en el firewall de Windows. |
| `python app.py --puerto 8080` | Usar otro puerto si el 8000 está ocupado. |
| `python semilla.py --reiniciar` | Borrar la base de datos y empezar de cero con los datos de ejemplo (con el servidor detenido). |

Las opciones se pueden combinar: `python app.py --red --simular-hora 10:00`

## 4. Pruebas automáticas

Desde `backend`:

```bash
python -m unittest pruebas.test_integracion -v
```

Son 15 pruebas que recorren la API completa con una base de datos temporal y un reloj simulado, así que no tocan tus datos ni hay que esperar los 30 minutos de tolerancia. Deben terminar en `OK`.

## 5. Recorrido de pruebas manuales sugerido

Conviene tener dos navegadores, o una ventana normal y otra de incógnito: uno para el alumno y otro para el administrador.

**Alumno**
1. Registro: intenta registrarte con la boleta `2026630148` → debe salir "Número de boleta invalido" (Req 2.9). Después regístrate con una boleta nueva: entras directo a **Principal alumno** (Req I-2.3).
2. Carrito: agrega 5 multímetros → al quinto debe salir el aviso de máximo 4 iguales (Req 2.8).
3. Elige un horario (+1:30 h o +3 h) y confirma el pedido → el botón se deshabilita con "Ya tienes un pedido activo" (Req 2.5).
4. Mis préstamos: aparece el pedido *Pendiente de recoger* con el botón **Cancelar pedido** (Req 2.9). Puedes probarlo y volver a pedir.
5. Principal alumno (es la pantalla que abre al iniciar sesión, Req I-2.3): cambia tu nombre o correo y guarda (Req 2.4). El botón **razón de la suspensión o bloqueo** dice "No estás suspendido o bloqueado" si tu cuenta está activa (Req I-2.4).
6. Historial: después de que el administrador entregue y reciba piezas, aparecen en una tabla (Req I-2.6).

**Administrador**
7. Sección de préstamos: acepta el pedido. Se registran tu folio y la hora (Req 5.1).
8. Devoluciones: marca las piezas una por una. Al marcar la última sale "Pedido completado" (Req 5.2 y 4.2).
9. Control de alumnos: pulsa **Ver información** (o el **nombre**) de un alumno → se abre la ventana con sus datos, su estado y los botones **Bloquear alumno** y **Quitar sanciones** (Req I-5.4 e I-5.5). Bloquéalo con un motivo; luego entra como ese alumno al carrito y debe salir el aviso con la causa (Req 5.5 e I-2.10). Al final quítale las sanciones.
10. Gestión de inventario: registra un material con foto y edita otro con el botón **Editar** (Req 5.4 y 5.7).
11. Gestor de administradores: crea un administrador. Se muestra el folio asignado, y puedes iniciar sesión con él (Req 5.6).
12. Cerrar sesión: es el último botón de la barra superior del administrador (Req I-5.1).

**Temporizadores (Req 4.4 y 2.12)**
- Si un pedido se queda pendiente más de **30 minutos**, se cancela solo y las piezas se liberan.
- Si un pedido aceptado pasa su hora máxima de devolución, el alumno queda **Suspendido**. Al devolver todas las piezas vuelve a **Activo**.
- El servidor revisa estas reglas cada minuto. Para verlo sin esperar 1:30 h: arranca con `--simular-hora 20:55`, haz y acepta un pedido de 1:30 h, y deja el servidor corriendo. También puedes confiarte de las pruebas automáticas, que lo simulan.

## 6. Problemas comunes

| Problema | Solución |
|---|---|
| `python` no se reconoce | Usa `py` en Windows, o reinstala Python marcando "Add Python to PATH". |
| `ModuleNotFoundError: flask` o `jwt` | Falta el paso 2: `pip install -r requirements.txt`. |
| "No se pudo conectar con el servidor" | El servidor no está corriendo, o abriste el HTML con doble clic. Entra por `http://localhost:8000`. |
| `Address already in use` | El puerto 8000 está ocupado: `python app.py --puerto 8080`. |
| El carrito no muestra horarios | Estás fuera del horario de 07:00 a 21:00 h (Req 4.5). Usa `--simular-hora 10:00`. |
| Me saca al login al reiniciar el servidor | Es normal: los tokens se firman con una clave nueva en cada arranque. Vuelve a iniciar sesión. |
