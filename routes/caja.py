# routes/caja.py

from flask import Blueprint, render_template, redirect, url_for, flash, request, session, current_app, jsonify
from flask_login import current_user, login_required
from datetime import datetime, timedelta
from extensions import db
from models.models import (
    CierreCaja, CajaMovimiento, Venta, Anticipo, Branch, User
)
from utils.decorators import role_required
from utils.timezone_utils import get_local_now, utc_to_local, local_to_utc, COLOMBIA_TZ
from sqlalchemy import func, and_

bp = Blueprint('caja', __name__, url_prefix='/caja')

@bp.route('/cuadre')
@login_required
@role_required('admin', 'supervisor', 'vendedor')
def cuadre():
    """Mostrar el cuadre de caja del dia actual o fecha especifica"""
    branch_id = session.get("branch_id")
    if not branch_id:
        flash("Debes seleccionar una sucursal antes de continuar", "warning")
        return redirect(url_for("sales.seleccionar_sucursal"))
    
    # Obtener fecha del parametro o usar hoy (fecha mostrada en zona local Colombia)
    fecha_str = request.args.get('fecha', utc_to_local(get_local_now()).strftime('%Y-%m-%d'))
    try:
        # Interpretamos la fecha recibida como fecha local (America/Bogota)
        fecha_naive = datetime.strptime(fecha_str, '%Y-%m-%d')
        fecha_local = COLOMBIA_TZ.localize(fecha_naive)
    except ValueError:
        # Si hay error, usar la fecha local de ahora
        fecha_local = utc_to_local(get_local_now())

    # Convertir el rango local (midnight..23:59:59) a UTC para las consultas
    fecha_inicio_local = fecha_local.replace(hour=0, minute=0, second=0, microsecond=0)
    fecha_fin_local = fecha_local.replace(hour=23, minute=59, second=59, microsecond=999999)

    fecha_inicio = local_to_utc(fecha_inicio_local)
    fecha_fin = local_to_utc(fecha_fin_local)
    
    # Verificar si ya existe un cierre para esta fecha
    cierre_existente = CierreCaja.query.filter(
        CierreCaja.branch_id == branch_id,
        CierreCaja.fecha_inicio >= fecha_inicio,
        CierreCaja.fecha_fin <= fecha_fin
    ).first()
    
    # Calcular datos del cuadre
    # Si ya hay un cierre, usar los valores almacenados (congelados) para que
    # aplicar anticipos posteriormente no cambie el cuadre de días pasados
    if cierre_existente:
        cuadre_data = {
            'total_ventas': float(cierre_existente.total_ventas or 0),
            'total_anticipos': float(cierre_existente.total_anticipos or 0),
            'total_saldo_cobrado': float(cierre_existente.total_ventas or 0),
            'total_ingresos_extra': float(cierre_existente.total_ingresos_extra or 0),
            'total_egresos': float(cierre_existente.total_egresos or 0),
            'efectivo_esperado': float(cierre_existente.total_efectivo_esperado or 0),
            'ventas_detalle': [],
            'anticipos_detalle': [],
            'anticipos_siigo_detalle': [],
            'total_anticipos_siigo': 0,
            'movimientos': [],
            'cantidad_ventas': 0,
            'congelado': True,
            'efectivo_contado': float(cierre_existente.efectivo_contado) if cierre_existente.efectivo_contado else 0,
            'diferencia': float(cierre_existente.diferencia or 0),
        }
    else:
        cuadre_data = calcular_cuadre(branch_id, fecha_inicio, fecha_fin)
        cuadre_data['congelado'] = False
    
    sucursal = Branch.query.get(branch_id)
    
    return render_template('caja/cuadre.html', 
                         cuadre=cuadre_data,
                         fecha=utc_to_local(get_local_now()) if 'fecha_local' not in locals() else fecha_local,
                         sucursal=sucursal,
                         cierre_existente=cierre_existente)

