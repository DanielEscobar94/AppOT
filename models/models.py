from extensions import db
from sqlalchemy.sql import func
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
import enum
import re

# Importar utilidad de timezone
try:
    from utils.timezone_utils import get_local_now
except ImportError:
    # Fallback: devolver hora de Colombia con timezone
    import pytz
    def get_local_now():
        from datetime import datetime
        colombia_tz = pytz.timezone('America/Bogota')
        return datetime.now(colombia_tz)

# --- Productos en Orden de Trabajo ---
class ProductoOrden(db.Model):
    __tablename__ = "productos_orden"
    id = db.Column(db.Integer, primary_key=True)
    orden_id = db.Column(db.Integer, db.ForeignKey("ordenes_trabajo.id"), nullable=False)
    producto_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    cantidad = db.Column(db.Integer, nullable=False)
    precio_unitario = db.Column(db.Numeric(10, 2), nullable=False)
    nombre_producto = db.Column(db.String(200), nullable=True)  # Nombre personalizado del producto
    orden = db.relationship("OrdenTrabajo", back_populates="productos")
    producto = db.relationship("Product")
    
    def get_nombre_display(self):
        """Retorna el nombre personalizado en mayúsculas si existe, sino el nombre del producto en mayúsculas"""
        if self.nombre_producto:
            return self.nombre_producto.upper()
        elif self.producto and self.producto.nombre:
            return self.producto.nombre.upper()
        return "PRODUCTO ELIMINADO"

# MODELOS

# --- Categoria ---
class Category(db.Model):
    __tablename__ = "category"
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), unique=True, nullable=False)
    def __repr__(self):
        return f"<Category {self.nombre}>"

# New Category table for OrdenTrabajo categories (for migration from Enum)
# Note: we'll keep the existing OrdenTrabajo.categoria Enum column temporarily
# and add OrdenTrabajo.category_id as FK; once data is migrated we can drop the enum column.
class OTCategory(db.Model):
    __tablename__ = 'ot_category'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False, unique=True)
    activo = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now())
    def __repr__(self):
        return f"<OTCategory {self.nombre}>"

# --- Cliente ---
class Client(db.Model):
    __tablename__ = "clients"
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(120), nullable=False)
    cc = db.Column(db.String(12), unique=True, nullable=True)
    nit = db.Column(db.String(11), unique=True, nullable=True)
    correo = db.Column(db.String(120), unique=True, nullable=True)
    telefono = db.Column(db.String(20), nullable=True)
    ordenes = db.relationship("OrdenTrabajo", back_populates="client", lazy="selectin")
    def __repr__(self):
        return f"<Client {self.nombre}>"

# --- Sucursal ---
class Branch(db.Model):
    __tablename__ = "branches"
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False, unique=True)
    direccion = db.Column(db.String(200))
    ciudad = db.Column(db.String(100))
    estado = db.Column(db.String(100))
    activo = db.Column(db.Boolean, default=True)
    consecutivo_ot = db.Column(db.Integer, default=1)
    consecutivo_factura = db.Column(db.Integer, default=1)
    users = db.relationship("User", back_populates="branch", lazy="dynamic")
    sequences = db.relationship("BranchSequence", back_populates="branch", cascade="all, delete-orphan")
    ordenes = db.relationship("OrdenTrabajo", back_populates="branch", lazy="selectin")

# --- Secuencia de sucursal ---
class BranchSequence(db.Model):
    __tablename__ = "branch_sequences"
    id = db.Column(db.Integer, primary_key=True)
    branch_id = db.Column(db.Integer, db.ForeignKey("branches.id"), nullable=False)
    tipo = db.Column(db.String(20), nullable=False)
    siguiente = db.Column(db.Integer, default=1)
    branch = db.relationship("Branch", back_populates="sequences")

# --- Inventario por sucursal eliminado (no se maneja stock) ---

# --- Producto ---
class Product(db.Model):
    __tablename__ = 'products'
    id = db.Column(db.Integer, primary_key=True)
    sku = db.Column(db.String(50), unique=True, nullable=False)
    nombre = db.Column(db.String(120), nullable=False)
    precio = db.Column(db.Numeric(10, 2), nullable=False)
    bloqueado = db.Column(db.Boolean, default=False, nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "sku": self.sku,
            "label": self.nombre,  # Para compatibilidad con el autocompletado
            "nombre": self.nombre,
            "precio": float(self.precio) if self.precio else 0.0,
            "bloqueado": bool(self.bloqueado)
        }

