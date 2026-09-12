from flask import Blueprint, render_template, request, jsonify, current_app
from flask_login import login_required, current_user
from extensions import db
from models.models import Venta, OrdenTrabajo, Branch, User, Anticipo, Client
from sqlalchemy import func, and_, or_, exists, text
from datetime import datetime, date
from utils.decorators import role_required, scoped_branch_param

def validar_fecha(fecha_str):
    """Valida y convierte una cadena de fecha en formato dd/mm/yyyy a datetime con zona horaria."""
    try:
        dt_naive = datetime.strptime(fecha_str, '%d/%m/%Y')
        import pytz
        colombia_tz = pytz.timezone('America/Bogota')
        return colombia_tz.localize(dt_naive)
    except ValueError:
        current_app.logger.error(f"Formato de fecha inválido: {fecha_str}")
        return None


def _filtrar_anticipos_por_sucursal(query, branch_id):
    """Filtra anticipos por sucursal.
    - Si branch_id está fijado en el anticipo, se usa ese valor directamente.
    - Solo para registros históricos con branch_id NULL se recae en la sucursal de la OT.
    Esto evita que anticipos registrados por usuarios de otra sucursal aparezcan en los
    reportes de la sucursal dueña de la OT.
    """
    if not branch_id:
        return query
    from sqlalchemy import or_, and_
    return query.filter(
        or_(
            Anticipo.branch_id == branch_id,
            and_(
                Anticipo.branch_id.is_(None),
                Anticipo.orden_id.in_(
                    db.session.query(OrdenTrabajo.id).filter(OrdenTrabajo.branch_id == branch_id)
                )
            )
        )
    )

def _detalles_total_for_venta(venta_id):
    """Return sum of cantidad * precio_unitario for a venta using a safe raw query.
    Returns 0.0 if no rows or on error.
    """
    try:
        sql = text("SELECT SUM(cantidad * precio_unitario) as total FROM detalle_venta WHERE venta_id = :vid")
        row = db.session.execute(sql, {'vid': venta_id}).mappings().first()
        if row and row.get('total') is not None:
            return float(row.get('total'))
    except Exception:
        pass
    return 0.0

reportes_bp = Blueprint("reportes", __name__, url_prefix="/reportes")






