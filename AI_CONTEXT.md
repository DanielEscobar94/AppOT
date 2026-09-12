# 📖 Contexto Global de Desarrollo y Arquitectura - AppOT

> **Única Fuente de Verdad (Single Source of Truth)** del proyecto **AppOT**.
> Este documento fue generado a partir del código real de la rama `dev`. Si algo aquí contradice al código, **el código manda** — avísanos para actualizar este archivo.
>
> **Actualizado:** 2026-09-08 · **Rama de referencia:** `dev` (HEAD `8d980c1` — Sidebar responsiva) · **Base de datos:** PostgreSQL

---

## 1. Resumen Ejecutivo del Sistema

| Campo | Detalle |
|---|---|
| **Nombre del Proyecto** | AppOT (Sistema Web Intranet de Gestión Empresarial) |
| **Cliente** | Servipilas (comercialización de pilas/baterías y servicio técnico/reparación de equipos electrónicos) |
| **Autor Principal** | John J. Arcila |
| **Objetivo** | Controlar el punto de venta (POS), la trazabilidad de órdenes de servicio técnico, inventario, traslados entre sucursales, finanzas (caja, anticipos) y auditoría de permisos |
| **Tipo de aplicación** | Monorepo Flask: backend Python + frontend Jinja2/Bootstrap renderizado en servidor (intranet) |

### Funcionalidades núcleo
- **POS / Ventas**: ticket configurable por sucursal (`instance/sales_formats.json`), anticipos, saldo pendiente y estados de pago (`pendiente`/`pagada`).
- **Órdenes de Trabajo (OT)**: servicio técnico con categorías (tabla `ot_category`), estado físico del equipo, especificaciones de batería, repuestos instalados y consecutivos por sucursal-técnico.
- **Inventario / Salidas**: salidas de producto por motivo (`venta`, `defectuoso`, `perdida`, `traslado`, `devolucion`, `consumo_interno`, `regalo`, `otros`).
- **Traslados entre sucursales** con flujo de confirmación y anulación.
- **Caja**: movimientos (`ingreso`/`egreso`) y cierres/cuadre por sucursal.
- **Exportaciones a Siigo** (ventas y salidas vía Excel con `openpyxl`/`pandas`).
- **Notificaciones** (campana en la sidebar, polling cada 15 s) y **solicitudes de eliminación de ventas** con aprobación de supervisor/admin.
- **Roles y permisos**: `admin`, `supervisor`, `tecnico`, `vendedor` (decorador `role_required` en `utils/decorators.py`).

---

## 2. Stack Tecnológico y Restricciones de Código Estrictas

### 2.1 Versiones exactas del stack (lock en `requirements.txt`)

| Componente | Versión |
|---|---|
| Flask | 3.1.1 |
| SQLAlchemy | 2.0.41 (Flask-SQLAlchemy 3.1.1) |
| PostgreSQL | driver **psycopg2-binary 2.9.10** |
| Flask-Migrate / Alembic | 4.1.0 / 1.16.4 |
| Flask-Login | 0.6.3 |
| Flask-WTF / WTForms | 1.2.2 / 3.2.1 |
| Jinja2 | 3.1.6 |
| Werkzeug | 3.1.3 |
| Gunicorn (WSGI en producción) | 23.0.0 |
| openpyxl / pandas (Excel → Siigo) | 3.1.5 / 2.2.3 |
| python-dotenv / pytz | 1.0.1 / 2024.1 |

**Frontend:** Jinja2 + **Bootstrap 5.3.0** (CDN) + **Bootstrap Icons 1.10.5** + Google Font **Inter** + **Flatpickr** (calendarios) + **Cleave.js** (máscaras numéricas) + **JavaScript vanilla** (nada de jQuery).

### 2.2 Reglas críticas de desarrollo (inviolables)

- **SQLAlchemy 2.0 — sintaxis moderna obligatoria:** ⛔ **PROHIBIDO** usar la sintaxis antigua `Model.query`. Usa exclusivamente `select()`, `insert()`, `update()` y `delete()` ejecutados con `db.session.execute(...)`. Las relaciones deben declararse con `mapped_column` y cargarse con `selectinload()` / `joinedload()` para evitar el problema **N+1**.
  > ⚠️ *Estado real del código:* `models/models.py` aún usa el estilo declarativo clásico (`db.Column`, `db.relationship`). El modelo está **en migración hacia SQLAlchemy 2.0**; los módulos nuevos y las rutas NO deben usar `Model.query` y deben usar `db.session.execute()`.