@bp.route('/corregir_ventas_hoy', methods=['POST'])
@login_required
@role_required('admin', 'supervisor')
def corregir_ventas_hoy():
    """Endpoint temporal: Corregir ventas de hoy asignadas incorrectamente a Siigo"""
    
    # Seguridad: Solo admin y supervisor
    if current_user.rol not in ('admin', 'supervisor'):
        return jsonify({'error': 'No autorizado'}), 403
    
    branch_id = session.get("branch_id")
    if not branch_id:
        return jsonify({'error': 'Debes seleccionar una sucursal'}), 400
    
    # Obtener rango de hoy
    now = get_local_now()
    fecha_inicio_local = now.replace(hour=0, minute=0, second=0, microsecond=0)
    fecha_fin_local = now.replace(hour=23, minute=59, second=59, microsecond=999999)
    
    fecha_inicio = local_to_utc(fecha_inicio_local)
    fecha_fin = local_to_utc(fecha_fin_local)
    
    # Buscar ventas de hoy con caja_tramite='siigo' y orden_id en esta sucursal
    ventas_a_corregir = db.session.query(Venta).filter(
        and_(
            Venta.branch_id == branch_id,
            Venta.fecha >= fecha_inicio,
            Venta.fecha <= fecha_fin,
            Venta.caja_tramite == 'siigo',
            Venta.orden_id.isnot(None)
        )
    ).all()
    
    if not ventas_a_corregir:
        return jsonify({
            'success': True,
            'mensaje': 'No hay ventas de hoy que corregir en esta sucursal',
            'cantidad': 0
        })
    
    # Corregir cada venta
    try:
        for v in ventas_a_corregir:
            v.caja_tramite = 'appot'
        
        db.session.commit()
        
        detalles = []
        for v in ventas_a_corregir:
            detalles.append({
                'numero_factura': v.numero_factura or v.id,
                'total': float(v.total),
                'orden': v.orden.consecutivo if v.orden else 'N/A'
            })
        
        return jsonify({
            'success': True,
            'mensaje': f'{len(ventas_a_corregir)} ventas corregidas',
            'cantidad': len(ventas_a_corregir),
            'detalles': detalles
        })
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception("Error corrigiendo ventas de hoy")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@bp.route('/revisar_ventas_hoy')
@login_required
@role_required('admin', 'supervisor')
def revisar_ventas_hoy():
    """Endpoint temporal: Revisar todas las ventas de hoy en esta sucursal"""
    
    branch_id = session.get("branch_id")
    if not branch_id:
        return jsonify({'error': 'Debes seleccionar una sucursal'}), 400
    
    # Obtener rango de hoy
    now = get_local_now()
    fecha_inicio_local = now.replace(hour=0, minute=0, second=0, microsecond=0)
    fecha_fin_local = now.replace(hour=23, minute=59, second=59, microsecond=999999)
    
    fecha_inicio = local_to_utc(fecha_inicio_local)
    fecha_fin = local_to_utc(fecha_fin_local)
    
    # Ver TODAS las ventas de hoy con orden
    todas_ventas = db.session.query(Venta).filter(
        and_(
            Venta.branch_id == branch_id,
            Venta.fecha >= fecha_inicio,
            Venta.fecha <= fecha_fin,
            Venta.orden_id.isnot(None)
        )
    ).all()
    
    # Ver solo las que necesitan corrección
    ventas_a_corregir = [v for v in todas_ventas if v.caja_tramite == 'siigo']
    
    detalles_todas = []
    for v in todas_ventas:
        detalles_todas.append({
            'id': v.id,
            'numero_factura': v.numero_factura or v.id,
            'total': float(v.total),
            'caja_tramite': v.caja_tramite,
            'orden': v.orden.consecutivo if v.orden else 'N/A',
            'cliente': v.cliente.nombre if v.cliente else 'N/A'
        })
    
    return jsonify({
        'total_ventas': len(todas_ventas),
        'ventas_a_corregir': len(ventas_a_corregir),
        'detalles': detalles_todas
    })