@reportes_bp.route('/ventas/exportar')
@login_required
@role_required('admin', 'supervisor', 'vendedor', 'tecnico')
def exportar_ventas():
    """Exportar reporte de ventas a Excel"""
    import pandas as pd
    import io
    from flask import send_file

    # Obtener parametros de filtro
    sucursal_id = scoped_branch_param(request.args.get('sucursal', type=int))
    caja_filtro = request.args.get('caja', '').strip().lower()
    fecha_inicio = request.args.get('fecha_inicio')
    fecha_fin = request.args.get('fecha_fin')

    # Si el usuario proporcionó fecha_inicio pero no fecha_fin, asumimos que quiere filtrar ese día
    if fecha_inicio and (not fecha_fin or fecha_fin.strip() == ''):
        fecha_fin = fecha_inicio
    
    # Establecer fechas por defecto si no se proporcionan
    today = date.today()
    fecha_inicio_default = today.replace(day=1).strftime('%d/%m/%Y')
    fecha_fin_default = today.strftime('%d/%m/%Y')
    
    if not fecha_inicio or fecha_inicio.strip() == '':
        fecha_inicio = fecha_inicio_default
    if not fecha_fin or fecha_fin.strip() == '':
        fecha_fin = fecha_fin_default
    
    # Query base - filtrar por caja si se especifica
    query = Venta.query.filter(
        or_(Venta.eliminada == False, Venta.eliminada.is_(None))
    )
    
    # Aplicar filtro de caja
    if caja_filtro and caja_filtro in ['appot', 'siigo']:
        query = query.filter(Venta.caja_tramite == caja_filtro)
    
    # Aplicar filtros
    if sucursal_id:
        query = query.filter(Venta.branch_id == sucursal_id)
    
    if fecha_inicio and fecha_inicio.strip():
        fecha_inicio_dt = validar_fecha(fecha_inicio)
        if fecha_inicio_dt:
            try:
                import pytz
                fecha_inicio_utc = fecha_inicio_dt.astimezone(pytz.utc)
            except Exception:
                fecha_inicio_utc = fecha_inicio_dt
            query = query.filter(Venta.fecha >= fecha_inicio_utc)

    if fecha_fin and fecha_fin.strip():
        fecha_fin_dt = validar_fecha(fecha_fin)
        if fecha_fin_dt:
            fecha_fin_dt = fecha_fin_dt.replace(hour=23, minute=59, second=59)
            try:
                import pytz
                fecha_fin_utc = fecha_fin_dt.astimezone(pytz.utc)
            except Exception:
                fecha_fin_utc = fecha_fin_dt
            query = query.filter(Venta.fecha <= fecha_fin_utc)

    # Obtener todas las ventas (sin paginación)
    ventas = query.order_by(Venta.fecha.desc()).all()

    # Preparar datos para Excel - Una fila por producto mostrando productos
    data = []
    
    # Agregar ventas con sus productos (una fila por producto)
    from models.models import DetalleVenta
    for venta in ventas:
        # Usar SALDO para que la suma de la columna coincida con el Resumen (igual que la web)
        # saldo = total - anticipo_total (lo que realmente ingresó a caja al facturar)
        saldo_venta = float(venta.saldo if venta.saldo is not None
                            else max(0.0, float(venta.total or 0) - float(getattr(venta, 'anticipo_total', 0) or 0)))
        neto = max(0.0, saldo_venta)
        
        # Obtener los detalles de la venta
        detalles = DetalleVenta.query.filter_by(venta_id=venta.id).all()
        
        if detalles:
            # Crear una fila por cada producto
            # El total de la factura solo se muestra en la primera línea para evitar duplicación
            for idx, detalle in enumerate(detalles):
                # Obtener SKU del producto
                sku = ''
                if detalle.producto_id and detalle.producto:
                    sku = detalle.producto.sku or ''
                
                data.append({
                    'Tipo': 'Venta',
                    'Factura/OT': f"FAC-{venta.numero_factura}",
                    'Cliente': venta.cliente.nombre if venta.cliente else 'Consumidor Final',
                    'Sucursal': venta.branch.nombre if venta.branch else 'N/A',
                    'Fecha': venta.fecha.strftime('%d/%m/%Y %H:%M'),
                    'SKU': sku,
                    'Producto': detalle.get_nombre_display(),
                    'Cantidad': detalle.cantidad,
                    'Total': neto if idx == 0 else ''  # Solo mostrar en primera línea
                })
        else:
            # Si no hay detalles, agregar la venta sin productos
            data.append({
                'Tipo': 'Venta',
                'Factura/OT': f"FAC-{venta.numero_factura}",
                'Cliente': venta.cliente.nombre if venta.cliente else 'Consumidor Final',
                'Sucursal': venta.branch.nombre if venta.branch else 'N/A',
                'Fecha': venta.fecha.strftime('%d/%m/%Y %H:%M'),
                'SKU': '',
                'Producto': 'Sin productos',
                'Cantidad': 0,
                'Total': neto
            })
    
    # Consultar SOLO anticipos SIN FACTURAR (venta_id IS NULL) DE APPOT con el mismo filtro de sucursal y fechas
    from models.models import Anticipo, OrdenTrabajo
    
    anticipo_query = db.session.query(Anticipo).filter(
        Anticipo.venta_id.is_(None),
        Anticipo.caja_tramite == 'appot'
    )
    anticipo_query = _filtrar_anticipos_por_sucursal(anticipo_query, sucursal_id)
    
    if fecha_inicio and fecha_inicio.strip():
        fecha_inicio_dt = validar_fecha(fecha_inicio)
        if fecha_inicio_dt:
            try:
                import pytz
                fecha_inicio_utc = fecha_inicio_dt.astimezone(pytz.utc)
            except Exception:
                fecha_inicio_utc = fecha_inicio_dt
            anticipo_query = anticipo_query.filter(Anticipo.fecha >= fecha_inicio_utc)
    
    if fecha_fin and fecha_fin.strip():
        fecha_fin_dt = validar_fecha(fecha_fin)
        if fecha_fin_dt:
            fecha_fin_dt = fecha_fin_dt.replace(hour=23, minute=59, second=59)
            try:
                import pytz
                fecha_fin_utc = fecha_fin_dt.astimezone(pytz.utc)
            except Exception:
                fecha_fin_utc = fecha_fin_dt
            anticipo_query = anticipo_query.filter(Anticipo.fecha <= fecha_fin_utc)
    
    anticipos = anticipo_query.all()
    
    # Agregar anticipos (una fila por anticipo)
    for anticipo in anticipos:
        monto = float(anticipo.monto)
        
        data.append({
            'Tipo': 'Anticipo',
            'Factura/OT': f"OT-{anticipo.orden.consecutivo}" if anticipo.orden else 'N/A',
            'Cliente': anticipo.orden.client.nombre if anticipo.orden and anticipo.orden.client else 'N/A',
            'Sucursal': anticipo.orden.branch.nombre if anticipo.orden and anticipo.orden.branch else 'N/A',
            'Fecha': anticipo.fecha.strftime('%d/%m/%Y %H:%M'),
            'SKU': '',
            'Producto': 'Anticipo',
            'Cantidad': 1,
            'Total': monto
        })
    
    # Crear DataFrame y ordenar por fecha
    df = pd.DataFrame(data)
    if not df.empty:
        df = df.sort_values(by='Fecha', ascending=True)

    # Generar Excel en memoria
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        # Hoja principal con todos los datos
        df.to_excel(writer, index=False, sheet_name='Todos')
        
        # Hojas separadas por tipo si hay datos
        if not df.empty:
            df_ventas = df[df['Tipo'] == 'Venta']
            if not df_ventas.empty:
                df_ventas.to_excel(writer, index=False, sheet_name='Ventas')
            
            df_anticipos = df[df['Tipo'] == 'Anticipo']
            if not df_anticipos.empty:
                df_anticipos.to_excel(writer, index=False, sheet_name='Anticipos')
        
        # Agregar hoja resumen usando la MISMA lógica que la vista web
        # La web usa SUM(saldo) para ventas (lo que realmente ingresó a caja,
        # descontando anticipos ya contabilizados). Antes se usaba SUM(total - descuento)
        # lo que causaba discrepancia porque doble-contaba los anticipos aplicados.
        if not df.empty:
            resumen_data = []
            
            # Calcular total de ventas usando SALDO (igual que la vista web)
            # saldo = total - anticipo_total (lo que realmente se pagó al facturar)
            total_ventas_query = db.session.query(
                db.func.sum(
                    db.func.coalesce(Venta.saldo, Venta.total - db.func.coalesce(Venta.anticipo_total, 0))
                )
            ).filter(
                or_(Venta.eliminada == False, Venta.eliminada.is_(None))
            )
            
            # Aplicar filtro de caja según selección del usuario (no hardcodear 'appot')
            if caja_filtro and caja_filtro in ['appot', 'siigo']:
                total_ventas_query = total_ventas_query.filter(Venta.caja_tramite == caja_filtro)
            
            # Aplicar los mismos filtros de sucursal y fecha que se usaron para las ventas
            if sucursal_id:
                total_ventas_query = total_ventas_query.filter(Venta.branch_id == sucursal_id)
            
            if fecha_inicio and fecha_inicio.strip():
                fecha_inicio_dt = validar_fecha(fecha_inicio)
                if fecha_inicio_dt:
                    try:
                        import pytz
                        fecha_inicio_utc = fecha_inicio_dt.astimezone(pytz.utc)
                    except Exception:
                        fecha_inicio_utc = fecha_inicio_dt
                    total_ventas_query = total_ventas_query.filter(Venta.fecha >= fecha_inicio_utc)
            
            if fecha_fin and fecha_fin.strip():
                fecha_fin_dt = validar_fecha(fecha_fin)
                if fecha_fin_dt:
                    fecha_fin_dt = fecha_fin_dt.replace(hour=23, minute=59, second=59)
                    try:
                        import pytz
                        fecha_fin_utc = fecha_fin_dt.astimezone(pytz.utc)
                    except Exception:
                        fecha_fin_utc = fecha_fin_dt
                    total_ventas_query = total_ventas_query.filter(Venta.fecha <= fecha_fin_utc)
            
            total_ventas_resumen = float(total_ventas_query.scalar() or 0)
            
            # Calcular anticipos sin facturar usando la MISMA lógica que la vista web
            # (respetando filtro de caja y método de pago)
            anticipos_unicos = {}
            for ant in anticipos:
                if ant.id not in anticipos_unicos:
                    anticipos_unicos[ant.id] = ant
            
            total_anticipos_resumen = 0.0
            for ant in anticipos_unicos.values():
                metodo = getattr(ant, 'metodo_pago', '').lower()
                caja = getattr(ant, 'caja_tramite', 'appot')
                
                if caja_filtro == 'appot' or (not caja_filtro and caja == 'appot'):
                    # Solo efectivo para AppOT
                    if metodo == 'efectivo':
                        total_anticipos_resumen += float(ant.monto)
                elif caja_filtro == 'siigo' or (not caja_filtro and caja == 'siigo'):
                    # Todos los métodos para Siigo
                    total_anticipos_resumen += float(ant.monto)
            
            # Total en caja (igual que en la web)
            total_en_caja = total_ventas_resumen + total_anticipos_resumen
            
            # Crear resumen
            resumen_data.append({
                'Concepto': 'Ventas',
                'Total': float(total_ventas_resumen)
            })
            
            resumen_data.append({
                'Concepto': 'Anticipos sin facturar',
                'Total': float(total_anticipos_resumen)
            })
            
            resumen_data.append({
                'Concepto': 'TOTAL EN CAJA',
                'Total': float(total_en_caja)
            })
            
            df_resumen = pd.DataFrame(resumen_data)
            df_resumen.to_excel(writer, index=False, sheet_name='Resumen')
    
    output.seek(0)
    
    filename = f"Reporte_Caja_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=filename
    )