- **Frontend:** ⛔ Prohibido jQuery o frameworks JS pesados. Todo comportamiento dinámico con **JavaScript nativo (Vanilla JS)** + componentes estándar de Bootstrap 5.3.

- **Formularios:** Toda entrada de datos del backend debe validarse con **Flask-WTF** usando los módulos de `forms/` (no validar a mano con `request.form`).

- **Otras reglas de facto:**
  - El navbar superior fue **reemplazado por una sidebar izquierda** (`templates/base.html` + `static/js/sidebar.js`): barra fija de `250px` en escritorio (colapsable a `64px`, estado persistido en `localStorage` con clave `appot.sidebar`) y **Offcanvas** nativo de Bootstrap en móvil/tablet (`<1200px`).
  - No romper los bloques Jinja2 de `base.html` (`content`, `scripts`, `styles`, `extra_css`, `extra_js`, `body_class`): más de 45 plantillas los extienden.
  - `templates/users/login.html` **no** extiende `base.html` (es independiente).
  - El layout POS (`templates/layouts/sales-base.html`) depende de `body.sales-active > .container` como hijo directo del `<body>`.

---

## 3. Arquitectura del Repositorio (Árbol de Directorios Clave)

```
appot-main/
├── app.py                  # Factory create_app(): config por entorno, ProxyFix (Cloudflare),
│                           #   filtros TZ (local_datetime/local_date/local_time), init de
│                           #   admin y categorías OT, endpoint /health, registro de 14 blueprints.
│                           #   "/" redirige a dashboard.index; /test/carrito es de prueba.
├── config.py               # Config base + Development/Testing/Production (PostgreSQL, Redis,
│                           #   sesiones, CSRF, uploads). Lee variables de entorno (DATABASE_URL...).
├── extensions.py           # db = SQLAlchemy(); migrate = Migrate()  (instancias compartidas)
├── security_middleware.py  # Cabeceras de seguridad HTTP (add_security_headers)
├── requirements.txt        # Lock exacto de dependencias
├── Dockerfile              # Imagen de producción (gunicorn + dependencias)
├── docker-compose.dev.yml  # Entorno local contenerizado (app + PostgreSQL)
├── entrypoint.sh           # Arranque del contenedor (migraciones/check + lanzamiento)
├── DEV-SETUP.md            # Guía de arranque local con Docker
├── .env.dev                # Variables locales — NUNCA subir a GitHub
│
├── models/
│   ├── models.py           # Todos los modelos y enums SQLAlchemy del sistema (ver §4)
│   └── __init__.py
│
├── routes/                 # 14 blueprints + helper: cada módulo registra su Blueprint (ver §5)
│   └── sales_eliminacion.py# Helper de solicitudes de eliminación (importado por sales.py, NO es blueprint)
│
├── forms/                  # 12 módulos Flask-WTF: branch, category, clients, company, logo,
│                           #   orden_trabajo, pos, products, sales, traslado, user + forms.py base
│
├── templates/              # base.html (layout global con sidebar) + 65+ plantillas hijas
│   ├── layouts/            # sales-base / clients-base / orders-base (layout base por módulo)
│   ├── snippets/           # Tarjetas/modales reutilizables (buscador cliente, modal nuevo cliente)
│   └── .../                # branches, caja, categories, clients, dashboard, ordenes,
│                           #   ordenes_trabajo, permissions, products, reportes, sales, salidas,
│                           #   traslados, users
│
├── static/
│   ├── js/                 # Vanilla JS: auth_interceptor (401/403), sidebar (toggle+localStorage),
│   │                       #   pos-module, modal, number-format, datepicker-init, carrito OT
│   │   ├── modules/        # clients-core.js, orders-core.js, sales-core.js
│   │   └── shared/         # event-bus.js
│   ├── logo.png            # Logo de la empresa
│   └── uploads/            # Archivos subidos por la app
│
├── migrations/             # Migraciones Alembic (versions/) + alembic.ini + env.py
├── utils/
│   ├── decorators.py       # role_required (admin/supervisor/tecnico/vendedor)
│   ├── sequences.py        # Consecutivos por sucursal
│   └── timezone_utils.py   # get_local_now() (America/Bogota)
│
├── instance/               # Datos locales de configuración/estado:
│   ├── company.json        #   datos de la empresa (dashboard)
│   ├── sales_formats.json  #   formato de ticket POS por sucursal
│   └── permissions.json    #   configuración de permisos por rol (routes/permissions.py)
└── logs/                   # Logs de la aplicación
```