# --- Usuario ---
class User(db.Model, UserMixin):
    __tablename__ = "user"
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    username = db.Column(db.String(64), unique=True, nullable=True)
    password_hash = db.Column(db.String(256), nullable=False)
    rol = db.Column(db.String(20), default="vendedor")
    # Indica si este usuario representa un sitio físico de reparación
    es_sitio_reparacion = db.Column(db.Boolean, default=False, nullable=False)
    # Para controlar una sola sesión activa por usuario
    session_id = db.Column(db.String(256), nullable=True)
    ordenes_asignadas = db.relationship("OrdenTrabajo", foreign_keys="[OrdenTrabajo.tecnico_id]", back_populates="tecnico", lazy="selectin")
    anticipos_registrados = db.relationship("Anticipo", back_populates="registrado_por", lazy="select")
    branch_id = db.Column(db.Integer, db.ForeignKey("branches.id"))
    branch = db.relationship("Branch", back_populates="users")
    notifications = db.relationship('Notification', back_populates='user', cascade='all, delete-orphan')
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    def is_authenticated(self):
        return True
    def is_active(self):
        return True
    def is_anonymous(self):
        return False
    def get_id(self):
        return str(self.id)

# --- Login Logs ---
class LoginLog(db.Model):
    __tablename__ = "login_logs"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    user = db.relationship("User")
    login_time = db.Column(db.DateTime(timezone=True), default=get_local_now, server_default=func.now())
    ip_address = db.Column(db.String(45), nullable=True)  # IPv4/IPv6
    user_agent = db.Column(db.Text, nullable=True)
    success = db.Column(db.Boolean, default=True)

# --- Estado y Categoria de Orden ---
class EstadoOrden(enum.Enum):
    BUEN_ESTADO = "buen estado"
    REGULAR_ESTADO = "regular estado"
    MAL_ESTADO = "mal estado"
class CategoriaOrden(enum.Enum):
    RELOJ = "reloj"
    BATERIA = "bateria"
    EQUIPO_ELECTRONICO = "Articulo electronico"