@bp.route('/cerrar_turno', methods=['POST'])
@login_required
@role_required('admin', 'supervisor')
def cerrar_turno():
    """Cerrar el turno/cuadre de caja"""
    branch_id = session.get("branch_id")
    if not branch_id:
        flash("Debes seleccionar una sucursal", "error")
        return redirect(url_for("caja.cuadre"))
    
    fecha_str = request.form.get('fecha', utc_to_local(get_local_now()).strftime('%Y-%m-%d'))
    efectivo_contado = float(request.form.get('efectivo_contado', 0) or 0)
    observaciones = request.form.get('observaciones', '').strip()
    
    try:
        fecha_naive = datetime.strptime(fecha_str, '%Y-%m-%d')
        fecha_local = COLOMBIA_TZ.localize(fecha_naive)
    except ValueError:
        fecha_local = utc_to_local(get_local_now())

    fecha_inicio_local = fecha_local.replace(hour=0, minute=0, second=0, microsecond=0)
    fecha_fin_local = fecha_local.replace(hour=23, minute=59, second=59, microsecond=999999)

    fecha_inicio = local_to_utc(fecha_inicio_local)
    fecha_fin = local_to_utc(fecha_fin_local)
    
    # Verificar si ya existe un cierre
    cierre_existente = CierreCaja.query.filter(
        CierreCaja.branch_id == branch_id,
        CierreCaja.fecha_inicio >= fecha_inicio,
        CierreCaja.fecha_fin <= fecha_fin
    ).first()
    
    if cierre_existente:
        flash("Ya existe un cierre para esta fecha", "warning")
        return redirect(url_for("caja.cuadre", fecha=fecha_str))
    
    # Calcular totales
    cuadre_data = calcular_cuadre(branch_id, fecha_inicio, fecha_fin)
    diferencia = efectivo_contado - float(cuadre_data['efectivo_esperado'])
    
    # Crear el cierre
    cierre = CierreCaja(
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        branch_id=branch_id,
        usuario_id=current_user.id,
        total_ventas=cuadre_data['total_ventas'],
        total_anticipos=cuadre_data['total_anticipos'],
        total_ingresos_extra=cuadre_data['total_ingresos_extra'],
        total_egresos=cuadre_data['total_egresos'],
        total_efectivo_esperado=cuadre_data['efectivo_esperado'],
        efectivo_contado=efectivo_contado,
        diferencia=diferencia,
        estado='cerrado',
        observaciones=observaciones
    )
    
    try:
        db.session.add(cierre)
        db.session.commit()
        flash(f"Cierre de caja registrado. Diferencia: ${diferencia:,.0f}".replace(",", "."), "success")
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception("Error al cerrar caja")
        flash("Error al registrar el cierre de caja", "error")
    
    return redirect(url_for("caja.cuadre", fecha=fecha_str))

@bp.route('/historial')
@login_required
@role_required('admin', 'supervisor')
def historial():
    """Historial de cierres de caja"""
    branch_id = session.get("branch_id")
    if not branch_id:
        flash("Debes seleccionar una sucursal", "warning")
        return redirect(url_for("sales.seleccionar_sucursal"))
    
    # Filtros
    fecha_desde = request.args.get('fecha_desde')
    fecha_hasta = request.args.get('fecha_hasta')
    
    query = CierreCaja.query.filter(CierreCaja.branch_id == branch_id)
    
    if fecha_desde:
        try:
            fecha_desde_dt = datetime.strptime(fecha_desde, '%d/%m/%Y')
            query = query.filter(CierreCaja.fecha_inicio >= fecha_desde_dt)
        except ValueError:
            pass
    
    if fecha_hasta:
        try:
            fecha_hasta_dt = datetime.strptime(fecha_hasta, '%d/%m/%Y').replace(hour=23, minute=59, second=59)
            query = query.filter(CierreCaja.fecha_fin <= fecha_hasta_dt)
        except ValueError:
            pass
    
    cierres = query.order_by(CierreCaja.fecha_cierre.desc()).limit(50).all()
    sucursal = Branch.query.get(branch_id)
    
    return render_template('caja/historial.html', cierres=cierres, sucursal=sucursal)

