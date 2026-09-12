from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session
import re
from datetime import datetime
import uuid
import os
import json
from flask_login import login_required, current_user
from extensions import db
from models.models import OrdenTrabajo, CategoriaOrden, EstadoOrden, Anticipo, Client, Branch, User, ProductoOrden, OTCategory, Venta, Product, RepuestoInstalado
from models.models import Notification
from forms.orden_trabajo_form import OrdenTrabajoForm
from utils.decorators import role_required, require_branch_access, scoped_branch_param
from utils.timezone_utils import get_local_now

ordenes_bp = Blueprint("ordenes", __name__, url_prefix="/ordenes")

def sincronizar_productos_desde_json(orden):
    """
    Sincroniza productos desde articulos_json a productos_orden.
    Evita duplicados y asegura que siempre haya productos en productos_orden.
    """
    if not orden.articulos_json:
        return 0
    
    # Si ya hay productos en productos_orden, no duplicar
    if orden.productos and len(orden.productos) > 0:
        print(f"[DEBUG] OT {orden.id} ya tiene {len(orden.productos)} productos en productos_orden")
        return 0
    
    try:
        articulos = json.loads(orden.articulos_json)
        productos_agregados = 0
        
        for articulo in articulos:
            productos_articulo = articulo.get('productos', [])
            
            for prod in productos_articulo:
                try:
                    # Intentar extraer SKU de diferentes formatos
                    sku_raw = prod.get('sku', '').strip()
                    if not sku_raw:
                        continue
                    
                    # Formato: "NOMBRE (SKU)" -> extraer SKU
                    match = re.search(r'\(([^)]+)\)$', sku_raw)
                    sku = match.group(1) if match else sku_raw
                    
                    # Buscar producto por SKU
                    producto_db = Product.query.filter_by(sku=str(sku)).first()
                    
                    if not producto_db:
                        # Fallback: buscar por nombre si nombreCustom existe
                        nombre_custom = prod.get('nombreCustom', '').strip()
                        if nombre_custom:
                            producto_db = Product.query.filter(Product.nombre.ilike(f"%{nombre_custom}%")).first()
                    
                    if producto_db:
                        cantidad = int(prod.get('cantidad', 1))
                        precio = float(prod.get('precio', 0))
                        nombre_custom = prod.get('nombreCustom', '').strip()
                        
                        # Verificar que no exista ya este producto para esta orden
                        existe = ProductoOrden.query.filter_by(
                            orden_id=orden.id,
                            producto_id=producto_db.id
                        ).first()
                        
                        if not existe:
                            producto_orden = ProductoOrden(
                                orden_id=orden.id,
                                producto_id=producto_db.id,
                                cantidad=cantidad,
                                precio_unitario=precio,
                                nombre_producto=nombre_custom if nombre_custom else None
                            )
                            db.session.add(producto_orden)
                            productos_agregados += 1
                            print(f"[SYNC] Producto agregado a OT {orden.id}: {sku} x{cantidad} ${precio}")
                    else:
                        print(f"[SYNC WARNING] Producto no encontrado: SKU={sku}")
                        
                except Exception as e:
                    print(f"[SYNC ERROR] Error procesando producto: {e}")
                    continue
        
        if productos_agregados > 0:
            db.session.flush()
            print(f"[SYNC] Se agregaron {productos_agregados} productos a OT {orden.id}")
        
        return productos_agregados
        
    except Exception as e:
        print(f"[SYNC ERROR] Error general sincronizando productos para OT {orden.id}: {e}")
        return 0

@ordenes_bp.route('/listar')
@login_required
def listar_ordenes():
    sucursal_id = request.args.get('sucursal', type=int)
    # Prefer numeric client id filter when available
    cliente_id = request.args.get('cliente_id', type=int) or request.args.get('cliente', type=int)
    cliente_nombre = request.args.get('cliente_nombre', '').strip()
    fecha_inicio_str = request.args.get('fecha_inicio', '')
    fecha_fin_str = request.args.get('fecha_fin', '')
    orden_nro = request.args.get('orden', '').strip()
    sitio_reparacion_id = request.args.get('sitio_reparacion', type=int)

    # Parámetros de paginación
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)

    # Debugging info: log received cliente_id, cliente_nombre and whether request is AJAX
    try:
        print(f"[DEBUG listar_ordenes] cliente_id={cliente_id!r}, cliente_nombre={cliente_nombre!r}, AJAX={request.headers.get('X-Requested-With') == 'XMLHttpRequest'}")
    except Exception:
        pass

    query = OrdenTrabajo.query
    # Por defecto listar solo ordenes no finalizadas ni facturadas
    query = query.filter(~OrdenTrabajo.estado.in_(['finalizado', 'facturado']))
    # Scoping por sucursal: roles restringidos solo ven su sucursal
    sucursal_id = scoped_branch_param(sucursal_id)
    if sucursal_id:
        query = query.filter(OrdenTrabajo.branch_id == sucursal_id)
    # Filtro por sitio de reparación (técnico)
    if sitio_reparacion_id:
        # Buscar órdenes que tengan al menos un artículo con este sitio_reparacion_id
        query = query.filter(
            db.or_(
                OrdenTrabajo.tecnico_id == sitio_reparacion_id,
                OrdenTrabajo.articulos_json.like(f'%"sitio_reparacion_id": {sitio_reparacion_id}%')
            )
        )
    # If a numeric client id was provided, filter directly by it (preferred)
    if cliente_id:
        query = query.filter(OrdenTrabajo.client_id == cliente_id)
    elif cliente_nombre:
        clientes = Client.query.filter(Client.nombre.ilike(f'%{cliente_nombre}%')).all()
        if clientes:
            ids = [c.id for c in clientes]
            query = query.filter(OrdenTrabajo.client_id.in_(ids))
    
    # Filtro por rango de fechas
    if fecha_inicio_str:
        try:
            fecha_inicio_dt = datetime.strptime(fecha_inicio_str, '%d/%m/%Y')
            query = query.filter(OrdenTrabajo.fecha_creacion >= fecha_inicio_dt)
        except ValueError:
            pass
    if fecha_fin_str:
        try:
            fecha_fin_dt = datetime.strptime(fecha_fin_str, '%d/%m/%Y')
            fecha_fin_dt = fecha_fin_dt.replace(hour=23, minute=59, second=59)
            query = query.filter(OrdenTrabajo.fecha_creacion <= fecha_fin_dt)
        except ValueError:
            pass
    
    if orden_nro:
        if orden_nro.isdigit():
            query = query.filter(OrdenTrabajo.id == int(orden_nro))
        else:
            query = query.filter(OrdenTrabajo.consecutivo.like(f'%{orden_nro}%'))
    
    # Aplicar paginación
    ordenes_pagination = query.order_by(OrdenTrabajo.fecha_creacion.desc()).paginate(page=page, per_page=per_page, error_out=False)
    ordenes = ordenes_pagination.items
    
    # Obtener sitios de reparación para el filtro
    sitios_reparacion = User.query.filter(User.username.in_(['Taller Relojeria', 'Laboratorio Ensambles'])).order_by(User.username).all()
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return render_template('ordenes_trabajo/listar.html', ordenes=ordenes, Branch=Branch, Client=Client, sitios_reparacion=sitios_reparacion, ajax=True, ordenes_pagination=ordenes_pagination)
    return render_template('ordenes_trabajo/listar.html', ordenes=ordenes, Branch=Branch, Client=Client, sitios_reparacion=sitios_reparacion, ordenes_pagination=ordenes_pagination)


@ordenes_bp.route('/finalizadas')
@login_required
def listar_finalizadas():
    """Listado de ordenes finalizadas."""
    sucursal_id = request.args.get('sucursal', type=int)
    cliente_id = request.args.get('cliente_id', type=int) or request.args.get('cliente', type=int)
    cliente_nombre = request.args.get('cliente_nombre', '').strip()
    fecha_inicio_str = request.args.get('fecha_inicio', '')
    fecha_fin_str = request.args.get('fecha_fin', '')
    orden_nro = request.args.get('orden', '').strip()
    sitio_reparacion_id = request.args.get('sitio_reparacion', type=int)

    # Parámetros de paginación
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)

    query = OrdenTrabajo.query.filter(OrdenTrabajo.estado == 'finalizado')
    # Exclude orders that already have a linked Venta (i.e., already facturadas)
    try:
        from models.models import Venta as _Venta
        # left outer join and keep only those without a matching Venta
        query = query.outerjoin(_Venta, _Venta.orden_id == OrdenTrabajo.id).filter(_Venta.orden_id == None)
    except Exception:
        # if join fails for any reason (DB specifics), continue with original query
        pass
    if sucursal_id:
        query = query.filter(OrdenTrabajo.branch_id == sucursal_id)
    # Filtro por sitio de reparación (técnico)
    if sitio_reparacion_id:
        # Buscar órdenes que tengan al menos un artículo con este sitio_reparacion_id
        query = query.filter(
            db.or_(
                OrdenTrabajo.tecnico_id == sitio_reparacion_id,
                OrdenTrabajo.articulos_json.like(f'%\"sitio_reparacion_id\": {sitio_reparacion_id}%')
            )
        )
    if cliente_id:
        query = query.filter(OrdenTrabajo.client_id == cliente_id)
    elif cliente_nombre:
        clientes = Client.query.filter(Client.nombre.ilike(f'%{cliente_nombre}%')).all()
        if clientes:
            ids = [c.id for c in clientes]
            query = query.filter(OrdenTrabajo.client_id.in_(ids))
    
    # Filtro por rango de fechas
    if fecha_inicio_str:
        try:
            fecha_inicio_dt = datetime.strptime(fecha_inicio_str, '%d/%m/%Y')
            query = query.filter(OrdenTrabajo.fecha_creacion >= fecha_inicio_dt)
        except ValueError:
            pass
    if fecha_fin_str:
        try:
            fecha_fin_dt = datetime.strptime(fecha_fin_str, '%d/%m/%Y')
            fecha_fin_dt = fecha_fin_dt.replace(hour=23, minute=59, second=59)
            query = query.filter(OrdenTrabajo.fecha_creacion <= fecha_fin_dt)
        except ValueError:
            pass
    
    if orden_nro:
        if orden_nro.isdigit():
            query = query.filter(OrdenTrabajo.id == int(orden_nro))
        else:
            query = query.filter(OrdenTrabajo.consecutivo.like(f'%{orden_nro}%'))

    # Aplicar paginación
    ordenes_pagination = query.order_by(OrdenTrabajo.fecha_creacion.desc()).paginate(page=page, per_page=per_page, error_out=False)
    ordenes = ordenes_pagination.items
    
    # Obtener sitios de reparación para el filtro
    sitios_reparacion = User.query.filter(User.username.in_(['Taller Relojeria', 'Laboratorio Ensambles'])).order_by(User.username).all()
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return render_template('ordenes_trabajo/listar.html', ordenes=ordenes, Branch=Branch, Client=Client, sitios_reparacion=sitios_reparacion, ajax=True, finalizadas=True, ordenes_pagination=ordenes_pagination)
    return render_template('ordenes_trabajo/listar.html', ordenes=ordenes, Branch=Branch, Client=Client, sitios_reparacion=sitios_reparacion, finalizadas=True, ordenes_pagination=ordenes_pagination)