@reportes_bp.route('/ventas')
@login_required
@role_required('admin', 'supervisor', 'vendedor', 'tecnico')
def ventas():
    """Reporte de ventas con filtros por sucursal y rango de fechas"""
    
    # Obtener parametros de filtro
    sucursal_id = scoped_branch_param(request.args.get('sucursal', type=int))
    caja_filtro = request.args.get('caja', '').strip().lower()  # 'appot', 'siigo', o '' (todas)
    fecha_inicio = request.args.get('fecha_inicio')
    fecha_fin = request.args.get('fecha_fin')

    # Si el usuario proporcionó fecha_inicio pero no fecha_fin, asumimos que quiere filtrar ese día
    if fecha_inicio and (not fecha_fin or fecha_fin.strip() == ''):
        fecha_fin = fecha_inicio
    
    # Parámetros de paginación
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)
    
    # Establecer fechas por defecto si no se proporcionan
    today = date.today()
    fecha_inicio_default = today.replace(day=1).strftime('%d/%m/%Y')  # Primer día del mes actual
    fecha_fin_default = today.strftime('%d/%m/%Y')  # Día actual
    
    # Si no se proporcionan fechas, usar valores por defecto para mostrar
    if not fecha_inicio or fecha_inicio.strip() == '':
        fecha_inicio = fecha_inicio_default
    if not fecha_fin or fecha_fin.strip() == '':
        fecha_fin = fecha_fin_default
    
    # Query base - excluir ventas eliminadas (considerar NULL como no eliminada)
    query = Venta.query.filter(or_(Venta.eliminada == False, Venta.eliminada.is_(None)))
    
    # Aplicar filtro de caja
    if caja_filtro and caja_filtro in ['appot', 'siigo']:
        query = query.filter(Venta.caja_tramite == caja_filtro)
    # Si no hay filtro o es 'todas', mostrar todas las cajas
    
    # Aplicar filtros
    if sucursal_id:
        query = query.filter(Venta.branch_id == sucursal_id)
    
    # Aplicar filtro de fecha solo si se proporcionaron fechas
    if fecha_inicio and fecha_inicio.strip():
        fecha_inicio_dt = validar_fecha(fecha_inicio)
        if fecha_inicio_dt:
            # Convertir a UTC para comparar con la base de datos de forma consistente
            try:
                import pytz
                fecha_inicio_utc = fecha_inicio_dt.astimezone(pytz.utc)
            except Exception:
                fecha_inicio_utc = fecha_inicio_dt
            query = query.filter(Venta.fecha >= fecha_inicio_utc)

    if fecha_fin and fecha_fin.strip():
        fecha_fin_dt = validar_fecha(fecha_fin)
        if fecha_fin_dt:
            # Incluir todo el día final y convertir a UTC
            fecha_fin_dt = fecha_fin_dt.replace(hour=23, minute=59, second=59)
            try:
                import pytz
                fecha_fin_utc = fecha_fin_dt.astimezone(pytz.utc)
            except Exception:
                fecha_fin_utc = fecha_fin_dt
            query = query.filter(Venta.fecha <= fecha_fin_utc)
    
    # Normalizar rol del usuario y aplicar filtro de sucursal segun rol
    # - admin y supervisor ven todas las sucursales
    # - vendedor solo ve ventas de su sucursal y propias
    # - tecnico solo ve ventas de su sucursal
    # Normalizar rol del usuario (no filtramos ventas por rol aquí: todos ven todas las sucursales)
    try:
        role = (getattr(current_user, 'rol', '') or '').strip().lower()
        user_branch = getattr(current_user, 'branch_id', None)
        user_id = getattr(current_user, 'id', None)
    except Exception:
        role = ''
        user_branch = None
        user_id = None
    
    # Obtener ventas ordenadas por fecha descendente (últimas ventas primero)
    # Siempre ordenar por fecha descendente, sin agrupar por sucursal
    ventas_pagination = query.order_by(Venta.fecha.desc()).paginate(page=page, per_page=per_page, error_out=False)
    ventas = ventas_pagination.items

    # Calcular anticipos del período filtrado
    anticipos_query = Anticipo.query
    
    # Aplicar los mismos filtros de fecha a los anticipos (solo si se aplicaron a las ventas)
    if fecha_inicio and fecha_inicio.strip():
        fecha_inicio_dt = validar_fecha(fecha_inicio)
        if fecha_inicio_dt:
            # Convertir a UTC
            try:
                import pytz
                fecha_inicio_utc = fecha_inicio_dt.astimezone(pytz.utc)
            except Exception:
                fecha_inicio_utc = fecha_inicio_dt
            anticipos_query = anticipos_query.filter(Anticipo.fecha >= fecha_inicio_utc)

    if fecha_fin and fecha_fin.strip():
        fecha_fin_dt = validar_fecha(fecha_fin)
        if fecha_fin_dt:
            fecha_fin_dt = fecha_fin_dt.replace(hour=23, minute=59, second=59)
            # Convertir a UTC
            try:
                import pytz
                fecha_fin_utc = fecha_fin_dt.astimezone(pytz.utc)
            except Exception:
                fecha_fin_utc = fecha_fin_dt
            anticipos_query = anticipos_query.filter(Anticipo.fecha <= fecha_fin_utc)
    
    # Filtrar anticipos por sucursal (usando branch_id directo o subquery OT como fallback)
    anticipos_query = _filtrar_anticipos_por_sucursal(anticipos_query, sucursal_id)
    
    # Obtener todos los anticipos del período
    anticipos_periodo = anticipos_query.all()
    
    # Eliminar duplicados basándose en id del anticipo
    anticipos_unicos_dict = {}
    for ant in anticipos_periodo:
        if ant.id not in anticipos_unicos_dict:
            anticipos_unicos_dict[ant.id] = ant
    
    anticipos_periodo_unicos = list(anticipos_unicos_dict.values())
    
    # Separar anticipos según su estado y caja de trámite
    anticipos_sin_facturar = []
    anticipos_aplicados_ventas = []
    total_anticipos_sin_facturar = 0
    total_anticipos_aplicados = 0
    
    for anticipo in anticipos_periodo_unicos:
        anticipo_caja = getattr(anticipo, 'caja_tramite', 'appot')
        
        # Aplicar filtro de caja si está seleccionado
        if caja_filtro and caja_filtro in ['appot', 'siigo'] and anticipo_caja != caja_filtro:
            continue
        
        if anticipo.venta_id:
            # Anticipo aplicado a una venta
            anticipos_aplicados_ventas.append(anticipo)
            total_anticipos_aplicados += float(anticipo.monto)
        else:
            # Anticipo de OT no facturada
            anticipos_sin_facturar.append(anticipo)
            # Sumar según método de pago y caja
            metodo = getattr(anticipo, 'metodo_pago', '').lower()
            caja = getattr(anticipo, 'caja_tramite', 'appot')
            
            # Para el cuadre de caja:
            # - AppOT: solo efectivo
            # - Siigo: todos los métodos (tarjeta, transferencia)
            if caja == 'appot' and metodo == 'efectivo':
                total_anticipos_sin_facturar += float(anticipo.monto)
            elif caja == 'siigo':  # Siigo acepta todos los métodos
                total_anticipos_sin_facturar += float(anticipo.monto)
    
    # Total de anticipos del período = todos los anticipos filtrados
    total_anticipos_periodo = len(anticipos_sin_facturar) + len(anticipos_aplicados_ventas)

    # Calcular valores individuales para todas las ventas (para mostrar en tabla)
    # y sumar solo las de AppOT para el total de caja
    total_ventas = 0
    for venta in ventas:
        # Compute detalles_total safely without touching venta.detalles (which may trigger missing-column queries)
        detalles_total = _detalles_total_for_venta(venta.id) or 0.0
        try:
            venta_total = float(venta.total or 0)
        except Exception:
            venta_total = 0.0
        if detalles_total and int(detalles_total) != int(venta_total):
            displayed_total = detalles_total
        else:
            displayed_total = venta_total or detalles_total
        descuento = float(getattr(venta, 'descuento', 0) or 0)
        # If descuento not set, infer from detalles_total vs venta.total
        if (not descuento or descuento == 0) and detalles_total and (venta_total is not None):
            inferred = int(detalles_total) - int(venta_total)
            if inferred > 0:
                descuento = float(inferred)
        anticipo = float(getattr(venta, 'anticipo_total', 0) or 0)
        # Neto = total - descuento (NO restamos anticipo porque es parte del pago recibido)
        neto = max(0.0, displayed_total - descuento)
        # Store computed values on the object for the template to use (avoids changing template much)
        setattr(venta, '_displayed_total', displayed_total)
        setattr(venta, '_descuento_val', descuento)
        setattr(venta, '_neto', neto)
        
        # Sumar en total_ventas según el filtro de caja seleccionado
        venta_caja = getattr(venta, 'caja_tramite', 'appot')
        if not caja_filtro or caja_filtro == '' or venta_caja == caja_filtro:
            total_ventas += neto
    
    # ===== TOTAL EFECTIVO EN CAJA (AppOT) =====
    # Regla de negocio:
    #   - AppOT (efectivo): cuenta en caja física
    #   - Siigo (tarjeta/transferencia): NO cuenta en AppOT (caja externa)
    # Total en caja = saldo cobrado al facturar + todos los anticipos AppOT efectivo del período
    
    # 1. Saldo cobrado de ventas AppOT (lo que pagaron al facturar)
    saldo_query = db.session.query(
        db.func.sum(Venta.saldo)
    ).filter(
        or_(Venta.eliminada == False, Venta.eliminada.is_(None)),
        Venta.caja_tramite == 'appot'
    )
    if sucursal_id:
        saldo_query = saldo_query.filter(Venta.branch_id == sucursal_id)
    if fecha_inicio and fecha_inicio.strip():
        fecha_inicio_dt = validar_fecha(fecha_inicio)
        if fecha_inicio_dt:
            try:
                import pytz
                fecha_inicio_utc = fecha_inicio_dt.astimezone(pytz.utc)
            except Exception:
                fecha_inicio_utc = fecha_inicio_dt
            saldo_query = saldo_query.filter(Venta.fecha >= fecha_inicio_utc)
    if fecha_fin and fecha_fin.strip():
        fecha_fin_dt = validar_fecha(fecha_fin)
        if fecha_fin_dt:
            fecha_fin_dt = fecha_fin_dt.replace(hour=23, minute=59, second=59)
            try:
                import pytz
                fecha_fin_utc = fecha_fin_dt.astimezone(pytz.utc)
            except Exception:
                fecha_fin_utc = fecha_fin_dt
            saldo_query = saldo_query.filter(Venta.fecha <= fecha_fin_utc)
    total_saldo_cobrado = float(saldo_query.scalar() or 0)
    
    # 2. Todos los anticipos AppOT efectivo del período (aplicados + sin facturar)
    total_anticipos_appot_query = db.session.query(
        db.func.sum(Anticipo.monto)
    ).filter(
        Anticipo.caja_tramite == 'appot',
        Anticipo.metodo_pago == 'efectivo'
    )
    if sucursal_id:
        total_anticipos_appot_query = _filtrar_anticipos_por_sucursal(total_anticipos_appot_query, sucursal_id)
    if fecha_inicio and fecha_inicio.strip():
        fecha_inicio_dt = validar_fecha(fecha_inicio)
        if fecha_inicio_dt:
            try:
                import pytz
                fecha_inicio_utc = fecha_inicio_dt.astimezone(pytz.utc)
            except Exception:
                fecha_inicio_utc = fecha_inicio_dt
            total_anticipos_appot_query = total_anticipos_appot_query.filter(Anticipo.fecha >= fecha_inicio_utc)
    if fecha_fin and fecha_fin.strip():
        fecha_fin_dt = validar_fecha(fecha_fin)
        if fecha_fin_dt:
            fecha_fin_dt = fecha_fin_dt.replace(hour=23, minute=59, second=59)
            try:
                import pytz
                fecha_fin_utc = fecha_fin_dt.astimezone(pytz.utc)
            except Exception:
                fecha_fin_utc = fecha_fin_dt
            total_anticipos_appot_query = total_anticipos_appot_query.filter(Anticipo.fecha <= fecha_fin_utc)
    total_anticipos_appot_todos = float(total_anticipos_appot_query.scalar() or 0)
    
    # 3. Total efectivo en caja AppOT
    total_ventas_acumulado = total_saldo_cobrado + total_anticipos_appot_todos
    
    # ===== TODOS LOS ANTICIPOS SIIGO DEL PERÍODO (aplicados + sin facturar) =====
    # Se muestran en la tarjeta informativa "Anticipos Siigo"
    total_anticipos_siigo_query = db.session.query(
        db.func.sum(Anticipo.monto)
    ).filter(
        Anticipo.caja_tramite == 'siigo'
    )
    if sucursal_id:
        total_anticipos_siigo_query = _filtrar_anticipos_por_sucursal(total_anticipos_siigo_query, sucursal_id)
    if fecha_inicio and fecha_inicio.strip():
        fecha_inicio_dt = validar_fecha(fecha_inicio)
        if fecha_inicio_dt:
            try:
                import pytz
                fecha_inicio_utc = fecha_inicio_dt.astimezone(pytz.utc)
            except Exception:
                fecha_inicio_utc = fecha_inicio_dt
            total_anticipos_siigo_query = total_anticipos_siigo_query.filter(Anticipo.fecha >= fecha_inicio_utc)
    if fecha_fin and fecha_fin.strip():
        fecha_fin_dt = validar_fecha(fecha_fin)
        if fecha_fin_dt:
            fecha_fin_dt = fecha_fin_dt.replace(hour=23, minute=59, second=59)
            try:
                import pytz
                fecha_fin_utc = fecha_fin_dt.astimezone(pytz.utc)
            except Exception:
                fecha_fin_utc = fecha_fin_dt
            total_anticipos_siigo_query = total_anticipos_siigo_query.filter(Anticipo.fecha <= fecha_fin_utc)
    total_anticipos_siigo = float(total_anticipos_siigo_query.scalar() or 0)
    if caja_filtro == 'appot':
        total_anticipos_siigo = 0.0
    
    # ===== ANTICIPOS APPOT SIN FACTURAR (para tarjeta informativa verde) =====
    # Solo los NO vinculados a una venta (venta_id IS NULL)
    anticipos_sin_fact_query = anticipos_query.filter(Anticipo.venta_id.is_(None))
    if caja_filtro and caja_filtro in ['appot', 'siigo']:
        anticipos_sin_fact_query = anticipos_sin_fact_query.filter(Anticipo.caja_tramite == caja_filtro)
    anticipos_sin_fact_list = anticipos_sin_fact_query.all()
    anticipos_unicos = {}
    for ant in anticipos_sin_fact_list:
        if ant.id not in anticipos_unicos:
            anticipos_unicos[ant.id] = ant
    
    total_anticipos_appot = 0.0
    for ant in anticipos_unicos.values():
        metodo = getattr(ant, 'metodo_pago', '').lower()
        caja = getattr(ant, 'caja_tramite', 'appot')
        monto = float(ant.monto)
        if caja == 'appot' and metodo == 'efectivo':
            total_anticipos_appot += monto
    if caja_filtro == 'siigo':
        total_anticipos_appot = 0.0

    # Obtener sucursales para el filtro: todos los roles ven todas las sucursales
    try:
        sucursales = Branch.query.order_by(Branch.nombre).all()
    except Exception:
        sucursales = []

    # Añadir logging: muestra rol, user id, branch y número de sucursales disponibles
    try:
        current_app.logger.info(f"reportes.ventas: user_id={user_id} role={role} user_branch={user_branch} filtros.sucursal_id={sucursal_id} sucursales_count={len(sucursales)}")
        current_app.logger.info(f"reportes.ventas: total_ventas_acumulado=${total_ventas_acumulado:,.0f} total_anticipos_sin_facturar_acum=${total_anticipos_sin_facturar_acum:,.0f}")
    except Exception:
        pass

    # Obtener los valores originales del request para mostrar en el template
    fecha_inicio_display = request.args.get('fecha_inicio', '')
    fecha_fin_display = request.args.get('fecha_fin', '')
    
    return render_template('reportes/ventas.html', 
                         ventas=ventas, 
                         total_ventas=total_ventas,
                         total_ventas_acumulado=total_ventas_acumulado,  # Pasar el total acumulado
                         anticipos_sin_facturar=anticipos_sin_facturar,
                         anticipos_aplicados_ventas=anticipos_aplicados_ventas,
                         total_anticipos_sin_facturar=total_anticipos_sin_facturar,
                         total_anticipos_aplicados=total_anticipos_aplicados,
                         total_anticipos_periodo=total_anticipos_periodo,
                         total_anticipos_appot=total_anticipos_appot,  # Nuevo: anticipos AppOT
                         total_anticipos_siigo=total_anticipos_siigo,  # Nuevo: anticipos Siigo
                         sucursales=sucursales,
                         ventas_pagination=ventas_pagination,
                         filtros={
                             'sucursal_id': sucursal_id,
                             'caja': caja_filtro,
                             'fecha_inicio': fecha_inicio_display,
                             'fecha_fin': fecha_fin_display
                         })

