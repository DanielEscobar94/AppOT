from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash, make_response, send_file
from flask_login import login_required, current_user
from extensions import db
from models.models import (Venta, DetalleVenta, Product, Branch, User, SalidaProducto, TipoSalida, 
                          ExportacionSiigo, EstadoExportacion, ProductoOrden, OrdenTrabajo)
from sqlalchemy import func, and_, desc, or_, union_all, literal
from datetime import datetime, date
from utils.decorators import role_required
import pandas as pd
from io import BytesIO
import pytz

salidas_bp = Blueprint("salidas", __name__, url_prefix="/salidas")

# Configurar timezone de Bogota
BOGOTA_TZ = pytz.timezone('America/Bogota')

def obtener_fecha_bogota():
    """Obtener la fecha/hora actual en timezone de Bogota"""
    return datetime.now(BOGOTA_TZ)


def validar_fecha(fecha_str):
    """Convierte fecha DD/MM/YYYY a objeto date en timezone Bogotá"""
    if not fecha_str or not fecha_str.strip():
        return None
    try:
        # Parsear fecha DD/MM/YYYY
        fecha_dt = datetime.strptime(fecha_str.strip(), '%d/%m/%Y')
        # Establecer timezone Bogotá
        fecha_dt = BOGOTA_TZ.localize(fecha_dt.replace(hour=0, minute=0, second=0))
        return fecha_dt
    except ValueError:
        return None