@ordenes_bp.route('/facturadas')
@login_required
def listar_facturadas():
    """Listado de ordenes facturadas (tienen una venta vinculada)."""
    sucursal_id = request.args.get('sucursal', type=int)
    cliente_id = request.args.get('cliente_id', type=int) or request.args.get('cliente', type=int)
    cliente_nombre = request.args.get('cliente_nombre', '').strip()
    fecha_inicio_str = request.args.get('fecha_inicio', '')
    fecha_fin_str = request.args.get('fecha_fin', '')
    orden_nro = request.args.get('orden', '').strip()
    sitio_reparacion_id = request.args.get('sitio_reparacion', type=int)

    # Parámetros de paginación
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)

    # Join Venta on Venta.orden_id == OrdenTrabajo.id and filter where Venta.orden_id is not null
    query = OrdenTrabajo.query.join(Venta, Venta.orden_id == OrdenTrabajo.id)
    if sucursal_id:
        query = query.filter(OrdenTrabajo.branch_id == sucursal_id)
    # Filtro por sitio de reparación (técnico)
    if sitio_reparacion_id:
        # Buscar órdenes que tengan al menos un artículo con este sitio_reparacion_id
        query = query.filter(
            db.or_(
                OrdenTrabajo.tecnico_id == sitio_reparacion_id,
                OrdenTrabajo.articulos_json.like(f'%\"sitio_reparacion_id\": {sitio_reparacion_id}%')
            )
        )
    if cliente_id:
        query = query.filter(OrdenTrabajo.client_id == cliente_id)
    elif cliente_nombre:
        clientes = Client.query.filter(Client.nombre.ilike(f'%{cliente_nombre}%')).all()
        if clientes:
            ids = [c.id for c in clientes]
            query = query.filter(OrdenTrabajo.client_id.in_(ids))

    # Filtro por rango de fechas
    if fecha_inicio_str:
        try:
            fecha_inicio_dt = datetime.strptime(fecha_inicio_str, '%d/%m/%Y')
            query = query.filter(OrdenTrabajo.fecha_creacion >= fecha_inicio_dt)
        except ValueError:
            pass
    if fecha_fin_str:
        try:
            fecha_fin_dt = datetime.strptime(fecha_fin_str, '%d/%m/%Y')
            fecha_fin_dt = fecha_fin_dt.replace(hour=23, minute=59, second=59)
            query = query.filter(OrdenTrabajo.fecha_creacion <= fecha_fin_dt)
        except ValueError:
            pass

    if orden_nro:
        if orden_nro.isdigit():
            query = query.filter(OrdenTrabajo.id == int(orden_nro))
        else:
            query = query.filter(OrdenTrabajo.consecutivo.like(f'%{orden_nro}%'))

    # Aplicar paginación
    ordenes_pagination = query.order_by(OrdenTrabajo.fecha_creacion.desc()).paginate(page=page, per_page=per_page, error_out=False)
    ordenes = ordenes_pagination.items
    
    # Provide ventas lookup (numero_factura) to template via Venta model
    ventas = {v.orden_id: v for v in Venta.query.filter(Venta.orden_id.isnot(None)).all()}
    
    # Obtener sitios de reparación para el filtro
    sitios_reparacion = User.query.filter(User.username.in_(['Taller Relojeria', 'Laboratorio Ensambles'])).order_by(User.username).all()
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return render_template('ordenes_trabajo/listar.html', ordenes=ordenes, Branch=Branch, Client=Client, sitios_reparacion=sitios_reparacion, ajax=True, facturadas=True, ventas=ventas, ordenes_pagination=ordenes_pagination)
    return render_template('ordenes_trabajo/listar.html', ordenes=ordenes, Branch=Branch, Client=Client, sitios_reparacion=sitios_reparacion, facturadas=True, ventas=ventas, ordenes_pagination=ordenes_pagination)