@reportes_bp.route('/ventas/print')
@login_required
@role_required('admin', 'supervisor', 'tecnico', 'vendedor')
def ventas_print():
    """Pagina de impresion POS para el reporte de ventas"""
    # Obtener filtros (misma logica que la ruta principal)
    sucursal_id = scoped_branch_param(request.args.get('sucursal', type=int))
    fecha_inicio = request.args.get('fecha_inicio')
    fecha_fin = request.args.get('fecha_fin')
    
    # Default: mes actual (mismo comportamiento que la ruta principal)
    if not fecha_inicio or fecha_inicio.strip() == '':
        fecha_inicio = date.today().replace(day=1).strftime('%d/%m/%Y')
    if not fecha_fin or fecha_fin.strip() == '':
        fecha_fin = date.today().strftime('%d/%m/%Y')
    
    # Base query - excluir ventas eliminadas (considerar NULL como no eliminada)
    query = Venta.query.filter(or_(Venta.eliminada == False, Venta.eliminada.is_(None)))
    
    # Aplicar filtros por rol
    # No filtrar ventas por rol: todos los roles pueden ver ventas de todas las sucursales
    
    # Aplicar filtros adicionales
    if sucursal_id:
        query = query.filter_by(branch_id=sucursal_id)
    
    if fecha_inicio:
        fecha_inicio_dt = validar_fecha(fecha_inicio)
        if fecha_inicio_dt:
            query = query.filter(Venta.fecha >= fecha_inicio_dt)
    
    if fecha_fin:
        fecha_fin_dt = validar_fecha(fecha_fin)
        if fecha_fin_dt:
            fecha_fin_dt = fecha_fin_dt.replace(hour=23, minute=59, second=59)
            query = query.filter(Venta.fecha <= fecha_fin_dt)
    
    # Obtener resultados
    ventas = query.order_by(Venta.fecha.desc()).all()
    
    # Calcular anticipos del período
    anticipos_query = Anticipo.query
    
    if fecha_inicio:
        fecha_inicio_dt = validar_fecha(fecha_inicio)
        if fecha_inicio_dt:
            anticipos_query = anticipos_query.filter(Anticipo.fecha >= fecha_inicio_dt)
    
    if fecha_fin:
        fecha_fin_dt = validar_fecha(fecha_fin)
        if fecha_fin_dt:
            fecha_fin_dt = fecha_fin_dt.replace(hour=23, minute=59, second=59)
            anticipos_query = anticipos_query.filter(Anticipo.fecha <= fecha_fin_dt)
    
    anticipos_query = _filtrar_anticipos_por_sucursal(anticipos_query, sucursal_id)
    
    anticipos_periodo = anticipos_query.all()
    
    # Separar anticipos y filtrar por caja de trámite
    anticipos_sin_facturar = []
    total_anticipos_sin_facturar = 0
    total_anticipos_aplicados = 0
    
    for anticipo in anticipos_periodo:
        if anticipo.venta_id:
            total_anticipos_aplicados += float(anticipo.monto)
        else:
            anticipos_sin_facturar.append(anticipo)
            # Solo sumar anticipos de AppOT en EFECTIVO (para cuadre de caja)
            metodo = getattr(anticipo, 'metodo_pago', '').lower()
            if getattr(anticipo, 'caja_tramite', 'appot') == 'appot' and metodo == 'efectivo':
                total_anticipos_sin_facturar += float(anticipo.monto)
    
    total_anticipos_periodo = total_anticipos_sin_facturar + total_anticipos_aplicados

    # Total de anticipos AppOT EFECTIVO sin facturar (para sumar al total en caja)
    # Solo anticipos NO vinculados a una venta: los vinculados ya están en Venta.total
    total_anticipos_appot = 0.0
    for anticipo in anticipos_periodo:
        if anticipo.venta_id is not None:
            continue
        metodo = getattr(anticipo, 'metodo_pago', '').lower()
        if getattr(anticipo, 'caja_tramite', 'appot') == 'appot' and metodo == 'efectivo':
            try:
                total_anticipos_appot += float(anticipo.monto)
            except Exception:
                pass
    # Lista de anticipos AppOT EFECTIVO sin facturar (para mostrar detalle en impresion)
    anticipos_appot = [a for a in anticipos_periodo 
                       if a.venta_id is None
                       and getattr(a, 'caja_tramite', 'appot') == 'appot' 
                       and getattr(a, 'metodo_pago', '').lower() == 'efectivo']
    
    # Compute values for all sales (for table display)
    # and sum only AppOT sales for cash register total
    total_ventas = 0.0
    for venta in ventas:
        detalles_total = _detalles_total_for_venta(venta.id) or 0.0
        try:
            venta_total = float(venta.total or 0)
        except Exception:
            venta_total = 0.0
        if detalles_total and int(detalles_total) != int(venta_total):
            displayed_total = detalles_total
        else:
            displayed_total = venta_total or detalles_total
        descuento = float(getattr(venta, 'descuento', 0) or 0)
        if (not descuento or descuento == 0) and detalles_total and (venta_total is not None):
            inferred = int(detalles_total) - int(venta_total)
            if inferred > 0:
                descuento = float(inferred)
        neto = max(0.0, displayed_total - descuento)
        setattr(venta, '_displayed_total', displayed_total)
        setattr(venta, '_descuento_val', descuento)
        setattr(venta, '_neto', neto)
        
        # Only add to total_ventas if it's AppOT (exclude Siigo)
        if getattr(venta, 'caja_tramite', 'appot') == 'appot':
            total_ventas += neto
    
    # Obtener nombre de sucursal para el filtro
    sucursal_nombre = None
    if sucursal_id:
        sucursal = Branch.query.get(sucursal_id)
        sucursal_nombre = sucursal.nombre if sucursal else None
    
    return render_template('reportes/ventas_print.html', 
                         ventas=ventas, 
                         total_ventas=total_ventas,
                         anticipos_sin_facturar=anticipos_sin_facturar,
                         anticipos_appot=anticipos_appot,
                         total_anticipos_sin_facturar=total_anticipos_sin_facturar,
                         total_anticipos_aplicados=total_anticipos_aplicados,
                         total_anticipos_periodo=total_anticipos_periodo,
                         total_anticipos_appot=total_anticipos_appot,
                         filtros={
                             'sucursal_id': sucursal_id,
                             'sucursal_nombre': sucursal_nombre,
                             'fecha_inicio': fecha_inicio,
                             'fecha_fin': fecha_fin
                         })