# --- Orden de Trabajo ---
class OrdenTrabajo(db.Model):
    __tablename__ = "ordenes_trabajo"
    id = db.Column(db.Integer, primary_key=True)
    # Ensure both DB-side and Python-side defaults so objects get a timestamp
    fecha_creacion = db.Column(db.DateTime(timezone=True), default=get_local_now, server_default=func.now())
    referencia = db.Column(db.String(200), nullable=False)
    repuestos_usados = db.Column(db.Text, nullable=True)
    estado_equipo = db.Column(db.Enum(EstadoOrden), nullable=True)
    caracteristicas_articulo = db.Column(db.Text, nullable=True)
    articulos_json = db.Column(db.Text, nullable=True)  # Stores JSON with article groupings
    # New explicit battery fields (kept nullable for backward compatibility)
    bateria_voltaje = db.Column(db.String(50), nullable=True)
    bateria_amperaje = db.Column(db.String(50), nullable=True)
    bateria_celdas = db.Column(db.String(20), nullable=True)
    bateria_marca = db.Column(db.String(100), nullable=True)
    bateria_aplicacion = db.Column(db.String(50), nullable=True)
    # legacy enum column kept for migration purposes
    categoria = db.Column(db.Enum(CategoriaOrden), nullable=True)
    # new FK to OTCategory (use this as the canonical category after migration)
    category_id = db.Column(db.Integer, db.ForeignKey('ot_category.id'), nullable=True)
    category = db.relationship('OTCategory', backref='ordenes')
    descripcion = db.Column(db.Text, nullable=True)  # Opcional: cada artículo tiene su propia descripción
    consecutivo = db.Column(db.String(100), unique=True, nullable=False)
    entregado = db.Column(db.Boolean, default=False)
    fecha_entrega = db.Column(db.DateTime(timezone=True), nullable=True)
    # Service lifecycle state: 'pendiente', 'en_proceso', 'finalizado'
    estado = db.Column(db.String(20), default='pendiente')
    impreso = db.Column(db.Boolean, default=False)  # Indica si ya se imprimio el ticket
    client_id = db.Column(db.Integer, db.ForeignKey("clients.id"), nullable=False)
    client = db.relationship("Client", back_populates="ordenes", lazy="selectin")
    tecnico_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)  # Opcional - cada artículo tiene su sitio
    tecnico = db.relationship("User", foreign_keys=[tecnico_id], back_populates="ordenes_asignadas", lazy="selectin")
    responsable_nombre = db.Column(db.String(100), nullable=True)  # Nombre del responsable que elabora la OT
    created_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)  # Usuario que creo la OT
    created_by = db.relationship("User", foreign_keys=[created_by_id], lazy="selectin")
    branch_id = db.Column(db.Integer, db.ForeignKey("branches.id"), nullable=False)
    branch = db.relationship("Branch", back_populates="ordenes", lazy="selectin")
    anticipos = db.relationship("Anticipo", back_populates="orden")
    marca = db.Column(db.String(100), nullable=True)
    productos = db.relationship("ProductoOrden", back_populates="orden", cascade="all, delete-orphan")
    # Repuestos instalados en la orden (información interna)
    repuestos_instalados = db.relationship("RepuestoInstalado", back_populates="orden", cascade="all, delete-orphan", lazy="dynamic")
    def parsed_caracteristicas(self):
        """Parsea la cadena serializada en caracteristicas_articulo y devuelve
        un diccionario con campos de bateria y otros elementos.

        Ejemplo de salida:
        {
            'bateria': {'voltaje':'3.7V', 'amperaje':'2000 mAh', 'celdas':'2', 'marca':'MarcaX', 'aplicacion':'industrial'},
            'otros': ['Caja rayada', 'Cristal roto', 'Eslabones: 2']
        }
        """
        out = {'bateria': {}, 'otros': []}
        if not self.caracteristicas_articulo:
            return out
        try:
            parts = [p.strip() for p in re.split(r';\s*', self.caracteristicas_articulo) if p and p.strip()]
            for p in parts:
                if ':' in p:
                    key, val = p.split(':', 1)
                    k = key.strip().lower()
                    v = val.strip()
                    if 'voltaj' in k:
                        out['bateria']['voltaje'] = v
                    elif 'amper' in k:
                        out['bateria']['amperaje'] = v
                    elif 'cantidad' in k and 'cel' in k:
                        out['bateria']['celdas'] = v
                    elif k == 'marca':
                        out['bateria']['marca'] = v
                    elif 'aplic' in k:
                        out['bateria']['aplicacion'] = v
                    else:
                        out['otros'].append(p)
                else:
                    # checkbox-style plain value
                    out['otros'].append(p)
        except Exception:
            # en caso de parseo fallido, devolver la cadena original en 'otros'
            out['otros'] = [self.caracteristicas_articulo]
        return out

    @property
    def bateria_info(self):
        return self.parsed_caracteristicas().get('bateria', {})
    
    def total_anticipado(self):
        return sum(a.monto for a in self.anticipos)
    
    @property
    def estado_servicio(self):
        # Prefer the explicit estado column (if present) for three-way state
        try:
            if hasattr(self, 'estado') and self.estado:
                mapping = {
                    'pendiente': 'Pendiente',
                    'en_proceso': 'En proceso',
                    'finalizado': 'Finalizado'
                }
                return mapping.get(self.estado, self.estado)
        except Exception:
            pass
        # Fallback to legacy boolean view
        return "Entregado" if self.entregado else "Pendiente"
    
    def generar_consecutivo(self):
        """
        Genera un consecutivo único en el formato: SUCURSAL-TECNICO-ID
        Ejemplo: MAY-2-123
        Si no hay técnico asignado, usa 'GEN' (General)
        """
        sucursal_prefix = self.branch.nombre[:3].upper() if self.branch else "XXX"
        tecnico_id_str = str(self.tecnico.id) if self.tecnico else "GEN"
        return f"{sucursal_prefix}-{tecnico_id_str}-{self.id}"
    
    def __repr__(self):
        cat = None
        try:
            if hasattr(self, 'category') and self.category:
                cat = self.category.nombre
            elif self.categoria:
                cat = self.categoria.value
        except Exception:
            cat = None
        return f"<OT #{self.id} - {cat or 'N/A'} - {self.estado_equipo.value}>"