**Explicación rápida:** `app.py` es el **único punto de entrada** (factory `create_app`); `config.py` define 3 entornos; los `routes/` son *blueprints* independientes registrados en la factory; `forms/` centraliza la validación; `templates/` heredan de `base.html` (bloques `content`, `scripts`, `styles` + `extra_css`/`extra_js` en los layouts); `static/js/` contiene JS vanilla modular; `instance/` guarda estado de *runtime* (JSON) que no vive en la BD; `migrations/` gestiona el esquema de PostgreSQL.

---

## 4. Diccionario de Modelos y Relaciones (Base de Datos)

> Todas las tablas viven en `models/models.py`. La zona horaria por defecto es `America/Bogota` (`utils/timezone_utils.get_local_now`). Los valores de enum se almacenan como cadenas.

### 4.1 Acceso y auditoría
- **`User`** (`user`) — Usuarios del sistema. Campos: `email` (único), `username`, `password_hash`, `rol` (`admin|supervisor|tecnico|vendedor`), `es_sitio_reparacion`, `session_id` (control de **una sesión activa**), `branch_id`.
  - *Relaciones:* pertenece a una **Branch**; es técnico de muchas `OrdenTrabajo` (`ordenes_asignadas`); registra `Anticipo` y `SalidaProducto`; recibe `Notification`; tiene `branch` (sucursal).
- **`LoginLog`** (`login_logs`) — Historial de inicios de sesión (`user_id`, `login_time`, `ip_address`, `user_agent`, `success`). Útil para auditoría de accesos.

### 4.2 Catálogo
- **`Category`** (`category`) — Categorías de **productos** (nombre único).
- **`OTCategory`** (`ot_category`) — Categorías de **órdenes de trabajo** (nombre único, `activo`). Se precargan al arrancar (`init_ot_categories` en `app.py`).
- **`Product`** (`products`) — Productos: `sku` (único), `nombre`, `precio`, `bloqueado`. Sin stock por sucursal (el inventario se controla por salidas).
- **`Branch`** (`branches`) — **Sucursales**: `nombre` (único), `direccion`, `ciudad`, `estado`, `activo`, `consecutivo_ot`, `consecutivo_factura`.
  - *Relaciones:* tiene `User`, `BranchSequence`, `Venta`, `OrdenTrabajo`, `CierreCaja`, `SalidaProducto`, `ExportacionSiigo`, `Traslado` (origen/destino).
- **`BranchSequence`** (`branch_sequences`) — Contador de consecutivos por sucursal y tipo (`tipo` = OT, factura, etc.).

### 4.3 Clientes y ventas (POS)
- **`Client`** (`clients`) — Clientes: `nombre`, `cc` o `nit` (únicos), `correo`, `telefono`.
  - *Relaciones:* tiene muchas `Venta` y muchas `OrdenTrabajo`.
- **`Venta`** (`venta`) — **Ventas / POS**. Campo clave: `numero_factura` + `branch_id` (único conjunto), `total`, `anticipo_total`, `saldo`, `estado_pago` (`pendiente|pagada`), `caja_tramite` (`appot|siigo`), `descuento`, y **borrado lógico** (`eliminada`, `motivo_eliminacion`, `eliminada_por`). Expone el alias `client` para compatibilidad.
  - *Relaciones:* pertenece a `Client` y `Branch`; la crea un `User` (`usuario_id`); puede enlazarse a una `OrdenTrabajo` (`orden_id`, 1-a-1 vía `venta_rel`); tiene `detalles` (`DetalleVenta`), `anticipos` opcionales, `solicitudes_eliminacion` y `salidas_asociadas`.
- **`DetalleVenta`** (`detalle_venta`) — Líneas de la venta: `producto_id`, `cantidad`, `precio_unitario`, `subtotal`, `nombre_producto` (free-text), `descuento_porcentaje`, `descuento_valor`.
- **`IdempotencyKey`** (`idempotency_keys`) — Claves de idempotencia para no procesar dos veces la misma petición de venta (`key` PK, `venta_id` opcional).
- **`SolicitudEliminacionVenta`** (`solicitud_eliminacion_venta`) — Flujo de aprobación para eliminar ventas: `estado` (`pendiente|aprobada|rechazada`), `motivo`, `solicitante_id`, `aprobador_id`, fechas y comentario.
  - *Relaciones:* pertenece a `Venta`; `solicitante`/`aprobador` son `User`.