def obtener_salidas_productos(sucursal_id=None, fecha_desde=None, fecha_hasta=None):
    """
    Obtiene todas las salidas de productos (ventas + OTs) con filtros aplicados.
    Retorna una lista de diccionarios con: producto_id, producto_nombre, sku, cantidad, valor_total, sucursal_id, sucursal_nombre
    """
    # Convertir fechas string a objetos datetime
    fecha_desde_dt = validar_fecha(fecha_desde) if fecha_desde else None
    fecha_hasta_dt = validar_fecha(fecha_hasta) if fecha_hasta else None
    if fecha_hasta_dt:
        fecha_hasta_dt = fecha_hasta_dt.replace(hour=23, minute=59, second=59)
    
    # Convertir a UTC para comparación en BD
    if fecha_desde_dt:
        fecha_desde_utc = fecha_desde_dt.astimezone(pytz.utc)
    if fecha_hasta_dt:
        fecha_hasta_utc = fecha_hasta_dt.astimezone(pytz.utc)
    
    # Query 1: Salidas de VENTAS (DetalleVenta)
    query_ventas = db.session.query(
        Product.id.label('producto_id'),
        Product.nombre.label('producto_nombre'),
        Product.sku.label('sku'),
        func.sum(DetalleVenta.cantidad).label('cantidad'),
        func.sum(DetalleVenta.cantidad * DetalleVenta.precio_unitario).label('valor_total'),
        Branch.id.label('sucursal_id'),
        Branch.nombre.label('sucursal_nombre')
    ).join(
        DetalleVenta, Product.id == DetalleVenta.producto_id
    ).join(
        Venta, DetalleVenta.venta_id == Venta.id
    ).join(
        Branch, Venta.branch_id == Branch.id
    ).filter(
        or_(Venta.eliminada == False, Venta.eliminada.is_(None))  # Excluir ventas eliminadas
    )
    
    # Aplicar filtros a ventas
    if sucursal_id:
        query_ventas = query_ventas.filter(Venta.branch_id == sucursal_id)
    if fecha_desde_dt:
        query_ventas = query_ventas.filter(Venta.fecha >= fecha_desde_utc)
    if fecha_hasta_dt:
        query_ventas = query_ventas.filter(Venta.fecha <= fecha_hasta_utc)
    
    query_ventas = query_ventas.group_by(
        Product.id, Product.nombre, Product.sku, Branch.id, Branch.nombre
    )
    
    # Query 2: Salidas de ORDENES DE TRABAJO (ProductoOrden)
    query_ots = db.session.query(
        Product.id.label('producto_id'),
        Product.nombre.label('producto_nombre'),
        Product.sku.label('sku'),
        func.sum(ProductoOrden.cantidad).label('cantidad'),
        func.sum(ProductoOrden.cantidad * ProductoOrden.precio_unitario).label('valor_total'),
        Branch.id.label('sucursal_id'),
        Branch.nombre.label('sucursal_nombre')
    ).join(
        ProductoOrden, Product.id == ProductoOrden.producto_id
    ).join(
        OrdenTrabajo, ProductoOrden.orden_id == OrdenTrabajo.id
    ).join(
        Branch, OrdenTrabajo.branch_id == Branch.id
    )
    
    # Aplicar filtros a OTs
    if sucursal_id:
        query_ots = query_ots.filter(OrdenTrabajo.branch_id == sucursal_id)
    if fecha_desde_dt:
        query_ots = query_ots.filter(OrdenTrabajo.fecha_creacion >= fecha_desde_utc)
    if fecha_hasta_dt:
        query_ots = query_ots.filter(OrdenTrabajo.fecha_creacion <= fecha_hasta_utc)
    
    query_ots = query_ots.group_by(
        Product.id, Product.nombre, Product.sku, Branch.id, Branch.nombre
    )
    
    # Combinar ambas queries y agrupar por producto-sucursal
    # Ejecutar queries y combinar resultados en Python
    salidas_ventas = query_ventas.all()
    salidas_ots = query_ots.all()
    
    # Diccionario para combinar salidas por producto-sucursal
    salidas_combinadas = {}
    
    for salida in salidas_ventas:
        key = (salida.producto_id, salida.sucursal_id)
        salidas_combinadas[key] = {
            'producto_id': salida.producto_id,
            'producto_nombre': salida.producto_nombre,
            'sku': salida.sku or 'Sin SKU',
            'cantidad': float(salida.cantidad or 0),
            'valor_total': float(salida.valor_total or 0),
            'sucursal_id': salida.sucursal_id,
            'sucursal_nombre': salida.sucursal_nombre
        }
    
    for salida in salidas_ots:
        key = (salida.producto_id, salida.sucursal_id)
        if key in salidas_combinadas:
            # Sumar a existente
            salidas_combinadas[key]['cantidad'] += float(salida.cantidad or 0)
            salidas_combinadas[key]['valor_total'] += float(salida.valor_total or 0)
        else:
            # Agregar nuevo
            salidas_combinadas[key] = {
                'producto_id': salida.producto_id,
                'producto_nombre': salida.producto_nombre,
                'sku': salida.sku or 'Sin SKU',
                'cantidad': float(salida.cantidad or 0),
                'valor_total': float(salida.valor_total or 0),
                'sucursal_id': salida.sucursal_id,
                'sucursal_nombre': salida.sucursal_nombre
            }
    
    # Convertir a lista y ordenar por cantidad descendente
    resultado = list(salidas_combinadas.values())
    resultado.sort(key=lambda x: x['cantidad'], reverse=True)
    
    return resultado


def obtener_ok_siigo_filtro(sucursal_id, fecha_desde, fecha_hasta):
    """Obtener el numero OK de Siigo para un filtro especifico"""
    # Crear una clave unica para este filtro
    filtro_key = f"filtro_{sucursal_id or 'todas'}_{fecha_desde or 'sin_inicio'}_{fecha_hasta or 'sin_fin'}"
    
    # Buscar en la tabla un registro con esta combinacion especifica
    registro = SalidaProducto.query.filter_by(
        motivo=f'OK_SIIGO_FILTRO:{filtro_key}'
    ).first()
    
    return registro.numero_ok_siigo if registro else None