@ordenes_bp.route("/crear", methods=["GET", "POST"])
@login_required
def crear_orden():
    form = OrdenTrabajoForm()

    # Poblar tecnico_id con: Taller Relojeria, Laboratorio Ensambles, y el usuario actual
    tecnicos_fijos = ['Taller Relojeria', 'Laboratorio Ensambles']
    tecnicos = User.query.filter(User.username.in_(tecnicos_fijos)).all()
    
    # Agregar el usuario actual si no esta en la lista
    if current_user.is_authenticated and current_user.username not in tecnicos_fijos:
        tecnicos.append(current_user)
    
    # Agregar opcion por defecto
    form.tecnico_id.choices = [('', 'Selecciona sitio de Reparacion')] + [
        (u.id, u.username or u.email) for u in sorted(tecnicos, key=lambda x: x.username)
    ]
    
    # Obtener categorias desde la tabla OTCategory
    try:
        categorias = OTCategory.query.order_by(OTCategory.nombre.asc()).all()
        form.categoria.choices = [(c.id, c.nombre) for c in categorias]
    except Exception:
        form.categoria.choices = []


    branch_nombre = None
    if current_user.is_authenticated and current_user.branch_id:
        from models.models import Branch
        branch = Branch.query.get(current_user.branch_id)
        branch_nombre = branch.nombre if branch else None
    if request.method == "POST":
        # Idempotency check
        idempotency_key = request.form.get('idempotency_key') or str(uuid.uuid4())
        processed_keys_list = session.setdefault('processed_ot_keys', [])
        processed_keys = set(processed_keys_list)
        if idempotency_key in processed_keys:
            flash("Esta solicitud ya fue procesada. Evitando duplicados.", "warning")
            return redirect(url_for('ordenes.crear_orden'))
        # Reserve the key
        processed_keys.add(idempotency_key)
        session['processed_ot_keys'] = list(processed_keys)
        session.modified = True
        print("[DEBUG] Datos recibidos en POST:", request.form)
        print("[DEBUG] form.data:", form.data)
        print("[DEBUG] form.errors:", form.errors)
        # Eliminada la validacion de 'estado_equipo'.
        try:
            # Validar cliente explicitamente (pueden existir multiples valores si hubo duplicados en el form)
            client_values = request.form.getlist("client_id")
            # Tomar el ultimo valor no vacio
            client_id_str = next((v.strip() for v in reversed(client_values) if v and v.strip()), "")
            if not client_id_str:
                flash("Debes seleccionar un cliente antes de guardar la orden.", "danger")
                return render_template("ordenes_trabajo/crear.html", form=form, Client=Client, branch_nombre=branch_nombre)
            
            print(f"[DEBUG] client_id_str: {client_id_str}")
            client_id = int(client_id_str)
            client = Client.query.get(client_id)
            print(f"[DEBUG] client: {client}")
            if not client:
                flash("Cliente no encontrado. Debes crearlo primero.", "danger")
                return render_template("ordenes_trabajo/crear.html", form=form, Client=Client, branch_nombre=branch_nombre)

            # NOTA: La descripción ahora es opcional ya que cada artículo tiene su propia descripción
            # La validación de descripción obligatoria se ha eliminado

            # Tomar branch_id del usuario autenticado (ignorar lo que venga del formulario)
            if not current_user.branch_id:
                flash("Tu usuario no tiene una sucursal asignada. Contacta al administrador.", "danger")
                return render_template("ordenes_trabajo/crear.html", form=form, Client=Client, branch_nombre=branch_nombre)
            
            print(f"[DEBUG] current_user.branch_id: {current_user.branch_id}")
            branch_id = current_user.branch_id
            branch = Branch.query.get(branch_id)
            print(f"[DEBUG] branch: {branch}")
            if not branch:
                flash("Sucursal invalida en el usuario.", "danger")
                return render_template("ordenes_trabajo/crear.html", form=form, Client=Client, branch_nombre=branch_nombre)

            # Validar campo responsable
            print("[DEBUG] Valor de responsable:", form.responsable.data)
            print("[DEBUG] request.form.get('responsable'):", request.form.get('responsable'))
            if not form.responsable.data or not form.responsable.data.strip():
                flash("El nombre del responsable es obligatorio.", "danger")
                return render_template("ordenes_trabajo/crear.html", form=form, Client=Client, branch_nombre=branch_nombre)
            
            # Validar que solo contenga letras y espacios
            import re
            patron = r'^[a-zA-ZaeiouAEIOUnNuU\s]+$'
            if not re.match(patron, form.responsable.data.strip()):
                flash("El nombre del responsable solo puede contener letras y espacios.", "danger")
                return render_template("ordenes_trabajo/crear.html", form=form, Client=Client, branch_nombre=branch_nombre)

            # Construir kwargs y anadir creado_por_id solo si existe la columna
            # Map form.categoria (category id) to the FK and try to keep legacy enum value
            selected_cat_id = form.categoria.data
            selected_cat = OTCategory.query.get(selected_cat_id) if selected_cat_id else None
            legacy_categoria = None
            # Ya no se valida ni se asigna EstadoOrden
            legacy_categoria = None

            # Build caracteristicas_articulo: prefer serialized value if provided,
            # otherwise build from individual form fields to ensure server-side consistency.
            car_serial = request.form.get('caracteristicas_articulo')
            if not car_serial or not car_serial.strip():
                parts = []
                # multiple checkbox values
                for v in request.form.getlist('caracteristicas'):
                    if v and v.strip():
                        parts.append(v.strip())
                # extra fields
                eslab = (request.form.get('eslabones_numero') or '').strip()
                if eslab:
                    parts.append(f"Eslabones: {eslab}")
                tapa = (request.form.get('tapa_tipo') or '').strip()
                if tapa:
                    parts.append(f"Tapa: {tapa}")
                gar = (request.form.get('garantia') or '').strip()
                if gar:
                    parts.append(f"Garantia: {gar}")
                # battery explicit fields
                bv = (request.form.get('bateria_voltaje') or '').strip()
                ba = (request.form.get('bateria_amperaje') or '').strip()
                bc = (request.form.get('bateria_celdas') or '').strip()
                bm = (request.form.get('bateria_marca') or '').strip()
                bap = (request.form.get('bateria_aplicacion') or '').strip()
                if bv:
                    parts.append(f"Voltaje: {bv}")
                if ba:
                    parts.append(f"Amperaje: {ba}")
                if bc:
                    parts.append(f"Cantidad de celdas: {bc}")
                if bm:
                    parts.append(f"Marca: {bm}")
                if bap:
                    parts.append(f"Aplicacion: {bap}")
                car_serial = '; '.join(parts) if parts else None

            ot_kwargs = dict(
                category_id=selected_cat.id if selected_cat else None,
                categoria=legacy_categoria,
                estado_equipo=None,  # Field is now nullable, no enum validation
                caracteristicas_articulo=car_serial,
                # explicit bateria fields (optional)
                bateria_voltaje=bv or None,
                bateria_amperaje=ba or None,
                bateria_celdas=bc or None,
                bateria_marca=bm or None,
                bateria_aplicacion=bap or None,
                # service lifecycle state default
                estado='pendiente',
                referencia=form.referencia.data.strip() if form.referencia.data else "",
                repuestos_usados=form.repuestos_usados.data.strip() if hasattr(form, 'repuestos_usados') and form.repuestos_usados.data else None,
                descripcion=form.descripcion.data.strip() if form.descripcion.data else "",
                # ensure Python-side timestamp is set immediately for the new object
                fecha_creacion=get_local_now(),
                marca=form.marca.data.strip() if hasattr(form, 'marca') and form.marca.data else None,
                client_id=client.id if client else None,
                branch_id=branch.id if branch else None,
                tecnico_id=form.tecnico_id.data if form.tecnico_id.data else current_user.id,  # Si no se especifica, usar el creador
                responsable_nombre=form.responsable.data.strip() if form.responsable.data else None,
            )
            # Para evitar el error NOT NULL en consecutivo al hacer flush, asignamos un valor temporal
            ot_kwargs['consecutivo'] = f"TEMP-{uuid.uuid4().hex}"
            # Agregar el usuario que crea la orden
            ot_kwargs['created_by_id'] = current_user.id

            nueva_ot = OrdenTrabajo(**ot_kwargs)

            db.session.add(nueva_ot)
            db.session.flush()  # Para obtener nueva_ot.id antes del commit

            # Asignar tecnico_id ANTES de generar consecutivo
            articulos_json_str = request.form.get('articulos_json', '').strip()
            if articulos_json_str:
                try:
                    articulos = json.loads(articulos_json_str)
                    if articulos and len(articulos) > 0:
                        primer_articulo = articulos[0]
                        if 'sitio_reparacion_id' in primer_articulo and primer_articulo['sitio_reparacion_id']:
                            nueva_ot.tecnico_id = int(primer_articulo['sitio_reparacion_id'])
                except Exception as e:
                    # Si falla, mantener el tecnico_id ya asignado (current_user.id)
                    pass

            nueva_ot.consecutivo = nueva_ot.generar_consecutivo()

            # Guardar productos agregados
            # Primero intentar procesar articulos_json (nuevo sistema de carrito)
            articulos_json_str = request.form.get('articulos_json', '').strip()
            productos_validos = 0
            
            if articulos_json_str:
                # Save the JSON to the order for later display grouped by articles
                nueva_ot.articulos_json = articulos_json_str
                
                try:
                    articulos = json.loads(articulos_json_str)
                    print(f"[DEBUG] Procesando {len(articulos)} artículos del JSON")
                    
                    for articulo in articulos:
                        # Cada artículo tiene: tipo, marca, referencia, descripcion, valor, productos[]
                        productos_articulo = articulo.get('productos', [])
                        print(f"[DEBUG] Artículo con {len(productos_articulo)} productos")
                        
                        for prod in productos_articulo:
                            # Cada producto tiene: sku, nombreCustom, cantidad, descuento, precio
                            try:
                                # Buscar el producto por SKU para obtener el producto_id
                                from models.models import Product
                                # El SKU puede incluir el nombre, extraer solo el SKU entre paréntesis
                                sku_completo = prod.get('sku', '')
                                nombreCustom = prod.get('nombreCustom', '').strip()
                                # Intentar extraer SKU entre paréntesis, ej: "BATERÍA RELOJ (BATT-001)"
                                import re
                                match = re.search(r'\(([^)]+)\)', sku_completo)
                                if match:
                                    sku = match.group(1)
                                else:
                                    sku = sku_completo
                                
                                producto_bd = Product.query.filter_by(sku=sku).first()
                                
                                if producto_bd:
                                    cantidad = int(prod.get('cantidad', 1))
                                    precio = float(prod.get('precio', 0))
                                    
                                    # Usar nombre personalizado si existe, sino usar nombre del producto de BD
                                    nombre_final = nombreCustom if nombreCustom else producto_bd.nombre
                                    
                                    producto_orden = ProductoOrden(
                                        producto_id=producto_bd.id,
                                        cantidad=cantidad,
                                        precio_unitario=precio,
                                        nombre_producto=nombre_final,
                                        orden=nueva_ot
                                    )
                                    db.session.add(producto_orden)
                                    productos_validos += 1
                                    print(f"[DEBUG] Producto agregado: {sku} x{cantidad} ${precio} (nombre: {nombre_final})")
                                else:
                                    print(f"[WARNING] Producto no encontrado en BD: {sku}")
                            except Exception as err:
                                print(f"[ERROR] Error procesando producto: {err}")
                                continue
                                
                except json.JSONDecodeError as e:
                    print(f"[ERROR] Error parseando articulos_json: {e}")
                except Exception as e:
                    print(f"[ERROR] Error general procesando articulos_json: {e}")
            
            # Si no hay productos del JSON, intentar el método antiguo
            if productos_validos == 0:
                print("[DEBUG] No hay productos del JSON, intentando método antiguo...")
                i = 0
                while True:
                    producto_id = request.form.get(f"producto_id_{i}")
                    cantidad = request.form.get(f"cantidad_{i}")
                    precio_unitario = request.form.get(f"precio_unitario_{i}")
                    nombre_personalizado = request.form.get(f"nombre_producto_{i}", "").strip()
                    if not producto_id:
                        break
                    try:
                        producto_orden = ProductoOrden(
                            producto_id=int(producto_id),
                            cantidad=max(1, int(cantidad)),
                            precio_unitario=max(0, int(round(float(precio_unitario)))),
                            nombre_producto=nombre_personalizado if nombre_personalizado else None,
                            orden=nueva_ot
                        )
                        db.session.add(producto_orden)
                        productos_validos += 1
                    except Exception as err:
                        print(f"Producto invalido en posicion {i}: {err}")
                    i += 1

            if productos_validos == 0:
                db.session.rollback()
                flash("Debes agregar al menos un producto valido a la orden.", "danger")
                return redirect(url_for("ordenes.crear_orden"))

            if hasattr(form, 'anticipo_monto') and hasattr(form, 'anticipo_metodo') and form.anticipo_monto.data and form.anticipo_metodo.data:
                # Validar que para tarjeta o transferencia se haya proporcionado número de factura Siigo
                metodo_pago = form.anticipo_metodo.data.lower()
                numero_factura_siigo = request.form.get('numero_factura_siigo', '').strip()
                
                if metodo_pago in ('tarjeta', 'transferencia') and not numero_factura_siigo:
                    db.session.rollback()
                    flash("El Número de Factura Siigo es obligatorio para pagos con tarjeta o transferencia.", "danger")
                    return render_template("ordenes_trabajo/crear.html", form=form, Client=Client, branch_nombre=branch_nombre)
                
                # Validate anticipo against estimated total to avoid overpayments
                try:
                    est_total = 0
                    if nueva_ot.productos:
                        est_total = sum((p.cantidad * float(p.precio_unitario)) for p in nueva_ot.productos)
                except Exception:
                    est_total = None

                total_anticipos = 0
                try:
                    total_anticipos = sum(a.monto for a in (getattr(nueva_ot, 'anticipos') or []))
                except Exception:
                    total_anticipos = 0

                saldo_restante = None
                if est_total is not None:
                    saldo_restante = float(est_total) - float(total_anticipos)

                if saldo_restante is not None and form.anticipo_monto.data > saldo_restante:
                    # Ignore adding and show message
                    flash(f"El anticipo ({form.anticipo_monto.data}) es mayor al saldo estimado ({saldo_restante}). No se registro el anticipo.", 'warning')
                else:
                    # Obtener caja_tramite y numero_factura_siigo del formulario
                    caja_tramite = request.form.get('anticipo_caja_tramite', 'appot').strip()
                    numero_factura_siigo = request.form.get('anticipo_numero_factura_siigo', '').strip() or None
                    
                    # VERIFICACIÓN: Asegurar que tarjeta/transferencia siempre vayan a Siigo
                    metodo_lower = (form.anticipo_metodo.data or '').lower()
                    if metodo_lower in ('tarjeta', 'transferencia'):
                        caja_tramite = 'siigo'
                    elif metodo_lower == 'efectivo':
                        caja_tramite = 'appot'
                    
                    # Normalizar método de pago a minúsculas
                    metodo_normalizado = metodo_lower if metodo_lower else 'efectivo'
                    
                    anticipo = Anticipo(
                        monto=form.anticipo_monto.data,
                        metodo_pago=metodo_normalizado,
                        orden_id=nueva_ot.id,
                        registrado_por_id=current_user.id,
                        caja_tramite=caja_tramite,
                        numero_factura_siigo=numero_factura_siigo,
                        branch_id=nueva_ot.branch_id
                    )
                    db.session.add(anticipo)

            # Sincronizar productos desde articulos_json a productos_orden
            sincronizar_productos_desde_json(nueva_ot)

            db.session.commit()
            flash("Orden de trabajo creada con exito", "success")
            # Redirigir a ver la orden creada (con opción de imprimir)
            return redirect(url_for("ordenes.ver_orden", orden_id=nueva_ot.id, created=1))

        except Exception as e:
            db.session.rollback()
            import traceback
            error_trace = traceback.format_exc()
            print(f"[ERROR] Stack trace completo:\n{error_trace}")
            flash(f"Error al guardar la orden: {e}", "danger")
            print(f"Error tecnico: {e}")
        

    branch_nombre = None
    if current_user.is_authenticated and current_user.branch_id:
        from models.models import Branch
        branch = Branch.query.get(current_user.branch_id)
        branch_nombre = branch.nombre if branch else None
    # Generate idempotency key for the form
    key = str(uuid.uuid4())
    # Pasar sitios de reparación para el modal de artículos
    sitios_reparacion = [(u.id, u.username or u.email) for u in sorted(tecnicos, key=lambda x: x.username)]
    return render_template("ordenes_trabajo/crear.html", form=form, Client=Client, branch_nombre=branch_nombre, key=key, sitios_reparacion=sitios_reparacion)