# --- Repuestos instalados ---
class RepuestoInstalado(db.Model):
    __tablename__ = 'repuestos_instalados'
    id = db.Column(db.Integer, primary_key=True)
    orden_id = db.Column(db.Integer, db.ForeignKey('ordenes_trabajo.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=True)
    nombre = db.Column(db.String(200), nullable=True)  # nombre libre si no hay product_id
    cantidad = db.Column(db.Integer, nullable=False, default=1)
    costo_unitario = db.Column(db.Numeric(10,2), nullable=False, default=0.0)
    costo_total = db.Column(db.Numeric(12,2), nullable=False, default=0.0)
    registrado_por_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    fecha_instalacion = db.Column(db.DateTime(timezone=True), default=get_local_now, server_default=func.now())
    notas_privadas = db.Column(db.Text, nullable=True)
    visible_para_cliente = db.Column(db.Boolean, default=False)

    orden = db.relationship('OrdenTrabajo', back_populates='repuestos_instalados')
    product = db.relationship('Product', lazy='joined')
    registrado_por = db.relationship('User', lazy='selectin')

    def calcular_totales(self):
        try:
            self.costo_total = (self.costo_unitario or 0) * (self.cantidad or 0)
        except Exception:
            self.costo_total = self.costo_unitario or 0


# --- Anticipo ---
class Anticipo(db.Model):
    __tablename__ = "anticipo"
    __table_args__ = (
        db.Index('ix_anticipo_orden_fecha', 'orden_id', 'fecha'),
    )
    
    id = db.Column(db.Integer, primary_key=True)
    monto = db.Column(db.Float, nullable=False)
    metodo_pago = db.Column(db.String(50), nullable=False)
    fecha = db.Column(db.DateTime(timezone=True), default=get_local_now)
    orden_id = db.Column(db.Integer, db.ForeignKey("ordenes_trabajo.id"), nullable=False)
    # Optional link to a Venta when the anticipo is applied to a sale
    venta_id = db.Column(db.Integer, db.ForeignKey('venta.id'), nullable=True)
    registrado_por_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    # Caja de tramite: 'appot' o 'siigo'
    caja_tramite = db.Column(db.String(20), default='appot')
    # Numero de factura de Siigo (para anticipos con tarjeta/transferencia)
    numero_factura_siigo = db.Column(db.String(50), nullable=True)
    # Branch_id directo para evitar JOIN con OT en cuadres/reportes (nullable por compatibilidad)
    branch_id = db.Column(db.Integer, db.ForeignKey("branches.id"), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now())
    orden = db.relationship("OrdenTrabajo", back_populates="anticipos")
    registrado_por = db.relationship("User", back_populates="anticipos_registrados", lazy="selectin")
    # relation to Venta (when the anticipo is consumed by a Venta)
    venta = db.relationship('Venta', backref=db.backref('anticipos', lazy='selectin'), foreign_keys=[venta_id])
    branch = db.relationship('Branch', lazy='selectin')


# Simple caja/movimiento model to record ingresos por anticipos
class CajaMovimiento(db.Model):
    __tablename__ = 'caja_movimiento'
    id = db.Column(db.Integer, primary_key=True)
    fecha = db.Column(db.DateTime(timezone=True), default=get_local_now)
    descripcion = db.Column(db.String(255), nullable=False)
    monto = db.Column(db.Numeric(10,2), nullable=False)
    tipo = db.Column(db.String(20), nullable=False)  # 'ingreso'|'egreso'
    registrado_por_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    registrado_por = db.relationship('User', lazy='selectin')

# --- Cuadre/Cierre de Caja ---
class CierreCaja(db.Model):
    __tablename__ = 'cierre_caja'
    id = db.Column(db.Integer, primary_key=True)
    fecha_cierre = db.Column(db.DateTime(timezone=True), default=get_local_now)
    fecha_inicio = db.Column(db.DateTime(timezone=True), nullable=False)
    fecha_fin = db.Column(db.DateTime(timezone=True), nullable=False)
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'), nullable=False)
    usuario_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    # Totales calculados
    total_ventas = db.Column(db.Numeric(10,2), default=0)
    total_anticipos = db.Column(db.Numeric(10,2), default=0)
    total_ingresos_extra = db.Column(db.Numeric(10,2), default=0)
    total_egresos = db.Column(db.Numeric(10,2), default=0)
    total_efectivo_esperado = db.Column(db.Numeric(10,2), default=0)
    
    # Conteo fisico
    efectivo_contado = db.Column(db.Numeric(10,2), nullable=True)
    diferencia = db.Column(db.Numeric(10,2), default=0)
    
    # Estado y observaciones
    estado = db.Column(db.String(20), default='abierto')  # 'abierto', 'cerrado'
    observaciones = db.Column(db.Text, nullable=True)
    
    # Relaciones
    branch = db.relationship('Branch', lazy='selectin')
    usuario = db.relationship('User', lazy='selectin')


# --- Notificaciones ---
class Notification(db.Model):
    __tablename__ = 'notifications'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    message = db.Column(db.String(255), nullable=False)
    link = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now())
    read = db.Column(db.Boolean, default=False)

    user = db.relationship('User', back_populates='notifications')

# --- Venta y DetalleVenta ---
class Venta(db.Model):
    __tablename__ = 'venta'
    __table_args__ = (
        db.UniqueConstraint('numero_factura', 'branch_id', name='uq_numero_factura_branch'),
    )
    id = db.Column(db.Integer, primary_key=True)
    numero_factura = db.Column(db.String(20), nullable=True)
    fecha = db.Column(db.DateTime(timezone=True), default=get_local_now)
    cliente_id = db.Column(db.Integer, db.ForeignKey('clients.id'), nullable=False)
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'), nullable=False)
    total = db.Column(db.Numeric(10, 2), nullable=False)
    # Anticipo: monto pagado como anticipo antes del cierre completo
    anticipo_total = db.Column(db.Numeric(10, 2), default=0)
    # Saldo pendiente = total - anticipo_total
    saldo = db.Column(db.Numeric(10, 2), nullable=True)
    # Estado de pago de la venta: 'pendiente' o 'pagada'
    estado_pago = db.Column(db.String(20), default='pendiente')
    # Optional relation to an Orden de Trabajo (nullable to preserve existing ventas)
    orden_id = db.Column(db.Integer, db.ForeignKey('ordenes_trabajo.id'), nullable=True)
    # Auditoria: usuario que creo la venta
    usuario_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    # Caja de tramite: 'appot' o 'siigo'
    caja_tramite = db.Column(db.String(20), default='appot')
    # Soft delete: para marcar ventas eliminadas sin borrar el registro
    eliminada = db.Column(db.Boolean, default=False)
    motivo_eliminacion = db.Column(db.Text, nullable=True)
    fecha_eliminacion = db.Column(db.DateTime(timezone=True), nullable=True)
    eliminada_por_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    # relationship to access the linked orden (if any). We expose a one-to-one convenience backref 'venta_rel'
    orden = db.relationship('OrdenTrabajo', backref=db.backref('venta_rel', uselist=False), foreign_keys=[orden_id])
    cliente = db.relationship('Client', backref=db.backref('ventas', lazy=True))
    branch = db.relationship('Branch', backref=db.backref('ventas', lazy=True))
    usuario = db.relationship('User', foreign_keys=[usuario_id], backref=db.backref('ventas_creadas', lazy=True))
    eliminada_por = db.relationship('User', foreign_keys=[eliminada_por_id], backref=db.backref('ventas_eliminadas', lazy=True))
    # Descuento aplicado en la venta (valor absoluto en la moneda)
    descuento = db.Column(db.Numeric(10, 2), default=0)
# Backwards-compatibility alias:
# Some templates and code expect the attribute name `client` on Venta objects (English),
# while the model uses `cliente` (Spanish). Provide a read-only alias so both work.
setattr(Venta, 'client', property(lambda self: self.cliente))
class IdempotencyKey(db.Model):
    __tablename__ = 'idempotency_keys'
    # store a per-request unique key to avoid processing the same request twice
    key = db.Column(db.String(128), primary_key=True)
    venta_id = db.Column(db.Integer, db.ForeignKey('venta.id'), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now())
    venta = db.relationship('Venta', lazy='joined')
class DetalleVenta(db.Model):
    __tablename__ = 'detalle_venta'
    id = db.Column(db.Integer, primary_key=True)
    venta_id = db.Column(db.Integer, db.ForeignKey('venta.id'), nullable=False)
    producto_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    cantidad = db.Column(db.Integer, nullable=False)
    precio_unitario = db.Column(db.Numeric(10, 2), nullable=False)
    subtotal = db.Column(db.Numeric(10, 2), nullable=False)
    nombre_producto = db.Column(db.String(200), nullable=True)  # Nombre personalizado del producto
    # Descuento aplicado por linea (porcentaje y valor absoluto)
    descuento_porcentaje = db.Column(db.Numeric(5, 2), default=0)
    descuento_valor = db.Column(db.Numeric(10, 2), default=0)
    venta = db.relationship('Venta', backref=db.backref('detalles', cascade="all, delete-orphan", lazy=True))
    producto = db.relationship('Product')
    
    def get_nombre_display(self):
        """Retorna el nombre personalizado en mayúsculas si existe, sino el nombre del producto en mayúsculas"""
        if self.nombre_producto:
            return self.nombre_producto.upper()
        elif self.producto and self.producto.nombre:
            return self.producto.nombre.upper()
        return "PRODUCTO ELIMINADO"


# --- Tipos de Salida ---
class TipoSalida(enum.Enum):
    VENTA = "venta"
    DEFECTUOSO = "defectuoso"
    PERDIDA = "perdida"
    TRASLADO = "traslado"
    DEVOLUCION = "devolucion"
    CONSUMO_INTERNO = "consumo_interno"
    REGALO = "regalo"
    OTROS = "otros"


# --- Estados de Exportacion Siigo ---
class EstadoExportacion(enum.Enum):
    PENDIENTE = "pendiente"
    PROCESADO = "procesado"
    CANCELADO = "cancelado"


# --- Exportaciones a Siigo ---
class ExportacionSiigo(db.Model):
    __tablename__ = 'exportaciones_siigo'
    id = db.Column(db.Integer, primary_key=True)
    fecha_exportacion = db.Column(db.DateTime(timezone=True), default=get_local_now, server_default=func.now())
    fecha_desde = db.Column(db.Date, nullable=True)
    fecha_hasta = db.Column(db.Date, nullable=True)
    sucursal_id = db.Column(db.Integer, db.ForeignKey('branches.id'), nullable=True)
    numero_ok_siigo = db.Column(db.String(50), nullable=True)
    estado = db.Column(db.Enum(EstadoExportacion), default=EstadoExportacion.PENDIENTE)
    archivo_excel = db.Column(db.String(255), nullable=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    total_registros = db.Column(db.Integer, default=0)
    valor_total = db.Column(db.Numeric(15, 2), default=0.00)
    observaciones = db.Column(db.Text, nullable=True)
    fecha_procesado = db.Column(db.DateTime(timezone=True), nullable=True)
    
    # Relaciones
    sucursal = db.relationship('Branch', backref=db.backref('exportaciones_siigo', lazy=True))
    usuario = db.relationship('User', backref=db.backref('exportaciones_siigo', lazy=True))
    
    def __repr__(self):
        return f"<ExportacionSiigo {self.id} - {self.estado.value} - {self.archivo_excel}>"


# --- Salida de Productos ---
class SalidaProducto(db.Model):
    __tablename__ = 'salida_producto'
    id = db.Column(db.Integer, primary_key=True)
    fecha = db.Column(db.DateTime(timezone=True), default=get_local_now, server_default=func.now())
    producto_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    cantidad = db.Column(db.Integer, nullable=False)
    tipo_salida = db.Column(db.Enum(TipoSalida), nullable=False)
    motivo = db.Column(db.String(255), nullable=True)  # Descripcion del motivo
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'), nullable=False)
    usuario_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    # Referencia opcional a venta (cuando tipo_salida = VENTA)
    venta_id = db.Column(db.Integer, db.ForeignKey('venta.id'), nullable=True)
    
    # Valor unitario del producto al momento de la salida
    valor_unitario = db.Column(db.Numeric(10, 2), nullable=True)
    valor_total = db.Column(db.Numeric(10, 2), nullable=True)
    
    # Numero OK generado por Siigo
    numero_ok_siigo = db.Column(db.String(50), nullable=True)
    
    # Relaciones
    producto = db.relationship('Product', backref=db.backref('salidas', lazy=True))
    branch = db.relationship('Branch', backref=db.backref('salidas_productos', lazy=True))
    usuario = db.relationship('User', backref=db.backref('salidas_registradas', lazy=True))
    venta = db.relationship('Venta', backref=db.backref('salidas_asociadas', lazy=True))
    
    def __repr__(self):
        return f"<SalidaProducto {self.producto.nombre} - {self.cantidad} - {self.tipo_salida.value}>"


# --- Solicitud de Eliminación de Venta ---
class SolicitudEliminacionVenta(db.Model):
    __tablename__ = 'solicitud_eliminacion_venta'
    id = db.Column(db.Integer, primary_key=True)
    venta_id = db.Column(db.Integer, db.ForeignKey('venta.id'), nullable=False)
    solicitante_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    motivo = db.Column(db.Text, nullable=False)
    estado = db.Column(db.String(20), default='pendiente')  # pendiente, aprobada, rechazada
    aprobador_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    fecha_solicitud = db.Column(db.DateTime(timezone=True), default=get_local_now)
    fecha_respuesta = db.Column(db.DateTime(timezone=True), nullable=True)
    comentario_respuesta = db.Column(db.Text, nullable=True)
    
    # Relaciones
    venta = db.relationship('Venta', backref=db.backref('solicitudes_eliminacion', lazy=True))
    solicitante = db.relationship('User', foreign_keys=[solicitante_id], backref=db.backref('solicitudes_eliminacion_enviadas', lazy=True))
    aprobador = db.relationship('User', foreign_keys=[aprobador_id], backref=db.backref('solicitudes_eliminacion_procesadas', lazy=True))
    
    def __repr__(self):
        return f"<SolicitudEliminacionVenta Venta#{self.venta_id} - {self.estado}>"


# --- Traslado entre Sucursales ---
class Traslado(db.Model):
    __tablename__ = 'traslado'
    id = db.Column(db.Integer, primary_key=True)
    numero_traslado_siigo = db.Column(db.String(100), unique=True, nullable=False)
    branch_origen_id = db.Column(db.Integer, db.ForeignKey('branches.id'), nullable=False)
    branch_destino_id = db.Column(db.Integer, db.ForeignKey('branches.id'), nullable=False)
    fecha = db.Column(db.DateTime(timezone=True), default=get_local_now, nullable=False)
    responsable = db.Column(db.String(200), nullable=False)
    observacion = db.Column(db.Text, nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=get_local_now)
    
    # Campos de confirmación
    estado = db.Column(db.String(20), default='pendiente', nullable=False)  # pendiente/confirmado/anulado
    confirmado_por = db.Column(db.String(200), nullable=True)
    fecha_confirmacion = db.Column(db.DateTime(timezone=True), nullable=True)
    # Campos de anulación
    anulado_por = db.Column(db.String(200), nullable=True)
    motivo_anulacion = db.Column(db.Text, nullable=True)
    fecha_anulacion = db.Column(db.DateTime(timezone=True), nullable=True)
    
    # Relaciones
    branch_origen = db.relationship('Branch', foreign_keys=[branch_origen_id], backref=db.backref('traslados_origen', lazy=True))
    branch_destino = db.relationship('Branch', foreign_keys=[branch_destino_id], backref=db.backref('traslados_destino', lazy=True))
    usuario = db.relationship('User', backref=db.backref('traslados', lazy=True))
    detalles = db.relationship('DetalleTraslado', back_populates='traslado', lazy=True, cascade='all, delete-orphan')
    
    def __repr__(self):
        return f"<Traslado #{self.numero_traslado_siigo}>"


# --- Detalle de Traslado ---
class DetalleTraslado(db.Model):
    __tablename__ = 'detalle_traslado'
    id = db.Column(db.Integer, primary_key=True)
    traslado_id = db.Column(db.Integer, db.ForeignKey('traslado.id'), nullable=False)
    producto_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=True)
    cantidad = db.Column(db.Numeric(10, 2), nullable=False)
    descripcion = db.Column(db.Text, nullable=True)
    
    # Relaciones
    traslado = db.relationship('Traslado', back_populates='detalles')
    producto = db.relationship('Product')
    
    def get_nombre_display(self):
        """Retorna la descripción si existe, sino el nombre del producto"""
        if self.descripcion:
            return self.descripcion.upper()
        elif self.producto and self.producto.nombre:
            return self.producto.nombre.upper()
        return "PRODUCTO NO ESPECIFICADO"
    
    def __repr__(self):
        return f"<DetalleTraslado {self.cantidad} x {self.get_nombre_display()}>"