@reportes_bp.route('/reparaciones')
@login_required
def reparaciones():
    """
    Reporte de reparaciones con filtros por estado y rango de fechas.
    PERMISOS: Todos los usuarios (incluyendo vendedores) tienen acceso completo.
    Los vendedores tienen permisos de supervisor en esta ruta específica.
    """
    
    def calcular_total_orden(orden):
        total = 0
        for producto in orden.productos:
            total += float(producto.precio_unitario) * int(producto.cantidad)
        return total
    
    estado = request.args.get('estado')
    fecha_inicio = request.args.get('fecha_inicio')
    fecha_fin = request.args.get('fecha_fin')
    sitio_id_str = request.args.get('sitio')
    sitio_id = int(sitio_id_str) if sitio_id_str and sitio_id_str.isdigit() else None
    sucursal_id_str = request.args.get('sucursal')
    sucursal_id = int(sucursal_id_str) if sucursal_id_str and sucursal_id_str.isdigit() else None
    # Scoping por sucursal: roles restringidos solo ven su sucursal
    sucursal_id = scoped_branch_param(sucursal_id)
    
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)
    
    # Query base — solo joinedload para relaciones many-to-one (seguras)
    query = OrdenTrabajo.query.options(
        db.joinedload(OrdenTrabajo.client),
        db.joinedload(OrdenTrabajo.branch),
        db.joinedload(OrdenTrabajo.tecnico),
        db.subqueryload(OrdenTrabajo.productos)
    )
    
    # outerjoin a Venta solo cuando el filtro de estado lo requiere
    if estado:
        estado_norm = estado.lower()
        if estado_norm == 'facturado':
            query = query.outerjoin(Venta, Venta.orden_id == OrdenTrabajo.id)
            query = query.filter(
                or_(func.lower(OrdenTrabajo.estado) == 'facturado', Venta.id != None)
            )
        elif estado_norm == 'finalizado_no_facturado':
            query = query.outerjoin(Venta, Venta.orden_id == OrdenTrabajo.id)
            query = query.filter(func.lower(OrdenTrabajo.estado) == 'finalizado').filter(Venta.id == None)
        else:
            query = query.filter(func.lower(OrdenTrabajo.estado) == estado_norm)
    
    if sitio_id:
        query = query.filter(OrdenTrabajo.tecnico_id == sitio_id)
    
    if sucursal_id:
        query = query.filter(OrdenTrabajo.branch_id == sucursal_id)
    
    if fecha_inicio:
        fecha_inicio_dt = validar_fecha(fecha_inicio)
        if fecha_inicio_dt:
            query = query.filter(OrdenTrabajo.fecha_creacion >= fecha_inicio_dt)
    
    if fecha_fin:
        fecha_fin_dt = validar_fecha(fecha_fin)
        if fecha_fin_dt:
            fecha_fin_dt = fecha_fin_dt.replace(hour=23, minute=59, second=59)
            query = query.filter(OrdenTrabajo.fecha_creacion <= fecha_fin_dt)
    
    # Una sola ejecución: cargar TODO
    todas_las_ordenes = query.order_by(OrdenTrabajo.branch_id, OrdenTrabajo.fecha_creacion.desc()).all()
    
    # Batch query: saber qué ordenes tienen Venta asociada (una query, no N)
    orden_ids = [o.id for o in todas_las_ordenes]
    if orden_ids:
        venta_orden_ids = set(
            row[0] for row in db.session.query(Venta.orden_id)
            .filter(Venta.orden_id.in_(orden_ids))
            .all()
        )
    else:
        venta_orden_ids = set()
    
    # Paginación manual (sin paginate() que duplica queries y se confunde con joins)
    total = len(todas_las_ordenes)
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = max(1, min(page, total_pages))
    start = (page - 1) * per_page
    end = min(start + per_page, total)
    ordenes = todas_las_ordenes[start:end] if todas_las_ordenes else []
    
    class PaginationInfo:
        def __init__(self):
            self.page = page
            self.per_page = per_page
            self.total = total
            self.pages = total_pages
            self.items = ordenes
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
    
    ordenes_pagination = PaginationInfo()
    
    # Calcular estadísticas — usa venta_orden_ids (en memoria, cero queries)
    stats = {
        'total': total,
        'pendiente': 0,
        'en_proceso': 0,
        'finalizado': 0,
        'facturado': 0,
        'finalizado_no_facturado': 0,
        'total_valor': 0,
        'valor_facturado': 0,
        'valor_pendiente': 0
    }
    
    for orden in todas_las_ordenes:
        estado_ot = (orden.estado or '').lower()
        esta_facturada = orden.id in venta_orden_ids or estado_ot == 'facturado'
        
        if estado_ot == 'pendiente':
            stats['pendiente'] += 1
        elif estado_ot == 'en_proceso':
            stats['en_proceso'] += 1
        elif estado_ot == 'finalizado':
            stats['finalizado'] += 1
            if not esta_facturada:
                stats['finalizado_no_facturado'] += 1
        elif estado_ot == 'facturado':
            stats['facturado'] += 1
        
        valor_orden = calcular_total_orden(orden)
        stats['total_valor'] += valor_orden
        
        if esta_facturada:
            stats['valor_facturado'] += valor_orden
        else:
            stats['valor_pendiente'] += valor_orden
    
    sitios = User.query.filter_by(es_sitio_reparacion=True).order_by(User.username).all()
    sucursales = Branch.query.order_by(Branch.nombre).all()
    
    estados_disponibles = [
        ('', 'Todos los estados'),
        ('pendiente', 'Pendiente'),
        ('en_proceso', 'En Proceso'),
        ('finalizado', 'Finalizado'),
        ('finalizado_no_facturado', 'Finalizado (No Facturado)'),
        ('facturado', 'Facturado')
    ]
    
    return render_template('reportes/reparaciones.html', 
                         ordenes=ordenes, 
                         stats=stats,
                         sitios=sitios,
                         sucursales=sucursales,
                         estados_disponibles=estados_disponibles,
                         ordenes_pagination=ordenes_pagination,
                         filtros={
                             'estado': estado,
                             'sitio_id': sitio_id,
                             'sucursal_id': sucursal_id,
                             'fecha_inicio': fecha_inicio,
                             'fecha_fin': fecha_fin
                         },
                         calcular_total_orden=calcular_total_orden)