def guardar_ok_siigo_filtro_db(sucursal_id, fecha_desde, fecha_hasta, numero_ok):
    """Guardar el numero OK de Siigo para un filtro especifico"""
    # Crear una clave unica para este filtro
    filtro_key = f"filtro_{sucursal_id or 'todas'}_{fecha_desde or 'sin_inicio'}_{fecha_hasta or 'sin_fin'}"
    
    # Buscar registro existente
    registro = SalidaProducto.query.filter_by(
        motivo=f'OK_SIIGO_FILTRO:{filtro_key}'
    ).first()
    
    if registro:
        # Actualizar existente
        registro.numero_ok_siigo = numero_ok
    else:
        # Crear nuevo registro especial para filtros
        registro = SalidaProducto(
            producto_id=1,  # Usar primer producto como placeholder
            cantidad=0,
            tipo_salida=TipoSalida.OTROS,
            branch_id=sucursal_id or 1,  # Usar primera sucursal como placeholder
            usuario_id=current_user.id,
            numero_ok_siigo=numero_ok,
            motivo=f'OK_SIIGO_FILTRO:{filtro_key}'
        )
        db.session.add(registro)
    
    db.session.commit()
    return registro

@salidas_bp.route('/')
@login_required
@role_required('admin', 'supervisor')
def listar():
    """Lista las salidas de productos (ventas + OTs) con filtros por sucursal y fecha"""
    
    # Obtener parametros de filtro
    sucursal_id = request.args.get('sucursal_id', type=int)
    fecha_desde = request.args.get('fecha_desde', type=str)
    fecha_hasta = request.args.get('fecha_hasta', type=str)
    page = request.args.get('page', 1, type=int)
    per_page = 10
    
    # Obtener salidas unificadas (ventas + OTs)
    salidas = obtener_salidas_productos(sucursal_id, fecha_desde, fecha_hasta)
    
    # Obtener todas las sucursales para el filtro
    sucursales = Branch.query.filter_by(activo=True).order_by(Branch.nombre).all()
    
    # Calcular totales generales
    total_productos_salidos = sum(s['cantidad'] for s in salidas)
    valor_total_salidas = sum(s['valor_total'] for s in salidas)
    
    # Paginación manual
    total = len(salidas)
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = max(1, min(page, total_pages))
    start = (page - 1) * per_page
    end = min(start + per_page, total)
    salidas_paginated = salidas[start:end] if salidas else []
    
    # Construir objeto de paginación simulado
    class PaginationInfo:
        def __init__(self):
            self.page = page
            self.per_page = per_page
            self.total = total
            self.pages = total_pages
            self.items = salidas_paginated
            self.has_prev = page > 1
            self.has_next = page < total_pages
            self.prev_num = page - 1 if page > 1 else None
            self.next_num = page + 1 if page < total_pages else None
        
        def iter_pages(self, left_edge=1, right_edge=1, left_current=2, right_current=2):
            last = self.pages
            left_edge_end = min(left_edge, last)
            right_edge_start = max(last - right_edge + 1, left_edge + 1)
            left_current_start = max(self.page - left_current, left_edge + 1)
            right_current_end = min(self.page + right_current, last - right_edge)
            
            for i in range(1, left_edge_end + 1):
                yield i
            if left_edge_end + 1 < left_current_start:
                yield None
            for i in range(left_current_start, right_current_end + 1):
                if i > left_edge_end:
                    yield i
            if right_current_end + 1 < right_edge_start:
                yield None
            for i in range(right_edge_start, last + 1):
                if i > right_current_end:
                    yield i
    
    pagination = PaginationInfo()
    
    return render_template('salidas/listar.html', 
                         salidas=salidas_paginated,
                         pagination=pagination,
                         sucursales=sucursales,
                         sucursal_id=sucursal_id,
                         fecha_desde=fecha_desde,
                         fecha_hasta=fecha_hasta,
                         total_productos_salidos=total_productos_salidos,
                         valor_total_salidas=valor_total_salidas)