def _anticipo_branch_filter(query, branch_id):
    """Filtra anticipos por branch_id.
    - Si branch_id está fijado en el anticipo, se usa ese valor directamente.
    - Solo para registros históricos con branch_id NULL se recae en la sucursal de la OT.
    Esto evita que anticipos registrados por usuarios de otra sucursal aparezcan en el
    cuadre de la sucursal dueña de la OT.
    """
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

def calcular_cuadre(branch_id, fecha_inicio, fecha_fin):
    """Calcular los datos del cuadre de caja para un periodo"""
    from models.models import OrdenTrabajo

    # --- VENTAS ---
    # total_ventas: valor económico completo (sum de Venta.total)
    ventas_total = db.session.query(func.sum(Venta.total)).filter(
        Venta.branch_id == branch_id,
        Venta.fecha >= fecha_inicio,
        Venta.fecha <= fecha_fin,
        Venta.caja_tramite == 'appot'
    ).scalar() or 0

    # saldo_cobrado: efectivo que realmente entró hoy por saldos pendientes (sum de Venta.saldo)
    saldo_cobrado = db.session.query(func.sum(Venta.saldo)).filter(
        Venta.branch_id == branch_id,
        Venta.fecha >= fecha_inicio,
        Venta.fecha <= fecha_fin,
        Venta.caja_tramite == 'appot'
    ).scalar() or 0

    # --- ANTICIPOS ---
    # Todos los anticipos AppOT registrados hoy (estén o no aplicados a una venta)
    # Esto captura el efectivo que entró por anticipos, incluso si se aplicaron el mismo día
    anticipos_hoy_query = Anticipo.query.filter(
        Anticipo.fecha >= fecha_inicio,
        Anticipo.fecha <= fecha_fin,
        Anticipo.caja_tramite == 'appot',
        Anticipo.metodo_pago == 'efectivo'
    )
    anticipos_hoy_query = _anticipo_branch_filter(anticipos_hoy_query, branch_id)
    anticipos_hoy = anticipos_hoy_query.with_entities(func.sum(Anticipo.monto)).scalar() or 0

    # Anticipos Siigo del día (solo informativo, no afectan caja AppOT)
    anticipos_siigo_hoy_query = Anticipo.query.filter(
        Anticipo.fecha >= fecha_inicio,
        Anticipo.fecha <= fecha_fin,
        Anticipo.caja_tramite == 'siigo',
        Anticipo.metodo_pago.in_(['tarjeta', 'transferencia'])
    )
    anticipos_siigo_hoy_query = _anticipo_branch_filter(anticipos_siigo_hoy_query, branch_id)
    anticipos_siigo_hoy = anticipos_siigo_hoy_query.with_entities(func.sum(Anticipo.monto)).scalar() or 0

    if anticipos_siigo_hoy > 0:
        current_app.logger.info(
            f"INFO: ${anticipos_siigo_hoy} en anticipos de tarjeta/transferencia sin facturar "
            "(contabilizados en Siigo, NO en AppOT)"
        )

    # Validación: anticipos con metodo_pago NULL
    anticipos_nulos_query = Anticipo.query.filter(
        Anticipo.fecha >= fecha_inicio,
        Anticipo.fecha <= fecha_fin,
        Anticipo.metodo_pago.is_(None)
    )
    anticipos_nulos_query = _anticipo_branch_filter(anticipos_nulos_query, branch_id)
    anticipos_nulos_count = anticipos_nulos_query.count()
    if anticipos_nulos_count > 0:
        current_app.logger.warning(
            f"ADVERTENCIA: {anticipos_nulos_count} anticipos con metodo_pago NULL encontrados "
            f"en sucursal {branch_id}. Revisa la BD."
        )

    # --- MOVIMIENTOS DE CAJA ---
    ingresos_extra = db.session.query(func.sum(CajaMovimiento.monto)).filter(
        CajaMovimiento.tipo == 'ingreso',
        CajaMovimiento.fecha >= fecha_inicio,
        CajaMovimiento.fecha <= fecha_fin
    ).scalar() or 0

    egresos = db.session.query(func.sum(CajaMovimiento.monto)).filter(
        CajaMovimiento.tipo == 'egreso',
        CajaMovimiento.fecha >= fecha_inicio,
        CajaMovimiento.fecha <= fecha_fin
    ).scalar() or 0

    # efectivo_esperado = saldo_cobrado_hoy + anticipos_nuevos_hoy + ingresos_extra - egresos
    # saldo_cobrado: lo que pagó el cliente al facturar (el saldo restante)
    # anticipos_hoy: los anticipos que se registraron hoy (efectivo que entró por adelantos)
    efectivo_esperado = float(saldo_cobrado) + float(anticipos_hoy) + float(ingresos_extra) - float(egresos)

    # --- DETALLES PARA MOSTRAR ---
    ventas_detalle = Venta.query.filter(
        Venta.branch_id == branch_id,
        Venta.fecha >= fecha_inicio,
        Venta.fecha <= fecha_fin,
        Venta.caja_tramite == 'appot'
    ).order_by(Venta.fecha.desc()).all()

    # Todos los anticipos del día (sin filtrar por venta_id)
    anticipos_detalle_query = Anticipo.query.filter(
        Anticipo.fecha >= fecha_inicio,
        Anticipo.fecha <= fecha_fin,
        Anticipo.caja_tramite == 'appot',
        Anticipo.metodo_pago == 'efectivo'
    )
    anticipos_detalle_query = _anticipo_branch_filter(anticipos_detalle_query, branch_id)
    anticipos_detalle = anticipos_detalle_query.order_by(Anticipo.fecha.desc()).all()

    movimientos = CajaMovimiento.query.filter(
        CajaMovimiento.fecha >= fecha_inicio,
        CajaMovimiento.fecha <= fecha_fin
    ).order_by(CajaMovimiento.fecha.desc()).all()

    # Anticipos Siigo del día (solo informativo)
    anticipos_siigo_query_detalle = Anticipo.query.filter(
        Anticipo.fecha >= fecha_inicio,
        Anticipo.fecha <= fecha_fin,
        Anticipo.caja_tramite == 'siigo',
        Anticipo.metodo_pago.in_(['tarjeta', 'transferencia'])
    )
    anticipos_siigo_query_detalle = _anticipo_branch_filter(anticipos_siigo_query_detalle, branch_id)
    anticipos_siigo_detalle = anticipos_siigo_query_detalle.order_by(Anticipo.fecha.desc()).all()

    return {
        'total_ventas': float(ventas_total),          # valor completo de las ventas
        'total_anticipos': float(anticipos_hoy),       # anticipos registrados hoy (efectivo AppOT)
        'total_saldo_cobrado': float(saldo_cobrado),   # saldo cobrado hoy en ventas
        'total_ingresos_extra': float(ingresos_extra),
        'total_egresos': float(egresos),
        'efectivo_esperado': efectivo_esperado,        # = saldo_cobrado + anticipos_hoy + ingresos - egresos
        'ventas_detalle': ventas_detalle,
        'anticipos_detalle': anticipos_detalle,         # todos los anticipos del día
        'anticipos_siigo_detalle': anticipos_siigo_detalle,
        'total_anticipos_siigo': float(anticipos_siigo_hoy),
        'movimientos': movimientos,
        'cantidad_ventas': len(ventas_detalle)
    }