@reportes_bp.route('/reparaciones/print')
@login_required
def reparaciones_print():
    """
    Versión imprimible del reporte de reparaciones.
    """
    # Obtener parametros de filtro
    estado = request.args.get('estado')
    fecha_inicio = request.args.get('fecha_inicio')
    fecha_fin = request.args.get('fecha_fin')
    sitio_id_str = request.args.get('sitio')
    sitio_id = int(sitio_id_str) if sitio_id_str and sitio_id_str.isdigit() else None
    sucursal_id_str = request.args.get('sucursal')
    sucursal_id = int(sucursal_id_str) if sucursal_id_str and sucursal_id_str.isdigit() else None
    # Scoping por sucursal: roles restringidos solo ven su sucursal
    sucursal_id = scoped_branch_param(sucursal_id)

    # Función auxiliar para calcular el total de una orden
    def calcular_total_orden(orden):
        total = 0
        for producto in orden.productos:
            total += float(producto.precio_unitario) * int(producto.cantidad)
        return total
    
    # Función auxiliar para calcular el total de repuestos de una orden
    def calcular_total_repuestos(orden):
        total = 0
        try:
            if hasattr(orden, 'repuestos_instalados'):
                repuestos = orden.repuestos_instalados.all() if hasattr(orden.repuestos_instalados, 'all') else orden.repuestos_instalados
                for repuesto in repuestos:
                    total += float(repuesto.costo_total or 0)
        except:
            pass
        return total

    # Query base con join opcional a Venta (repuestos_instalados no se puede precargar porque es lazy='dynamic')
    query = OrdenTrabajo.query.options(
        db.joinedload(OrdenTrabajo.client),
        db.joinedload(OrdenTrabajo.branch),
        db.joinedload(OrdenTrabajo.tecnico),
        db.joinedload(OrdenTrabajo.productos)
    ).outerjoin(Venta, Venta.orden_id == OrdenTrabajo.id)

    # Aplicar filtros de estado
    if estado:
        estado_norm = estado.lower()
        if estado_norm == 'facturado':
            query = query.filter(
                or_(func.lower(OrdenTrabajo.estado) == 'facturado', Venta.id != None)
            )
        elif estado_norm == 'finalizado_no_facturado':
            query = query.filter(func.lower(OrdenTrabajo.estado) == 'finalizado').filter(Venta.id == None)
        else:
            query = query.filter(func.lower(OrdenTrabajo.estado) == estado_norm)

    if sitio_id:
        query = query.filter(OrdenTrabajo.tecnico_id == sitio_id)
    
    if sucursal_id:
        query = query.filter(OrdenTrabajo.branch_id == sucursal_id)

    # Aplicar filtros de fecha
    if fecha_inicio:
        fecha_inicio_dt = validar_fecha(fecha_inicio)
        if fecha_inicio_dt:
            query = query.filter(OrdenTrabajo.fecha_creacion >= fecha_inicio_dt)
    
    if fecha_fin:
        fecha_fin_dt = validar_fecha(fecha_fin)
        if fecha_fin_dt:
            fecha_fin_dt = fecha_fin_dt.replace(hour=23, minute=59, second=59)
            query = query.filter(OrdenTrabajo.fecha_creacion <= fecha_fin_dt)    # Obtener ordenes ordenadas por sucursal y fecha de creación descendente
    ordenes = query.order_by(OrdenTrabajo.branch_id, OrdenTrabajo.fecha_creacion.desc()).all()

    # Calcular anticipos del período
    anticipos_query = Anticipo.query.join(OrdenTrabajo)
    
    if fecha_inicio:
        fecha_inicio_dt = validar_fecha(fecha_inicio)
        if fecha_inicio_dt:
            anticipos_query = anticipos_query.filter(Anticipo.fecha >= fecha_inicio_dt)
    
    if fecha_fin:
        fecha_fin_dt = validar_fecha(fecha_fin)
        if fecha_fin_dt:
            fecha_fin_dt = fecha_fin_dt.replace(hour=23, minute=59, second=59)
            anticipos_query = anticipos_query.filter(Anticipo.fecha <= fecha_fin_dt)
    
    if sucursal_id:
        anticipos_query = anticipos_query.filter(OrdenTrabajo.branch_id == sucursal_id)
    
    if sitio_id:
        anticipos_query = anticipos_query.filter(OrdenTrabajo.tecnico_id == sitio_id)
    
    anticipos_periodo = anticipos_query.all()
    
    # Separar anticipos por método de pago
    anticipos_appot = []  # Efectivo
    anticipos_siigo = []  # Tarjeta/Transferencia
    
    for anticipo in anticipos_periodo:
        metodo = (anticipo.metodo_pago or '').lower()
        if metodo in ['efectivo', 'cash']:
            anticipos_appot.append(anticipo)
        else:
            anticipos_siigo.append(anticipo)
    
    total_anticipos_appot = sum(float(a.monto) for a in anticipos_appot)
    total_anticipos_siigo = sum(float(a.monto) for a in anticipos_siigo)

    # Calcular estadísticas simples para impresión
    stats = {
        'total': len(ordenes),
        'finalizado_no_facturado': 0,
        'facturado': 0,
        'total_valor': 0,
        'total_repuestos': 0
    }

    for orden in ordenes:
        estado_ot = (orden.estado or '').lower()
        esta_facturada = (estado_ot == 'facturado' or orden.venta_rel)

        if estado_ot == 'finalizado' and not esta_facturada:
            stats['finalizado_no_facturado'] += 1
        elif esta_facturada:
            stats['facturado'] += 1

        stats['total_valor'] += calcular_total_orden(orden)
        stats['total_repuestos'] += calcular_total_repuestos(orden)

    # Nombre del sitio si aplica
    sitio_nombre = None
    if sitio_id:
        sitio = User.query.get(sitio_id)
        sitio_nombre = sitio.username if sitio else None

    # Nombre de la sucursal si aplica
    sucursal_nombre = None
    if sucursal_id:
        sucursal = Branch.query.get(sucursal_id)
        sucursal_nombre = sucursal.nombre if sucursal else None
    
    # Preparar lista de órdenes con repuestos para el template
    ordenes_con_repuestos = []
    for orden in ordenes:
        try:
            repuestos_list = orden.repuestos_instalados.all() if orden.repuestos_instalados else []
            if repuestos_list:
                ordenes_con_repuestos.append({
                    'orden': orden,
                    'repuestos': repuestos_list
                })
        except:
            pass

    return render_template('reportes/reparaciones_print.html',
                         ordenes=ordenes,
                         stats=stats,
                         ordenes_con_repuestos=ordenes_con_repuestos,
                         filtros={
                             'estado': estado,
                             'sitio_id': sitio_id,
                             'sitio_nombre': sitio_nombre,
                             'sucursal_id': sucursal_id,
                             'sucursal_nombre': sucursal_nombre,
                             'fecha_inicio': fecha_inicio,
                             'fecha_fin': fecha_fin
                         },
                         calcular_total_orden=calcular_total_orden,
                         calcular_total_repuestos=calcular_total_repuestos)