@salidas_bp.route('/detalle/<int:producto_id>')
@login_required
@role_required('admin', 'supervisor')
def detalle_producto(producto_id):
    """Muestra el detalle de salidas de un producto especifico"""
    
    producto = Product.query.get_or_404(producto_id)
    
    # Obtener parametros de filtro
    sucursal_id = request.args.get('sucursal_id', type=int)
    fecha_desde = request.args.get('fecha_desde', type=str)
    fecha_hasta = request.args.get('fecha_hasta', type=str)
    
    # Query para obtener todas las ventas de este producto
    query = db.session.query(
        Venta.id,
        Venta.numero_factura,
        Venta.fecha,
        DetalleVenta.cantidad,
        DetalleVenta.precio_unitario,
        (DetalleVenta.cantidad * DetalleVenta.precio_unitario).label('subtotal'),
        Branch.nombre.label('sucursal_nombre'),
        Venta.cliente_id
    ).join(
        DetalleVenta, Venta.id == DetalleVenta.venta_id
    ).join(
        Branch, Venta.branch_id == Branch.id
    ).filter(
        DetalleVenta.producto_id == producto_id
    )
    
    # Aplicar filtros
    filtros = []
    
    if sucursal_id:
        filtros.append(Venta.branch_id == sucursal_id)
    
    if fecha_desde:
        try:
            fecha_desde_obj = datetime.strptime(fecha_desde, '%d/%m/%Y').date()
            filtros.append(func.date(Venta.fecha) >= fecha_desde_obj)
        except ValueError:
            pass
    
    if fecha_hasta:
        try:
            fecha_hasta_obj = datetime.strptime(fecha_hasta, '%d/%m/%Y').date()
            filtros.append(func.date(Venta.fecha) <= fecha_hasta_obj)
        except ValueError:
            pass
    
    if filtros:
        query = query.filter(and_(*filtros))
    
    ventas_detalle = query.order_by(desc(Venta.fecha)).all()
    
    # Obtener todas las sucursales para el filtro
    sucursales = Branch.query.filter_by(activo=True).order_by(Branch.nombre).all()
    
    return render_template('salidas/detalle.html',
                         producto=producto,
                         ventas_detalle=ventas_detalle,
                         sucursales=sucursales,
                         sucursal_id=sucursal_id,
                         fecha_desde=fecha_desde,
                         fecha_hasta=fecha_hasta)


@salidas_bp.route('/registrar', methods=['GET', 'POST'])
@login_required
@role_required('admin', 'supervisor')
def registrar_salida():
    """Registrar una nueva salida manual de productos"""
    
    if request.method == 'POST':
        try:
            producto_id = request.form.get('producto_id', type=int)
            cantidad = request.form.get('cantidad', type=int)
            tipo_salida = request.form.get('tipo_salida')
            motivo = request.form.get('motivo', '').strip()
            sucursal_id = request.form.get('sucursal_id', type=int)
            
            # Validaciones
            if not all([producto_id, cantidad, tipo_salida, sucursal_id]):
                flash('Todos los campos obligatorios deben ser completados', 'danger')
                return redirect(url_for('salidas.registrar_salida'))
            
            if cantidad <= 0:
                flash('La cantidad debe ser mayor a 0', 'danger')
                return redirect(url_for('salidas.registrar_salida'))
            
            producto = Product.query.get(producto_id)
            if not producto:
                flash('Producto no encontrado', 'danger')
                return redirect(url_for('salidas.registrar_salida'))
            
            sucursal = Branch.query.get(sucursal_id)
            if not sucursal:
                flash('Sucursal no encontrada', 'danger')
                return redirect(url_for('salidas.registrar_salida'))
            
            # Crear nuevo registro de salida
            salida = SalidaProducto(
                producto_id=producto_id,
                cantidad=cantidad,
                tipo_salida=TipoSalida(tipo_salida),
                motivo=motivo,
                branch_id=sucursal_id,
                usuario_id=current_user.id,
                valor_unitario=producto.precio_unitario or 0,
                valor_total=(producto.precio_unitario or 0) * cantidad
            )
            
            db.session.add(salida)
            db.session.commit()
            
            flash(f'Salida registrada exitosamente: {cantidad} unidades de {producto.nombre} - Tipo: {tipo_salida}', 'success')
            return redirect(url_for('salidas.listar'))
            
        except Exception as e:
            flash(f'Error al registrar la salida: {str(e)}', 'danger')
            return redirect(url_for('salidas.registrar_salida'))
    
    # GET - Mostrar formulario
    productos = Product.query.order_by(Product.nombre).all()
    sucursales = Branch.query.filter_by(activo=True).order_by(Branch.nombre).all()
    
    tipos_salida = [
        ('defectuoso', 'Producto Defectuoso'),
        ('perdida', 'Perdida'),
        ('traslado', 'Traslado'),
        ('devolucion', 'Devolucion'),
        ('consumo_interno', 'Consumo Interno'),
        ('regalo', 'Regalo'),
        ('otros', 'Otros')
    ]
    
    return render_template('salidas/registrar.html',
                         productos=productos,
                         sucursales=sucursales,
                         tipos_salida=tipos_salida)