@ordenes_bp.route("/buscar_cliente", methods=["POST"])
@login_required
def buscar_cliente():
    q = request.form.get("cc_or_nit", "").strip()
    client = None
    if q:
        # 0) Si viene en formato "Nombre (123)" o incluye un (ID), resolver por ID
        m = re.search(r"\((\d+)\)", q)
        if m:
            try:
                client = Client.query.get(int(m.group(1)))
            except Exception:
                client = None
        # 1) Intentar por CC o NIT exacto (permitiendo espacios)
        if not client:
            compact = q.replace(" ", "")
            client = Client.query.filter((Client.cc == compact) | (Client.nit == compact)).first()
        # 2) Intentar por ID numerico puro
        if not client and q.isdigit():
            client = Client.query.get(int(q))
        # 3) Intentar por nombre parcial (quitando cualquier "(algo)")
        if not client:
            nombre_only = re.sub(r"\(.*?\)", "", q).strip()
            if nombre_only:
                client = Client.query.filter(Client.nombre.ilike(f"%{nombre_only}%")).order_by(Client.id.desc()).first()
    if client:
        return jsonify({"id": client.id, "nombre": client.nombre, "correo": client.correo, "telefono": client.telefono})
    return jsonify({"error": "Cliente no encontrado"}), 404


@ordenes_bp.route('/buscar_para_venta')
@login_required
def buscar_para_venta():
    """Endpoint JSON para buscar ordenes que pueden ser facturadas.
    SEGURIDAD: Solo devuelve OTs de la sucursal activa del usuario.
    Parametro q: texto que puede ser parte del nombre del cliente, documento (cc/nit), consecutivo o id.
    Devuelve lista de ordenes con cliente y productos.
    """
    q = request.args.get('q', '').strip()
    if not q:
        return jsonify([])

    # VALIDACIÓN DE SEGURIDAD: Obtener sucursal activa del usuario
    branch_id = session.get("branch_id")
    if not branch_id:
        current_app.logger.warning(f"Usuario {current_user.id} intenta buscar OT sin sucursal activa")
        return jsonify({"error": "No hay sucursal activa. Selecciona una sucursal primero."}), 400

    # Buscar por consecutivo exacto o parcial
    query = OrdenTrabajo.query.join(Client)
    
    # SEGURIDAD: Filtrar SOLO ordenes de la sucursal activa
    query = query.filter(OrdenTrabajo.branch_id == branch_id)
    
    filters = []
    try:
        if q.isdigit():
            filters.append(OrdenTrabajo.id == int(q))
    except Exception:
        pass
    filters.append(OrdenTrabajo.consecutivo.ilike(f"%{q}%"))
    filters.append(Client.nombre.ilike(f"%{q}%"))
    filters.append(Client.cc.ilike(f"%{q}%"))
    filters.append(Client.nit.ilike(f"%{q}%"))

    # Mostrar todas las ordenes (cualquier estado) para que el usuario vea el badge de estado
    # La validacion de que solo se facturen las finalizadas se hace en el frontend
    results = query.filter(db.or_(*filters))
    try:
        # Exclude those that already have a linked Venta (facturadas)
        # Using an outer join against Venta to filter those without a match
        from models.models import Venta as _Venta
        results = results.outerjoin(_Venta, _Venta.orden_id == OrdenTrabajo.id).filter(_Venta.orden_id == None)
    except Exception:
        # Fallback: if any issue, keep original result set
        pass
    results = results.order_by(OrdenTrabajo.fecha_creacion.desc()).limit(20).all()
    out = []
    for ot in results:
        # Sincronizar productos si productos_orden está vacío pero articulos_json tiene datos
        if ot.articulos_json and (not ot.productos or len(ot.productos) == 0):
            try:
                sincronizar_productos_desde_json(ot)
                db.session.commit()
            except Exception as e:
                print(f"[ERROR] No se pudieron sincronizar productos para OT {ot.id}: {e}")
                db.session.rollback()
        
        # Determinar el documento (cc o nit)
        documento = ot.client.cc if ot.client.cc else (ot.client.nit if ot.client.nit else None)
        
        # --- PATCH: If ot.productos is empty, try to parse articulos_json for products ---
        productos_list = []
        if ot.productos and len(ot.productos) > 0:
            for p in ot.productos:
                productos_list.append({
                    'producto_id': p.producto.id if p.producto else None,
                    'nombre': p.producto.nombre if p.producto else (p.nombre_producto or 'PRODUCTO'),
                    'nombre_producto': p.nombre_producto,  # Nombre personalizado si existe
                    'cantidad': p.cantidad,
                    'precio_unitario': int(round(float(p.precio_unitario)))
                })
        else:
            # Refuerzo: parsear articulos_json y mapear todos los productos internos correctamente
            import json
            try:
                articulos = json.loads(ot.articulos_json) if ot.articulos_json else []
                for articulo in articulos:
                    productos_articulo = articulo.get('productos', [])
                    for prod in productos_articulo:
                        # Mapeo robusto de campos
                        producto_id = prod.get('producto_id') or prod.get('id') or None
                        nombre = prod.get('nombre') or prod.get('nombreCustom') or prod.get('nombre_producto') or 'PRODUCTO'
                        nombre_producto = prod.get('nombreCustom') or prod.get('nombre') or prod.get('nombre_producto') or 'PRODUCTO'
                        cantidad = prod.get('cantidad') or prod.get('qty') or 1
                        precio = prod.get('precio_unitario') or prod.get('precio') or prod.get('valor') or 0
                        try:
                            cantidad = int(cantidad)
                        except Exception:
                            cantidad = 1
                        try:
                            precio = int(round(float(precio)))
                        except Exception:
                            precio = 0
                        productos_list.append({
                            'producto_id': producto_id,
                            'nombre': nombre,
                            'nombre_producto': nombre_producto,
                            'cantidad': cantidad,
                            'precio_unitario': precio
                        })
            except Exception as e:
                print(f"[ERROR] No se pudo parsear articulos_json para OT {ot.id}: {e}")

        out.append({
            'id': ot.id,
            'consecutivo': ot.consecutivo,
            'cliente': {
                'id': ot.client.id,
                'nombre': ot.client.nombre,
                'documento': documento,
                'correo': ot.client.correo,
                'telefono': ot.client.telefono
            },
            'productos': productos_list,
            'anticipos': [
                {
                    'id': a.id,
                    'monto': int(round(float(a.monto))),
                    'metodo_pago': a.metodo_pago,
                    'fecha': a.fecha.isoformat() if getattr(a, 'fecha', None) else None,
                    'registrado_por': (a.registrado_por.username if getattr(a, 'registrado_por', None) and getattr(a.registrado_por, 'username', None) else (a.registrado_por.email if getattr(a, 'registrado_por', None) else None))
                } for a in ot.anticipos
            ],
            'entregado': bool(ot.entregado),
            'estado': ot.estado,
        })
    return jsonify(out)