### 4.4 Órdenes de Trabajo (servicio técnico)
- **`OrdenTrabajo`** (`ordenes_trabajo`) — **Corazón del servicio técnico.** Campos: `referencia`, `fecha_creacion`, `estado_equipo` (enum `EstadoOrden`: `buen estado|regular estado|mal estado`), `caracteristicas_articulo`, `articulos_json`, campos de **batería** (`bateria_voltaje`, `bateria_amperaje`, `bateria_celdas`, `bateria_marca`, `bateria_aplicacion`), `estado` (`pendiente|en_proceso|finalizado`), `entregado`.
  - *Relaciones:* pertenece a `Client` y a `Branch`; la atiende un `User` técnico (`tecnico_id`); tiene `productos` (`ProductoOrden`), `repuestos_instalados`, `anticipos`, una `Venta` opcional (1-a-1) y una `OTCategory` (`category_id`, la columna `categoria` enum es legacy).
  - *Consecutivo:* `generar_consecutivo()` → `PREFIX-SUCURSAL-TECNICO-ID` (ej. `MAY-2-123`).
- **`ProductoOrden`** (`productos_orden`) — Productos asociados a una OT: `cantidad`, `precio_unitario`, `nombre_producto` (nombre libre en mayúsculas; si no, el del `Product`).
- **`RepuestoInstalado`** (`repuestos_instalados`) — Repuestos físicos instalados en la reparación: `nombre`, `cantidad`, `costo_unitario`, `costo_total`, `notas_privadas`, `visible_para_cliente`, `registrado_por_id`, `fecha_instalacion`.

### 4.5 Finanzas (caja y anticipos)
- **`Anticipo`** (`anticipo`) — Pagos anticipados sobre una OT: `monto`, `metodo_pago`, `fecha`, `caja_tramite` (`appot|siigo`), `numero_factura_siigo`, `branch_id` (denormalizado para reportes).
  - *Relaciones:* pertenece a `OrdenTrabajo` y lo registra un `User`; puede vincularse a una `Venta` (`venta_id`) cuando el anticipo se consume.
- **`CajaMovimiento`** (`caja_movimiento`) — Registro simple de caja: `descripcion`, `monto`, `tipo` (`ingreso|egreso`), `registrado_por_id`.
- **`CierreCaja`** (`cierre_caja`) — **Cuadre de caja** por sucursal: `fecha_inicio`, `fecha_fin`, `fecha_cierre`, totales (`total_ventas`, `total_anticipos`, `total_ingresos_extra`, `total_egresos`, `total_efectivo_esperado`), `efectivo_contado`, `diferencia`, `estado` (`abierto|cerrado`), `observaciones`. Relacionado a `Branch` y `User`.

### 4.6 Inventario y logística
- **`SalidaProducto`** (`salida_producto`) — Salidas de inventario: `cantidad`, `tipo_salida` (enum `TipoSalida`), `motivo`, `valor_unitario`, `valor_total`, `numero_ok_siigo`; referencias a `Product`, `Branch`, `User` y `Venta` opcional.
- **`Traslado`** (`traslado`) — Traslados **entre sucursales**: `numero_traslado_siigo` (único), `branch_origen_id`, `branch_destino_id`, `responsable`, `estado` (`pendiente|confirmado|anulado`), campos de confirmación/anulación.
  - *Relaciones:* `branch_origen`/`branch_destino` ("Branch"), lo registra un `User`, y tiene `detalles` (`DetalleTraslado`).
- **`DetalleTraslado`** (`detalle_traslado`) — Líneas del traslado: `producto_id` (opcional), `cantidad`, `descripcion` (nombre libre).

### 4.7 Integración contable (Siigo)
- **`ExportacionSiigo`** (`exportaciones_siigo`) — Exportaciones generadas: rango de fechas, `sucursal_id`, `numero_ok_siigo`, `estado` (enum `EstadoExportacion`: `pendiente|procesado|cancelado`), `archivo_excel`, `total_registros`, `valor_total`, `observaciones`, `usuario_id`.

### 4.8 Notificaciones
- **`Notification`** (`notifications`) — Avisos por usuario: `message`, `link` (URL opcional), `read` (leída), `created_at`. Se muestran en la campana de la sidebar con polling cada 15 s y endpoints `users.notifications` / `users.notifications_mark_all` / `users.mark_read`.

### 4.9 Enums auxiliares (se guardan como string)
- `EstadoOrden` — `buen estado`, `regular estado`, `mal estado`.
- `CategoriaOrden` (legacy) — `reloj`, `bateria`, `Articulo electronico`.
- `TipoSalida` — `venta`, `defectuoso`, `perdida`, `traslado`, `devolucion`, `consumo_interno`, `regalo`, `otros`.
- `EstadoExportacion` — `pendiente`, `procesado`, `cancelado`.

---

## 5. Módulos y Rutas del Sistema (Blueprints)

La aplicación registra **14 blueprints** en `app.py` (`create_app`). Cada uno gestiona un área concreta:

| Módulo (`routes/*.py`) | Blueprint | URL base | Qué gestiona |
|---|---|---|---|
| `dashboard` | `dashboard_bp` | `/dashboard` | Panel principal, métricas, acceso rápido CRUD, datos de empresa (`company.json`), cambio de logo, formato POS por sucursal (`sales_formats.json`), dashboard de vendedor |
| `clients` | `clients_bp` | `/clients` | CRUD de clientes + creación desde modal (AJAX) |
| `products` | `products_bp` | `/products` | CRUD de productos, listado, por categoría, edición |
| `categories` | `categories_bp` | `/categories` | Categorías de producto (+ variante `categories/api/nuevo.html`) |
| `sales` | `bp` (`sales`) | `/ventas` | **POS**: nueva venta, detalle, tickets, selección de sucursal, solicitudes de eliminación (usa el helper `sales_eliminacion.py`) |
| `users` | `users_bp` | `/users` | Login/logout, CRUD de usuarios, logs de login, API de notificaciones (`notifications`, `mark_read`, `mark_all`) |
| `branches` | `branches_bp` | `/branches` | CRUD de sucursales |
| `ordenes_trabajo` | `ordenes_bp` | `/ordenes` | **Órdenes de Trabajo**: crear/editar/listar, carrito de artículos, sincronización de productos desde JSON, repuestos |
| `caja` | `bp` (`caja`) | `/caja` | Cuadre/cierre de caja e historial de cierres |
| `anticipos` | `anticipos_bp` | `/anticipos` | Registro de anticipos (POST) |
| `reportes` | `reportes_bp` | `/reportes` | Reportes de ventas, reparaciones y anticipos (+ versiones imprimibles) |
| `salidas` | `salidas_bp` | `/salidas` | Registrar salidas de producto, historial de exportaciones a Siigo, detalle |
| `permissions` | `permissions_bp` | `/permissions` | Configuración de permisos por rol (almacenada en `instance/permissions.json`) |
| `traslados` | `traslados_bp` | `/traslados` | Traslados entre bodegas: crear/editar/listar/ver |

**Puntos de entrada globales** (`app.py`): `/` → `dashboard.index` (autenticado), `/health` → chequeo de salud para Docker/monitoreo, `/test/carrito` (solo desarrollo).

> 💡 **Ojo:** `routes/sales_eliminacion.py` **no es un blueprint**; es un módulo *helper* de funciones importado por `sales.py`.

---

## 6. Flujo de Trabajo, Git y Despliegue

### 6.1 Ramas
- **`main`** → **Producción** (despliegue automatizado en **Dokploy**). ⛔ **PROHIBIDO hacer commits o modificaciones directas a `main`.** Solo recibe la salida de `dev` revisada (fast-forward / PR).
- **`dev`** → **Rama activa de desarrollo y pruebas.** Todos los cambios de las IA y del desarrollo local se hacen aquí exclusivamente. Es la rama en la que estás trabajando ahora.

### 6.2 Ciclo de cambios
1. Trabajar siempre en `dev` (checkout previo si hace falta).
2. Commitear con mensajes claros (prefijo temático p.ej. `Sidebar:`, `Nav:`, `Deploy:`).
3. Push a `origin/dev` (`git push origin dev`).
4. Cuando `dev` está estable y probado → migrar a `main` con **fast-forward** (`git merge --ff-only`) y push a `origin/master`.
5. Si algo sale mal en producción publicada, usar `git revert` (nunca reescribir historia compartida).

### 6.3 Entorno y despliegue
- **Contenerizado con Docker** (`Dockerfile` + `docker-compose.dev.yml`); arranque vía `entrypoint.sh`.
- **Producción:** Gunicorn (WSGI) + **ProxyFix** configurado para **Cloudflare** (`ProxyFix(app, x_for=1, x_proto=1, x_host=1, x_prefix=1)` en `app.py`).
- **Configuración por entorno** (`config.py`): `DevelopmentConfig`, `TestingConfig`, `ProductionConfig` — seleccionada con `FLASK_ENV`.
- **Variables de entorno clave:** `DATABASE_URL` (PostgreSQL), `SECRET_KEY`, `TZ` (`America/Bogota`), `REDIS_URL` (caché en producción), `MAIL_*`.
- **Seguridad:** Flask-Login (sesiones de 24 h, una sesión activa por usuario), CSRF en formularios WTForms (`WTF_CSRF_ENABLED=True`), cabeceras de seguridad (`security_middleware.py`), control de acceso por rol (`role_required`).

---

*Fin del documento — AppOT `dev`. Actualizado el 2026-09-08.*