@salidas_bp.route('/buscar_producto')
@login_required
@role_required('admin', 'supervisor')
def buscar_producto():
    """Buscar productos por SKU o nombre para el autocompletado"""
    q = request.args.get('q', '').strip()
    
    if not q or len(q) < 2:
        return jsonify([])
    
    # Buscar productos por SKU o nombre
    from sqlalchemy import or_
    productos = Product.query.filter(
        or_(
            Product.sku.ilike(f'%{q}%'),
            Product.nombre.ilike(f'%{q}%')
        )
    ).limit(10).all()
    
    resultados = []
    for p in productos:
        resultados.append({
            'id': p.id,
            'nombre': p.nombre,
            'sku': p.sku or 'Sin SKU',
            'label': f'{p.nombre} ({p.sku or "Sin SKU"})',
            'precio': float(p.precio_unitario) if p.precio_unitario else 0
        })

    return jsonify(resultados)


@salidas_bp.route('/exportar-excel')
@login_required
@role_required('admin', 'supervisor')
def exportar_excel():
    """Exportar salidas filtradas a Excel (ventas + OTs) y crear registro de exportacion"""
    
    # Obtener parametros de filtro
    sucursal_id = request.args.get('sucursal_id', type=int)
    fecha_desde = request.args.get('fecha_desde', type=str)
    fecha_hasta = request.args.get('fecha_hasta', type=str)
    
    # Convertir fechas string a objetos date
    fecha_desde_obj = None
    fecha_hasta_obj = None
    
    if fecha_desde:
        try:
            fecha_desde_obj = datetime.strptime(fecha_desde, '%d/%m/%Y').date()
        except ValueError:
            pass
    
    if fecha_hasta:
        try:
            fecha_hasta_obj = datetime.strptime(fecha_hasta, '%d/%m/%Y').date()
        except ValueError:
            pass
    
    # Obtener salidas unificadas usando la misma función que la vista web
    salidas = obtener_salidas_productos(sucursal_id, fecha_desde, fecha_hasta)
    
    # Convertir a DataFrame
    data = []
    for s in salidas:
        data.append({
            'SKU': s['sku'],
            'Producto': s['producto_nombre'],
            'Cantidad': s['cantidad'],
            'Valor Total': s['valor_total'],
            'Sucursal': s['sucursal_nombre'],
        })
    
    df = pd.DataFrame(data)
    
    # Crear archivo Excel en memoria
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Salidas de Productos', index=False)
        
        # Formatear el worksheet
        workbook = writer.book
        worksheet = writer.sheets['Salidas de Productos']
        
        # Ajustar ancho de columnas
        for col in worksheet.columns:
            max_length = 0
            column = col[0].column_letter
            for cell in col:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            adjusted_width = min(max_length + 2, 50)
            worksheet.column_dimensions[column].width = adjusted_width
    
    output.seek(0)
    
    # Generar nombre de archivo con filtros aplicados
    filename = "salidas_productos"
    if sucursal_id:
        sucursal = Branch.query.get(sucursal_id)
        if sucursal:
            filename += f"_{sucursal.nombre.replace(' ', '_')}"
    
    if fecha_desde and fecha_hasta:
        filename += f"_{fecha_desde}_a_{fecha_hasta}"
    elif fecha_desde:
        filename += f"_desde_{fecha_desde}"
    elif fecha_hasta:
        filename += f"_hasta_{fecha_hasta}"
    
    filename += ".xlsx"
    
    # Calcular totales para el registro
    total_registros = len(salidas)
    valor_total = sum(s['valor_total'] for s in salidas)
    
    # Crear registro de exportacion
    try:
        exportacion = ExportacionSiigo(
            fecha_exportacion=obtener_fecha_bogota(),
            fecha_desde=fecha_desde_obj,
            fecha_hasta=fecha_hasta_obj,
            sucursal_id=sucursal_id,
            archivo_excel=filename,
            usuario_id=current_user.id,
            total_registros=total_registros,
            valor_total=valor_total,
            estado=EstadoExportacion.PENDIENTE,
            observaciones=f"Exportacion automatica - {total_registros} registros"
        )
        
        db.session.add(exportacion)
        db.session.commit()
        
        # Actualizar filename para incluir ID de exportacion
        filename_with_id = f"EXP{exportacion.id:04d}_{filename}"
        exportacion.archivo_excel = filename_with_id
        db.session.commit()
        
    except Exception as e:
        db.session.rollback()
        print(f"Error creando registro de exportacion: {e}")
        filename_with_id = filename
    
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=filename_with_id
    )