@ordenes_bp.route('/ver/<int:orden_id>')
@login_required
def ver_orden(orden_id):
    orden = OrdenTrabajo.query.get_or_404(orden_id)
    # Anti-IDOR: solo la sucursal duena (admin/supervisor global)
    denied = require_branch_access(orden.branch_id)
    if denied:
        return denied
    # Guardar la página anterior en session para el botón volver
    if request.referrer and not request.referrer.endswith(f'/ver/{orden_id}'):
        session['previous_page'] = request.referrer
    
    # Cargar todos los sitios de reparación (usuarios técnicos)
    sitios_dict = {u.id: u.username for u in User.query.filter_by(es_sitio_reparacion=True).all()}
    
    # Cargar repuestos instalados
    repuestos = []
    total_repuestos = 0
    try:
        if hasattr(orden, 'repuestos_instalados') and orden.repuestos_instalados:
            repuestos = orden.repuestos_instalados.all()
            total_repuestos = sum(float(r.costo_total or 0) for r in repuestos)
    except:
        pass
    
    return render_template("ordenes/ver.html", orden=orden, sitios_dict=sitios_dict, 
                         repuestos=repuestos, total_repuestos=total_repuestos)


@ordenes_bp.route('/ticket/<int:orden_id>')
@login_required
def ticket_orden(orden_id):
    orden = OrdenTrabajo.query.get_or_404(orden_id)
    # Anti-IDOR: el ticket expone datos del cliente y la sucursal duena
    denied = require_branch_access(orden.branch_id)
    if denied:
        return denied
    # Verificar si es la primera impresion
    primera_impresion = not orden.impreso
    print(f"DEBUG: Orden {orden.consecutivo} - impreso={orden.impreso}, primera_impresion={primera_impresion}")
    # Marcar como impreso despues de verificar
    if not orden.impreso:
        orden.impreso = True
        db.session.commit()
        print(f"DEBUG: Orden marcada como impresa")
    
    # Cargar configuracion de impresion de OT desde archivo independiente
    ot_cfg = {
        'ticket_width': '80',
        'font_size': 14,
        'show_company': True,
        'include_address': True,
        'auto_print': True,
        'header_text': 'ORDEN DE TRABAJO',
        'footer_text': 'Gracias por confiar en nuestro servicio',
        'show_signatures': True,
        'copies_on_first_print': 2
    }
    try:
        config_path = os.path.join(os.getcwd(), 'instance', 'ot_formats.json')
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                cfg_data = json.load(f)
            # Usar configuracion de la sucursal si existe, sino default
            branch_key = f'branch_{orden.sucursal_id}' if orden.sucursal_id else 'default'
            if branch_key in cfg_data:
                ot_cfg.update(cfg_data[branch_key])
            elif 'default' in cfg_data:
                ot_cfg.update(cfg_data['default'])
    except Exception as e:
        print(f"Error al cargar ot_formats.json: {e}")
    
    # Cargar todos los sitios de reparación (usuarios técnicos)
    sitios_dict = {u.id: u.username for u in User.query.filter_by(es_sitio_reparacion=True).all()}
    
    # Optionally restrict to vendedores or allow broader access depending on policy
    return render_template('ordenes/pos_ticket.html', orden=orden, primera_impresion=primera_impresion, ot_cfg=ot_cfg, sitios_dict=sitios_dict)


@ordenes_bp.route('/actualizar_estado/<int:orden_id>', methods=['POST'])
@login_required
@role_required('admin', 'supervisor', 'tecnico', 'vendedor')
def actualizar_estado(orden_id):
    orden = OrdenTrabajo.query.get_or_404(orden_id)
    # Anti-IDOR: solo la sucursal duena (admin/supervisor global)
    denied = require_branch_access(orden.branch_id)
    if denied:
        return denied

    # Los técnicos pueden actualizar el estado de todas las OT (sin restricción de asignación)
    # Los vendedores solo pueden actualizar si están asignados como sitio de reparación
    if current_user.rol == 'vendedor' and orden.tecnico_id != current_user.id:
        flash('Solo puedes cambiar el estado de ordenes asignadas a tu sitio de reparacion.', 'danger')
        return redirect(url_for('ordenes.ver_orden', orden_id=orden.id))

    # Validar que el consecutivo enviado coincida con la orden (proteccion adicional)
    posted_cons = (request.form.get('consecutivo') or '').strip()
    if posted_cons and posted_cons != (orden.consecutivo or ''):
        flash('Consecutivo invalido. Operacion abortada.', 'danger')
        return redirect(url_for('ordenes.ver_orden', orden_id=orden.id))

    estado = request.form.get('estado_servicio')
    try:
        if estado == 'finalizado':
            orden.entregado = True
            orden.fecha_entrega = get_local_now()
            orden.estado = 'finalizado'
        elif estado == 'en_proceso':
            orden.entregado = False
            orden.fecha_entrega = None
            orden.estado = 'en_proceso'
        elif estado == 'pendiente':
            orden.entregado = False
            orden.fecha_entrega = None
            orden.estado = 'pendiente'

        db.session.commit()
        cons = orden.consecutivo or f"OT-{orden.id}"
        flash(f'Estado de la orden {cons} actualizado.', 'success')
        # Si la orden quedo finalizada, crear notificacion para el vendedor de la sucursal
        if estado == 'finalizado':
            try:
                # Notificar a todos los vendedores asignados a la sucursal que creo la orden
                vendedores = User.query.filter_by(branch_id=orden.branch_id, rol='vendedor').all()
                destinatarios = [v.id for v in vendedores]

                # fallback si no hay vendedores: intentar creador de la orden o el tecnico
                if not destinatarios:
                    if hasattr(orden, 'creado_por_id') and orden.creado_por_id:
                        destinatarios = [orden.creado_por_id]
                    elif orden.tecnico_id:
                        destinatarios = [orden.tecnico_id]

                if destinatarios:
                    msg = f"La orden {cons} ha sido marcada como finalizada."
                    link = url_for('ordenes.ver_orden', orden_id=orden.id)
                    # Crear una notificacion por destinatario (evitar duplicados con set)
                    for uid in set(destinatarios):
                        notif = Notification(user_id=uid, message=msg, link=link)
                        db.session.add(notif)
                    db.session.commit()
            except Exception:
                db.session.rollback()
    except Exception as e:
        db.session.rollback()
        flash(f'Error al actualizar el estado: {e}', 'danger')

    # Si la orden quedo finalizada, redirigir al listado de finalizadas
    if estado == 'finalizado':
        return redirect(url_for('ordenes.listar_finalizadas'))

    return redirect(url_for('ordenes.ver_orden', orden_id=orden.id))


@ordenes_bp.route('/sitios_reparacion', methods=['GET'])
@login_required
def listar_sitios_reparacion():
    # Devuelve una lista de sitios de reparacion (vendedores y tecnicos) para poblar selects dinamicos
    usuarios = User.query.filter(User.rol.in_(['vendedor', 'tecnico'])).order_by(User.username).all()
    data = [{'id': u.id, 'username': u.username or u.email} for u in usuarios]
    return jsonify(data)