@reportes_bp.route('/anticipos')
@login_required
def anticipos():
    sucursal_id = scoped_branch_param(request.args.get('sucursal', type=int))
    fecha_desde = request.args.get('desde', '')
    fecha_hasta = request.args.get('hasta', '')
    
    # Parámetros de paginación
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 25, type=int)
    
    query = Anticipo.query.join(OrdenTrabajo).join(Client).outerjoin(Branch, OrdenTrabajo.branch_id == Branch.id)
    query = _filtrar_anticipos_por_sucursal(query, sucursal_id)
    if fecha_desde:
        try:
            desde = datetime.strptime(fecha_desde, '%Y-%m-%d')
            query = query.filter(Anticipo.fecha >= desde)
        except:
            pass
    if fecha_hasta:
        try:
            hasta = datetime.strptime(fecha_hasta, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
            query = query.filter(Anticipo.fecha <= hasta)
        except:
            pass
    
    anticipos_pagination = query.order_by(Anticipo.fecha.desc()).paginate(page=page, per_page=per_page, error_out=False)
    anticipos = anticipos_pagination.items
    
    branches = Branch.query.all()
    
    # Calcular totales por tipo de caja sobre todos los anticipos filtrados (sin paginación)
    total_query = Anticipo.query.join(OrdenTrabajo).join(Client).outerjoin(Branch, OrdenTrabajo.branch_id == Branch.id)
    total_query = _filtrar_anticipos_por_sucursal(total_query, sucursal_id)
    if fecha_desde:
        try:
            desde = datetime.strptime(fecha_desde, '%Y-%m-%d')
            total_query = total_query.filter(Anticipo.fecha >= desde)
        except:
            pass
    if fecha_hasta:
        try:
            hasta = datetime.strptime(fecha_hasta, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
            total_query = total_query.filter(Anticipo.fecha <= hasta)
        except:
            pass
    
    all_anticipos = total_query.all()
    total_appot = sum(a.monto for a in all_anticipos if getattr(a, 'caja_tramite', 'appot') == 'appot')
    total_siigo = sum(a.monto for a in all_anticipos if getattr(a, 'caja_tramite', 'appot') == 'siigo')
    total_general = total_appot + total_siigo
    
    return render_template('reportes/anticipos.html', 
                           anticipos=anticipos, 
                           anticipos_pagination=anticipos_pagination,
                           branches=branches,
                           total_appot=total_appot, 
                           total_siigo=total_siigo, 
                           total_general=total_general)