@salidas_bp.route('/guardar-ok-siigo', methods=['POST'])
@login_required
@role_required('admin', 'supervisor')
def guardar_ok_siigo():
    """Guardar el numero OK de Siigo para una salida de producto"""
    try:
        data = request.get_json()
        producto_id = data.get('producto_id')
        sucursal_id = data.get('sucursal_id')
        numero_ok_siigo = data.get('numero_ok_siigo', '').strip()
        
        if not producto_id:
            return jsonify({'success': False, 'message': 'Producto ID requerido'}), 400
        
        # Por ahora creamos un registro de salida temporal o lo actualizamos
        # En el futuro esto deberia estar vinculado a registros reales de salidas
        
        # Buscar si ya existe un registro de salida para este producto/sucursal
        salida_existente = SalidaProducto.query.filter_by(
            producto_id=producto_id,
            branch_id=sucursal_id
        ).first()
        
        if salida_existente:
            # Actualizar el registro existente
            salida_existente.numero_ok_siigo = numero_ok_siigo
        else:
            # Crear un nuevo registro temporal
            producto = Product.query.get(producto_id)
            if not producto:
                return jsonify({'success': False, 'message': 'Producto no encontrado'}), 404
            
            salida = SalidaProducto(
                producto_id=producto_id,
                cantidad=0,  # Temporal, se actualizara cuando se registre la salida real
                tipo_salida=TipoSalida.OTROS,
                branch_id=sucursal_id,
                usuario_id=current_user.id,
                numero_ok_siigo=numero_ok_siigo,
                motivo='Registro temporal para OK Siigo'
            )
            db.session.add(salida)
        
        db.session.commit()
        
        return jsonify({
            'success': True, 
            'message': f'OK Siigo guardado: {numero_ok_siigo}',
            'numero_ok': numero_ok_siigo
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500


@salidas_bp.route('/guardar-ok-siigo-filtro', methods=['POST'])
@login_required
@role_required('admin', 'supervisor')
def guardar_ok_siigo_filtro():
    """Guardar el numero OK de Siigo para un filtro especifico"""
    try:
        data = request.get_json()
        numero_ok_siigo = data.get('numero_ok_siigo', '').strip()
        sucursal_id = data.get('sucursal_id')
        fecha_desde = data.get('fecha_desde')
        fecha_hasta = data.get('fecha_hasta')
        
        # Convertir strings vacios a None
        if sucursal_id == '':
            sucursal_id = None
        else:
            sucursal_id = int(sucursal_id) if sucursal_id else None
            
        if fecha_desde == '':
            fecha_desde = None
        if fecha_hasta == '':
            fecha_hasta = None
        
        if not numero_ok_siigo:
            return jsonify({'success': False, 'message': 'Numero OK requerido'}), 400
        
        # Guardar en la base de datos
        registro = guardar_ok_siigo_filtro_db(sucursal_id, fecha_desde, fecha_hasta, numero_ok_siigo)
        
        return jsonify({
            'success': True, 
            'message': f'OK Siigo guardado para el filtro: {numero_ok_siigo}',
            'numero_ok': numero_ok_siigo
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500


@salidas_bp.route('/historial-exportaciones')
@login_required
@role_required('admin', 'supervisor')
def historial_exportaciones():
    """Ver historial de exportaciones a Siigo"""
    
    # Obtener filtros
    estado_filtro = request.args.get('estado', '')
    sucursal_filtro = request.args.get('sucursal_id', type=int)
    
    # Query base
    query = ExportacionSiigo.query
    
    # Aplicar filtros
    if estado_filtro:
        query = query.filter(ExportacionSiigo.estado == EstadoExportacion(estado_filtro))
    
    if sucursal_filtro:
        query = query.filter(ExportacionSiigo.sucursal_id == sucursal_filtro)
    
    # Ordenar por fecha mas reciente
    exportaciones = query.order_by(desc(ExportacionSiigo.fecha_exportacion)).all()
    
    # Obtener sucursales para filtro
    sucursales = Branch.query.filter_by(activo=True).order_by(Branch.nombre).all()
    
    # Estados disponibles
    estados = [estado.value for estado in EstadoExportacion]
    
    return render_template('salidas/historial_exportaciones.html',
                         exportaciones=exportaciones,
                         sucursales=sucursales,
                         estados=estados,
                         estado_filtro=estado_filtro,
                         sucursal_filtro=sucursal_filtro)


@salidas_bp.route('/actualizar-ok-siigo/<int:exportacion_id>', methods=['POST'])
@login_required
@role_required('admin', 'supervisor')
def actualizar_ok_siigo(exportacion_id):
    """Actualizar el numero OK de Siigo para una exportacion"""
    try:
        data = request.get_json()
        numero_ok = data.get('numero_ok_siigo', '').strip()
        
        exportacion = ExportacionSiigo.query.get_or_404(exportacion_id)
        
        if not numero_ok:
            return jsonify({'success': False, 'message': 'Numero OK requerido'}), 400
        
        exportacion.numero_ok_siigo = numero_ok
        exportacion.estado = EstadoExportacion.PROCESADO
        exportacion.fecha_procesado = obtener_fecha_bogota()
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'OK Siigo actualizado: {numero_ok}',
            'numero_ok': numero_ok
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500


@salidas_bp.route('/cancelar-exportacion/<int:exportacion_id>', methods=['POST'])
@login_required
@role_required('admin', 'supervisor')
def cancelar_exportacion(exportacion_id):
    """Eliminar un registro de exportacion (accion irreversible)."""
    try:
        exportacion = ExportacionSiigo.query.get_or_404(exportacion_id)
        # Para seguridad, solo permitir eliminar exportaciones en estado pendiente o cancelado
        # (evitar borrar registros procesados). Si se desea otro comportamiento, ajustar aquí.
        if exportacion.estado == EstadoExportacion.PROCESADO:
            return jsonify({'success': False, 'message': 'No se puede eliminar una exportacion ya procesada.'}), 400

        db.session.delete(exportacion)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Registro de exportacion eliminado.'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Error al eliminar: {e}'}), 500