@ordenes_bp.route('/editar/<int:orden_id>', methods=['GET', 'POST'])
@login_required
@role_required('admin', 'supervisor', 'tecnico', 'vendedor')
def editar_orden(orden_id):
    orden = OrdenTrabajo.query.get_or_404(orden_id)
    # Anti-IDOR: solo la sucursal duena (admin/supervisor global)
    denied = require_branch_access(orden.branch_id)
    if denied:
        return denied
    form = OrdenTrabajoForm(obj=orden)

    # Los técnicos pueden editar todas las OT (sin restricción de asignación)
    # Los vendedores solo pueden editar si están asignados como sitio de reparación
    if current_user.rol == 'vendedor' and orden.tecnico_id != current_user.id:
        flash('Solo puedes editar ordenes asignadas a tu sitio de reparacion.', 'danger')
        return redirect(url_for('ordenes.listar_ordenes'))

    # No permitir editar si la orden ya fue facturada (tiene una Venta vinculada)
    try:
        if getattr(orden, 'venta_rel', None) is not None:
            flash('La orden ya fue facturada y no puede editarse.', 'warning')
            return redirect(url_for('ordenes.ver_orden', orden_id=orden.id))
    except Exception:
        # En caso de fallo inesperado, continuar con precaucion (seguira aplicandose la comprobacion en plantilla)
        pass

    form = OrdenTrabajoForm(obj=orden)
    # Poblar choices de sitios de reparacion (vendedores y tecnicos)
    form.tecnico_id.choices = [(u.id, u.username or u.email) for u in User.query.filter(User.rol.in_(['vendedor', 'tecnico'])).order_by(User.username).all()]
    try:
        categorias = OTCategory.query.order_by(OTCategory.nombre.asc()).all()
        form.categoria.choices = [(c.id, c.nombre) for c in categorias]
    except Exception:
        form.categoria.choices = []
    # Preseleccionar la categoria guardada en la orden (si aplica)
    try:
        # Preferir category_id (FK) si esta presente
        if getattr(orden, 'category_id', None) is not None:
            try:
                cid = int(orden.category_id)
            except Exception:
                cid = None
            if cid is not None:
                # Asegurar que la opcion exista en choices; si no, intentar obtener nombre desde OTCategory
                has_choice = any((str(choice[0]) == str(cid) or choice[0] == cid) for choice in (form.categoria.choices or []))
                if not has_choice:
                    try:
                        cat = OTCategory.query.get(cid)
                        label = cat.nombre if cat and getattr(cat, 'nombre', None) else None
                    except Exception:
                        label = None
                    # fallback label desde legacy enum si existe
                    if not label and getattr(orden, 'categoria', None):
                        try:
                            label = orden.categoria.value if hasattr(orden.categoria, 'value') else str(orden.categoria)
                        except Exception:
                            label = str(orden.categoria)
                    if not label:
                        label = f"Categoria {cid}"
                    # append as int id
                    try:
                        form.categoria.choices = list(form.categoria.choices or []) + [(cid, label)]
                    except Exception:
                        # ensure it's a list of tuples
                        form.categoria.choices = [(cid, label)]
                # finalmente asignar el valor (coerce a int para WTForms)
                try:
                    form.categoria.data = int(cid)
                except Exception:
                    form.categoria.data = cid
        # Si no hay FK, intentar mapear desde el enum legacy
        elif getattr(orden, 'categoria', None):
            try:
                legacy_name = orden.categoria.value if hasattr(orden.categoria, 'value') else str(orden.categoria)
            except Exception:
                legacy_name = str(orden.categoria)
            legacy_name = (legacy_name or '').strip()
            if legacy_name:
                found = OTCategory.query.filter(OTCategory.nombre.ilike(legacy_name)).first()
                if not found:
                    found = OTCategory.query.filter(OTCategory.nombre.ilike(f"%{legacy_name}%")).first()
                if found:
                    try:
                        form.categoria.data = int(found.id)
                    except Exception:
                        form.categoria.data = found.id
    except Exception:
        pass
    # estado_equipo field was removed from form - no longer needed

    # Helper to detect AJAX requests
    def is_ajax():
        return request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    if form.validate_on_submit():
        print(f"DEBUG: Formulario validado correctamente")
        try:
            # Actualizar campos editables
            # Update category FK (no longer update legacy enum field to avoid type conflicts)
            selected_cat = OTCategory.query.get(form.categoria.data)
            orden.category_id = selected_cat.id if selected_cat else None
            # Ya no se valida ni se asigna EstadoOrden
            orden.referencia = form.referencia.data.strip() if form.referencia.data else ''
            orden.repuestos_usados = form.repuestos_usados.data.strip() if hasattr(form, 'repuestos_usados') and form.repuestos_usados.data else None
            orden.descripcion = form.descripcion.data.strip() if form.descripcion.data else ''
            orden.marca = form.marca.data.strip() if hasattr(form, 'marca') and form.marca.data else None
            # Caracteristicas del articulo (serializado desde checkboxes)
            try:
                car_serial = request.form.get('caracteristicas_articulo')
                if not car_serial or not car_serial.strip():
                    parts = []
                    for v in request.form.getlist('caracteristicas'):
                        if v and v.strip():
                            parts.append(v.strip())
                    eslab = (request.form.get('eslabones_numero') or '').strip()
                    if eslab:
                        parts.append(f"Eslabones: {eslab}")
                    tapa = (request.form.get('tapa_tipo') or '').strip()
                    if tapa:
                        parts.append(f"Tapa: {tapa}")
                    gar = (request.form.get('garantia') or '').strip()
                    if gar:
                        parts.append(f"Garantia: {gar}")
                    bv = (request.form.get('bateria_voltaje') or '').strip()
                    ba = (request.form.get('bateria_amperaje') or '').strip()
                    bc = (request.form.get('bateria_celdas') or '').strip()
                    bm = (request.form.get('bateria_marca') or '').strip()
                    bap = (request.form.get('bateria_aplicacion') or '').strip()
                    if bv:
                        parts.append(f"Voltaje: {bv}")
                    if ba:
                        parts.append(f"Amperaje: {ba}")
                    if bc:
                        parts.append(f"Cantidad de celdas: {bc}")
                    if bm:
                        parts.append(f"Marca: {bm}")
                    if bap:
                        parts.append(f"Aplicacion: {bap}")
                    car_serial = '; '.join(parts) if parts else None
                orden.caracteristicas_articulo = car_serial or None
            except Exception:
                pass
            # Update explicit bateria fields if provided (keep existing if absent)
            try:
                if 'bateria_voltaje' in request.form:
                    orden.bateria_voltaje = request.form.get('bateria_voltaje') or None
                if 'bateria_amperaje' in request.form:
                    orden.bateria_amperaje = request.form.get('bateria_amperaje') or None
                if 'bateria_celdas' in request.form:
                    orden.bateria_celdas = request.form.get('bateria_celdas') or None
                if 'bateria_marca' in request.form:
                    orden.bateria_marca = request.form.get('bateria_marca') or None
                if 'bateria_aplicacion' in request.form:
                    orden.bateria_aplicacion = request.form.get('bateria_aplicacion') or None
            except Exception:
                pass
            orden.tecnico_id = form.tecnico_id.data
            
            # Procesar articulos_json (nuevo sistema de carrito con múltiples artículos)
            articulos_json_str = request.form.get('articulos_json', '').strip()
            
            if articulos_json_str:
                # Guardar el JSON en la orden
                orden.articulos_json = articulos_json_str
                
                # Eliminar todos los ProductoOrden existentes
                try:
                    ProductoOrden.query.filter_by(orden_id=orden.id).delete()
                except Exception as e:
                    print(f"Error eliminando productos existentes: {e}")
                
                # Procesar artículos del JSON
                try:
                    import json
                    articulos = json.loads(articulos_json_str)
                    
                    if articulos and isinstance(articulos, list):
                        for articulo in articulos:
                            productos = articulo.get('productos', [])
                            
                            for producto in productos:
                                try:
                                    # Buscar producto por SKU
                                    sku = producto.get('sku', '').strip()
                                    nombreCustom = producto.get('nombreCustom', '').strip()
                                    cantidad = int(producto.get('cantidad', 1))
                                    precio = float(producto.get('precio', 0))
                                    
                                    if not sku or cantidad <= 0 or precio < 0:
                                        continue
                                    
                                    # Extraer nombre del producto del SKU si tiene formato "Nombre (SKU)"
                                    nombre_producto = sku
                                    producto_id = None
                                    
                                    if '(' in sku and ')' in sku:
                                        nombre_producto = sku.split('(')[0].strip()
                                        sku_code = sku.split('(')[1].replace(')', '').strip()
                                        
                                        # Buscar producto por SKU
                                        from models.models import Product
                                        prod = Product.query.filter_by(sku=sku_code).first()
                                        if prod:
                                            producto_id = prod.id
                                            # Si no hay nombre personalizado, usar el del producto de BD
                                            if not nombreCustom:
                                                nombre_producto = prod.nombre
                                    
                                    # Si hay nombre personalizado, usarlo
                                    if nombreCustom:
                                        nombre_producto = nombreCustom
                                    
                                    # Si no se encontró por SKU, buscar por nombre
                                    if not producto_id:
                                        from models.models import Product
                                        prod = Product.query.filter_by(nombre=nombre_producto).first()
                                        if prod:
                                            producto_id = prod.id
                                    
                                    # Si aún no se encontró, crear un producto genérico
                                    if not producto_id:
                                        # Buscar o crear un producto "SERVICIO GENERICO"
                                        from models.models import Product
                                        prod_generico = Product.query.filter_by(sku='GENERICO').first()
                                        if not prod_generico:
                                            prod_generico = Product(
                                                nombre='SERVICIO GENERICO',
                                                sku='GENERICO',
                                                precio=0,
                                                stock=999999
                                            )
                                            db.session.add(prod_generico)
                                            db.session.flush()
                                        producto_id = prod_generico.id
                                    
                                    # Crear ProductoOrden
                                    po = ProductoOrden(
                                        producto_id=producto_id,
                                        cantidad=cantidad,
                                        precio_unitario=precio,
                                        orden=orden,
                                        nombre_producto=nombre_producto
                                    )
                                    db.session.add(po)
                                    
                                except Exception as e:
                                    print(f"Error procesando producto del artículo: {e}")
                                    continue
                    
                except Exception as e:
                    print(f"Error procesando articulos_json en edición: {e}")
            
            # Fallback: Procesar productos en formato legacy si no hay articulos_json
            elif request.form.get('producto_id_0'):
                try:
                    # Recolectar ids enviados para detectar eliminaciones
                    enviado_ids = []
                    i = 0
                    productos_validos = 0
                    while True:
                        prod_id = request.form.get(f"producto_id_{i}")
                        if not prod_id:
                            break
                        cant = request.form.get(f"cantidad_{i}")
                        precio = request.form.get(f"precio_unitario_{i}")
                        nombre_personalizado = request.form.get(f"nombre_producto_{i}", "").strip()
                        prod_orden_id = request.form.get(f"producto_orden_id_{i}")
                        try:
                            cantidad_val = max(1, int(cant))
                            precio_val = max(0, int(round(float(precio))))
                        except Exception:
                            print(f"Producto con datos invalidos en posicion {i}")
                            i += 1
                            continue

                        if prod_orden_id:
                            # Intentar actualizar existente
                            try:
                                po = ProductoOrden.query.filter_by(id=int(prod_orden_id), orden_id=orden.id).first()
                                if po:
                                    po.producto_id = int(prod_id)
                                    po.cantidad = cantidad_val
                                    po.precio_unitario = precio_val
                                    po.nombre_producto = nombre_personalizado if nombre_personalizado else None
                                    db.session.add(po)
                                    enviado_ids.append(po.id)
                                    productos_validos += 1
                                else:
                                    # ID no encontrada: crear nueva fila
                                    po_new = ProductoOrden(
                                        producto_id=int(prod_id), 
                                        cantidad=cantidad_val, 
                                        precio_unitario=precio_val, 
                                        orden=orden,
                                        nombre_producto=nombre_personalizado if nombre_personalizado else None
                                    )
                                    db.session.add(po_new)
                                    db.session.flush()
                                    enviado_ids.append(po_new.id)
                                    productos_validos += 1
                            except Exception as err:
                                print(f"Error actualizando producto_orden id={prod_orden_id}: {err}")
                        else:
                            # Crear nuevo detalle
                            try:
                                po_new = ProductoOrden(
                                    producto_id=int(prod_id), 
                                    cantidad=cantidad_val, 
                                    precio_unitario=precio_val, 
                                    orden=orden,
                                    nombre_producto=nombre_personalizado if nombre_personalizado else None
                                )
                                db.session.add(po_new)
                                db.session.flush()
                                enviado_ids.append(po_new.id)
                                productos_validos += 1
                            except Exception as err:
                                print(f"Error creando producto en posicion {i}: {err}")
                        i += 1

                    if productos_validos == 0:
                        db.session.rollback()
                        flash('Debes enviar al menos un producto valido al editar la orden.', 'danger')
                        return redirect(url_for('ordenes.editar_orden', orden_id=orden.id))

                    # Eliminar los ProductoOrden que pertenecen a la orden pero que no fueron reenviados
                    try:
                        actuales = ProductoOrden.query.filter_by(orden_id=orden.id).all()
                        for a in actuales:
                            if a.id not in enviado_ids:
                                db.session.delete(a)
                    except Exception as err:
                        print(f"Error al eliminar productos no enviados: {err}")
                except Exception as e:
                    db.session.rollback()
                    flash(f'Error al procesar productos: {e}', 'danger')
                    return redirect(url_for('ordenes.editar_orden', orden_id=orden.id))

            # Procesar anticipos desde JSON (nuevo formato con múltiples anticipos)
            anticipos_json = request.form.get('anticipos_json')
            
            if anticipos_json:
                try:
                    import json
                    anticipos_data = json.loads(anticipos_json)
                    
                    if isinstance(anticipos_data, list):
                        existing_ids = set()
                        for ant_data in anticipos_data:
                            try:
                                ant_id = ant_data.get('id')
                                if ant_id and str(ant_id).isdigit():
                                    existing_ids.add(int(ant_id))
                            except Exception:
                                pass
                        
                        # Eliminar solo anticipos que NO vienen en el JSON
                        Anticipo.query.filter(
                            Anticipo.orden_id == orden.id,
                            ~Anticipo.id.in_(existing_ids) if existing_ids else True
                        ).delete(synchronize_session=False) if not existing_ids else Anticipo.query.filter(
                            Anticipo.orden_id == orden.id,
                            ~Anticipo.id.in_(existing_ids)
                        ).delete(synchronize_session=False)
                        
                        # Crear o actualizar anticipos del JSON
                        for ant_data in anticipos_data:
                            try:
                                ant_id = ant_data.get('id')
                                monto_val = float(ant_data.get('monto', 0))
                                metodo = ant_data.get('metodo', '').strip()
                                numero_factura = ant_data.get('numero_factura_siigo', '').strip()
                                
                                if monto_val <= 0 or not metodo:
                                    continue
                                
                                metodo_lower = metodo.lower()
                                caja_tramite = 'siigo' if metodo_lower in ('tarjeta', 'transferencia') else 'appot'
                                
                                if ant_id and str(ant_id).isdigit():
                                    anticipo = Anticipo.query.get(int(ant_id))
                                    if anticipo and anticipo.orden_id == orden.id and anticipo.venta_id is None:
                                        anticipo.monto = monto_val
                                        anticipo.metodo_pago = metodo_lower
                                        anticipo.caja_tramite = caja_tramite
                                        anticipo.numero_factura_siigo = numero_factura if numero_factura else None
                                    else:
                                        # Anticipo no encontrado, de otra orden o ya consumido por una venta:
                                        # NO crear duplicado, solo registrar en log.
                                        current_app.logger.warning(f"Anticipo id={ant_id} no actualizable (orden={orden.id}, venta consumida o inexistente). Se omite para evitar duplicado.")
                                else:
                                    anticipo_branch_id = current_user.branch_id if current_user.branch_id else orden.branch_id
                                    anticipo = Anticipo(
                                        monto=monto_val, metodo_pago=metodo_lower,
                                        orden_id=orden.id, registrado_por_id=current_user.id,
                                        caja_tramite=caja_tramite,
                                        numero_factura_siigo=numero_factura if numero_factura else None,
                                        branch_id=anticipo_branch_id
                                    )
                                    db.session.add(anticipo)
                            except Exception as e:
                                current_app.logger.error(f"Error procesando anticipo desde JSON: {e}")
                    
                except Exception as e:
                    current_app.logger.error(f"Error procesando anticipos_json: {e}")
            
            # Fallback: Procesar anticipo individual (formato legacy)
            elif request.form.get('anticipo_monto') and request.form.get('anticipo_metodo'):
                anticipo_monto = request.form.get('anticipo_monto')
                anticipo_metodo = request.form.get('anticipo_metodo')
                anticipo_caja_tramite = request.form.get('anticipo_caja_tramite', 'appot')
                anticipo_numero_factura_siigo = request.form.get('anticipo_numero_factura_siigo')
                try:
                    monto_val = float(anticipo_monto)
                    est_total = sum((p.cantidad * float(p.precio_unitario)) for p in orden.productos) if orden.productos else 0
                    total_anticipos_existentes = sum(a.monto for a in orden.anticipos) if orden.anticipos else 0
                    saldo_restante = est_total - total_anticipos_existentes
                    if monto_val > saldo_restante:
                        flash(f"El anticipo ({monto_val}) es mayor al saldo estimado ({saldo_restante}). No se registró el anticipo.", 'warning')
                    else:
                        metodo_lower = (anticipo_metodo or '').lower()
                        if metodo_lower in ('tarjeta', 'transferencia'):
                            anticipo_caja_tramite = 'siigo'
                        elif metodo_lower == 'efectivo':
                            anticipo_caja_tramite = 'appot'
                        metodo_normalizado = metodo_lower if metodo_lower else 'efectivo'
                        anticipo_branch_id = current_user.branch_id if current_user.branch_id else orden.branch_id
                        anticipo = Anticipo(
                            monto=monto_val, metodo_pago=metodo_normalizado,
                            orden_id=orden.id, registrado_por_id=current_user.id,
                            caja_tramite=anticipo_caja_tramite,
                            numero_factura_siigo=anticipo_numero_factura_siigo or None,
                            branch_id=anticipo_branch_id
                        )
                        db.session.add(anticipo)
                except Exception as e:
                    current_app.logger.error(f"Error creando anticipo en edición: {e}")

            db.session.commit()
            flash('Orden actualizada correctamente', 'success')
            
            # Return JSON for AJAX requests
            if is_ajax():
                return jsonify({
                    'success': True,
                    'message': 'Orden actualizada correctamente',
                    'redirect_url': url_for('ordenes.ver_orden', orden_id=orden.id)
                })
            
            return redirect(url_for('ordenes.ver_orden', orden_id=orden.id))
        except Exception as e:
            db.session.rollback()
            flash(f'Error al actualizar la orden: {e}', 'danger')
    else:
        print(f"DEBUG: Validación del formulario falló")
        print(f"DEBUG: Errores del formulario: {form.errors}")
        if request.method == 'POST':
            print(f"DEBUG: Datos del formulario recibidos")
            flash('Error de validación en el formulario. Revisa los campos requeridos.', 'danger')

    # Render form with errors if validation failed
    # compute totals for anticipos to show saldo
    try:
        total_anticipos = sum(a.monto for a in (getattr(orden, 'anticipos') or []))
    except Exception:
        total_anticipos = 0
    # assume orden has a total estimated cost? If not, we compute saldo as None
    saldo = None
    try:
        if hasattr(orden, 'productos') and orden.productos:
            est_total = sum((p.cantidad * p.precio_unitario) for p in orden.productos)
            saldo = float(est_total) - float(total_anticipos)
    except Exception:
        saldo = None
    
    # Cargar artículos de forma unificada: priorizar articulos_json, fallback a productos legacy.
    # Se entrega como objeto Python y la plantilla lo serializa con |tojson
    # (nunca |safe sobre texto crudo: evita breakout </script> = XSS almacenado).
    articulos_unificados = []
    try:
        import json
        # Intentar cargar desde articulos_json (sistema nuevo)
        if orden.articulos_json:
            try:
                articulos_unificados = json.loads(orden.articulos_json)
            except Exception:
                articulos_unificados = []
            print(f"DEBUG: Artículos cargados desde articulos_json")
        # Fallback: convertir productos legacy a formato JSON moderno
        elif orden.productos:
            articulos_legacy = []
            for p in orden.productos:
                # Construir SKU en formato "Nombre (SKU)"
                sku_display = p.nombre_producto or (p.producto.nombre if p.producto else "Producto")
                if p.producto and hasattr(p.producto, 'sku') and p.producto.sku:
                    sku_display = f"{sku_display} ({p.producto.sku})"
                
                producto_legacy = {
                    'sku': sku_display,
                    'nombreCustom': p.nombre_producto or '',
                    'cantidad': p.cantidad,
                    'precio': float(p.precio_unitario) if p.precio_unitario else 0,
                    'descuento': 0
                }
                articulos_legacy.append(producto_legacy)
            
            # Envolver en estructura de artículo con sitio de reparación
            articulo_wrapper = {
                'sitioReparacion': orden.tecnico_id or 0,
                'productos': articulos_legacy
            }
            articulos_unificados = [articulo_wrapper]
            print(f"DEBUG: Artículos convertidos desde productos legacy a JSON")
        else:
            articulos_unificados = []
            print(f"DEBUG: No hay artículos para cargar")
    except Exception as e:
        print(f"ERROR al cargar artículos unificados: {e}")
        articulos_unificados = []
    
    # Serializar anticipos existentes para el frontend
    anticipos_serialized = []
    if orden.anticipos:
        for ant in orden.anticipos:
            anticipo_dict = {
                'id': ant.id,
                'monto': float(ant.monto) if ant.monto else 0,
                'metodo': ant.metodo_pago or '',
                'numero_factura_siigo': ant.numero_factura_siigo or '',
                'caja_tramite': getattr(ant, 'caja_tramite', '')
            }
            anticipos_serialized.append(anticipo_dict)
    
    
    # Obtener sitios de reparación para el modal de artículos (igual que en crear_orden)
    sitios_reparacion_users = User.query.filter(User.es_sitio_reparacion == True).order_by(User.username).all()
    sitios_reparacion = [(u.id, u.username or u.email) for u in sitios_reparacion_users]
    
    # Calcular el total de servicios/artículos para la alerta de repuestos
    total_servicios = 0
    import json
    try:
        if orden.articulos_json:
            articulos = json.loads(orden.articulos_json)
            for articulo in articulos:
                total_servicios += float(articulo.get('valor', 0))
        elif orden.productos:
            for p in orden.productos:
                total_servicios += float(p.cantidad or 0) * float(p.precio_unitario or 0)
    except Exception as e:
        print(f"Error calculando total_servicios: {e}")
        total_servicios = 0

    return render_template('ordenes_trabajo/editar.html', form=form, orden=orden, Client=Client, total_anticipos=total_anticipos, saldo=saldo, articulos_unificados=articulos_unificados, anticipos_serialized=anticipos_serialized, sitios_reparacion=sitios_reparacion, total_servicios=total_servicios)

@ordenes_bp.route('/crear_orden', methods=['POST'])
@login_required
def crear_orden_modal():
    # Idempotency check
    idempotency_key = request.form.get('idempotency_key') or str(uuid.uuid4())
    processed_keys_list = session.setdefault('processed_ot_modal_keys', [])
    processed_keys = set(processed_keys_list)
    if idempotency_key in processed_keys:
        flash("Esta solicitud ya fue procesada. Evitando duplicados.", "warning")
        return redirect(url_for('sales.nueva'))
    # Reserve the key
    processed_keys.add(idempotency_key)
    session['processed_ot_modal_keys'] = list(processed_keys)
    session.modified = True

    cliente_nombre = request.form.get('cliente', '').strip()
    descripcion = request.form.get('descripcion', '').strip()
    responsable = request.form.get('responsable', '').strip()
    if not cliente_nombre or not descripcion:
        flash('Todos los campos son obligatorios', 'danger')
        return redirect(url_for('sales.nueva'))
    cliente = Client.query.filter_by(nombre=cliente_nombre).first()
    if not cliente:
        flash('Cliente no encontrado', 'danger')
        return redirect(url_for('sales.nueva'))
    
    # Verificar que el usuario tenga sucursal y tecnico asignado
    if not current_user.branch_id:
        flash('Tu usuario no tiene una sucursal asignada. Contacta al administrador.', 'danger')
        return redirect(url_for('sales.nueva'))
    
    orden = OrdenTrabajo(
        client_id=cliente.id, 
        descripcion=descripcion,
        created_by_id=current_user.id,
        branch_id=current_user.branch_id,
        tecnico_id=current_user.id,  # Se asigna el usuario actual como tecnico por defecto
        referencia="",
        responsable_nombre=responsable,
        consecutivo=f"TEMP-{uuid.uuid4().hex}"
    )
    try:
        db.session.add(orden)
        db.session.flush()  # Para obtener el ID
        orden.consecutivo = orden.generar_consecutivo()
        db.session.commit()
        flash('Orden de trabajo creada correctamente', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al guardar la orden: {e}', 'danger')
    return redirect(url_for('sales.nueva'))


# --- Repuestos instalados (endpoints JSON para la UI interna) ---
@ordenes_bp.route('/<int:orden_id>/repuestos', methods=['GET'])
@login_required
@role_required('admin', 'supervisor', 'tecnico', 'vendedor', 'bodega')
def listar_repuestos(orden_id):
    try:
        orden = OrdenTrabajo.query.get_or_404(orden_id)
        denied = require_branch_access(orden.branch_id)
        if denied:
            return denied
        items = []
        # Check if the table exists by trying to access repuestos_instalados
        try:
            repuestos = orden.repuestos_instalados.all() if hasattr(orden.repuestos_instalados, 'all') else list(orden.repuestos_instalados)
        except Exception as e:
            # Table might not exist yet (migration pending) - return empty list
            print(f"Warning: Could not load repuestos_instalados: {e}")
            return jsonify({'repuestos': []})
        
        for r in repuestos:
            items.append({
                'id': r.id,
                'orden_id': r.orden_id,
                'product_id': r.product_id,
                'nombre': r.nombre or (r.product.nombre if r.product else None),
                'cantidad': int(r.cantidad or 0),
                'costo_unitario': float(r.costo_unitario or 0),
                'costo_total': float(r.costo_total or 0),
                'registrado_por_id': r.registrado_por_id,
                'registrado_por': getattr(r.registrado_por, 'username', None) if getattr(r, 'registrado_por', None) else None,
                'fecha_instalacion': r.fecha_instalacion.isoformat() if r.fecha_instalacion else None,
                'notas_privadas': r.notas_privadas,
                'visible_para_cliente': bool(r.visible_para_cliente)
            })
        return jsonify({'repuestos': items})
    except Exception as e:
        print(f"Error in listar_repuestos: {e}")
        return jsonify({'error': str(e), 'repuestos': []}), 500


@ordenes_bp.route('/<int:orden_id>/repuestos', methods=['POST'])
@login_required
@role_required('admin', 'supervisor', 'tecnico', 'vendedor', 'bodega')
def crear_repuesto(orden_id):
    # Verificar si la tabla existe
    try:
        from sqlalchemy import inspect
        inspector = inspect(db.engine)
        if 'repuestos_instalados' not in inspector.get_table_names():
            return jsonify({
                'error': 'Función no disponible', 
                'detail': 'La tabla repuestos_instalados no existe. Ejecuta las migraciones pendientes.'
            }), 503
    except Exception as e:
        print(f"Error verificando tabla: {e}")
    
    orden = OrdenTrabajo.query.get_or_404(orden_id)
    denied = require_branch_access(orden.branch_id)
    if denied:
        return denied
    data = request.get_json() or request.form
    try:
        product_id = data.get('product_id') or None
        nombre = (data.get('nombre') or '').strip() or None
        cantidad = int(data.get('cantidad') or 1)
        costo_unitario = float(data.get('costo_unitario') or 0)
        notas = data.get('notas_privadas') or None
        visible = data.get('visible_para_cliente') in (True, 'true', '1', 'y', 'yes')
    except Exception as e:
        return jsonify({'error': 'Datos invalidos', 'detail': str(e)}), 400

    rep = RepuestoInstalado(
        orden_id=orden.id,
        product_id=product_id,
        nombre=nombre,
        cantidad=cantidad,
        costo_unitario=costo_unitario,
        notas_privadas=notas,
        visible_para_cliente=visible,
        registrado_por_id=current_user.id if current_user.is_authenticated else None
    )
    rep.calcular_totales()
    try:
        db.session.add(rep)
        db.session.commit()
        return jsonify({'ok': True, 'repuesto_id': rep.id})
    except Exception as e:
        db.session.rollback()
        print(f"Error guardando repuesto: {e}")
        return jsonify({'error': 'No se pudo guardar', 'detail': str(e)}), 500


@ordenes_bp.route('/repuestos/<int:rep_id>', methods=['PUT'])
@login_required
@role_required('admin', 'supervisor', 'tecnico', 'vendedor', 'bodega')
def actualizar_repuesto(rep_id):
    rep = RepuestoInstalado.query.get_or_404(rep_id)
    # Anti-IDOR via la OT duena del repuesto
    orden = OrdenTrabajo.query.get(rep.orden_id)
    denied = require_branch_access(orden.branch_id if orden else None)
    if denied:
        return denied
    data = request.get_json() or request.form
    try:
        if 'cantidad' in data:
            rep.cantidad = int(data.get('cantidad') or rep.cantidad)
        if 'costo_unitario' in data:
            rep.costo_unitario = float(data.get('costo_unitario') or rep.costo_unitario)
        if 'nombre' in data:
            rep.nombre = (data.get('nombre') or '').strip() or rep.nombre
        if 'notas_privadas' in data:
            rep.notas_privadas = data.get('notas_privadas')
        if 'visible_para_cliente' in data:
            rep.visible_para_cliente = data.get('visible_para_cliente') in (True, 'true', '1', 'y', 'yes')
        rep.calcular_totales()
        db.session.commit()
        return jsonify({'ok': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'No se pudo actualizar', 'detail': str(e)}), 500


@ordenes_bp.route('/repuestos/<int:rep_id>', methods=['DELETE'])
@login_required
@role_required('admin', 'supervisor', 'tecnico', 'vendedor', 'bodega')
def eliminar_repuesto(rep_id):
    rep = RepuestoInstalado.query.get_or_404(rep_id)
    # Anti-IDOR via la OT duena del repuesto
    orden = OrdenTrabajo.query.get(rep.orden_id)
    denied = require_branch_access(orden.branch_id if orden else None)
    if denied:
        return denied
    try:
        db.session.delete(rep)
        db.session.commit()
        return jsonify({'ok': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'No se pudo eliminar', 'detail': str(e)}), 500