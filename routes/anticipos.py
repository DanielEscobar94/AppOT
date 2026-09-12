from flask import Blueprint, request, redirect, url_for, flash, jsonify, current_app
from utils.decorators import require_branch_access
from flask_login import login_required, current_user
from extensions import db
from models.models import Anticipo, Client

anticipos_bp = Blueprint("anticipos", __name__, url_prefix="/anticipos")

@anticipos_bp.route('/nuevo', methods=['POST'])
@login_required
def nuevo_anticipo():
    # Support two flows:
    # - from sales.nueva: provide 'cliente' and 'monto' (legacy)
    # - from ordenes/editar: provide 'orden_id', 'monto', 'metodo_pago' and optional ajax flag -> return JSON
    orden_id = request.form.get('orden_id', type=int)
    monto = request.form.get('monto', type=float)
    metodo = request.form.get('metodo_pago') or request.form.get('metodo') or request.form.get('metodoPago')

    if not monto or monto <= 0:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json:
            return jsonify({'ok': False, 'error': 'Monto invalido'}), 400
        flash('Monto invalido', 'danger')
        return redirect(url_for('sales.nueva'))

    # VALIDACIÓN CRÍTICA: Asegurar que metodo_pago NUNCA sea NULL
    # Esto previene descuadres en el cuadre de caja
    if not metodo or not str(metodo).strip():
        metodo = 'efectivo'  # Default si no se proporciona
        current_app.logger.warning(
            f"ADVERTENCIA: nuevo_anticipo llamado sin metodo_pago. Usando default 'efectivo'."
        )

    try:
        if orden_id:
            # Associate anticipo to a specific order
            from models.models import OrdenTrabajo
            orden = OrdenTrabajo.query.get(orden_id)
            if not orden:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json:
                    return jsonify({'ok': False, 'error': 'Orden no encontrada'}), 404
                flash('Orden no encontrada', 'danger')
                return redirect(url_for('orders.index'))
            # Anti-IDOR: solo anticipar ordenes de la propia sucursal
            denied = require_branch_access(orden.branch_id)
            if denied:
                return denied
            # Validate against order estimated total and existing anticipos to avoid overpayment
            try:
                est_total = 0
                if getattr(orden, 'productos', None):
                    est_total = sum((p.cantidad * float(p.precio_unitario)) for p in orden.productos)
                total_anticipos = sum(a.monto for a in (getattr(orden, 'anticipos') or []))
                saldo_restante = float(est_total) - float(total_anticipos)
            except Exception:
                # fallback: if any error calculating, allow creation but log
                est_total = None
                saldo_restante = None

            if saldo_restante is not None and saldo_restante <= 0:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json:
                    return jsonify({'ok': False, 'error': 'La orden ya esta totalmente anticipada'}), 400
                flash('La orden ya esta totalmente anticipada', 'danger')
                return redirect(url_for('ordenes.editar_orden', orden_id=orden.id))

            if saldo_restante is not None and monto > saldo_restante:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json:
                    return jsonify({'ok': False, 'error': f'Monto mayor al saldo restante ({saldo_restante})'}), 400
                flash(f'Monto mayor al saldo restante ({saldo_restante})', 'danger')
                return redirect(url_for('ordenes.editar_orden', orden_id=orden.id))

            # Capturar caja de trámite (automáticamente asignada por frontend según método de pago)
            caja_tramite = request.form.get('caja_tramite', 'appot').strip()
            
            # VERIFICACIÓN ADICIONAL: Asegurarse de que tarjeta/transferencia siempre vayan a Siigo
            # Esta verificación en backend previene errores si el frontend falla
            metodo_lower = (metodo or '').lower()
            if metodo_lower in ('tarjeta', 'transferencia'):
                caja_tramite = 'siigo'
            elif metodo_lower == 'efectivo':
                caja_tramite = 'appot'
            
            # Capturar número de factura Siigo (opcional, solo para tarjeta/transferencia)
            numero_factura_siigo = request.form.get('numero_factura_siigo', '').strip() or None
            
            # Normalizar método de pago a minúsculas para consistencia en queries
            metodo_normalizado = (metodo or 'efectivo').lower().strip()
            
            # VALIDACIÓN FINAL: metodo_normalizado NUNCA debe estar vacío
            if not metodo_normalizado or metodo_normalizado == '':
                metodo_normalizado = 'efectivo'
            
            # Usar la sucursal del usuario que registra el anticipo (donde se recibe el dinero),
            # NO la sucursal de la OT. Esto evita que anticipos de otros vendedores
            # aparezcan en el cuadre de una sucursal que no los cobró.
            # Fallback a orden.branch_id solo si el usuario no tiene sucursal asignada (ej. admin).
            anticipo_branch_id = current_user.branch_id if current_user.branch_id else orden.branch_id
            anticipo = Anticipo(
                orden_id=orden.id, 
                monto=monto, 
                metodo_pago=metodo_normalizado, 
                registrado_por_id=current_user.id,
                caja_tramite=caja_tramite,
                numero_factura_siigo=numero_factura_siigo,
                branch_id=anticipo_branch_id
            )
            db.session.add(anticipo)
            db.session.commit()
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json:
                return jsonify({'ok': True, 'anticipo': {'id': anticipo.id, 'monto': anticipo.monto, 'metodo_pago': anticipo.metodo_pago, 'fecha': anticipo.fecha.isoformat(), 'registrado_por_id': anticipo.registrado_por_id, 'venta_id': anticipo.venta_id}})
            flash('Anticipo registrado correctamente', 'success')
            return redirect(url_for('ordenes.editar_orden', orden_id=orden.id))
        else:
            # legacy flow: create anticipo via cliente name (used in sales.nueva)
            cliente_nombre = request.form.get('cliente', '').strip()
            if not cliente_nombre:
                flash('Todos los campos son obligatorios', 'danger')
                return redirect(url_for('sales.nueva'))
            cliente = Client.query.filter_by(nombre=cliente_nombre).first()
            if not cliente:
                flash('Cliente no encontrado', 'danger')
                return redirect(url_for('sales.nueva'))
            from models.models import OrdenTrabajo
            orden = OrdenTrabajo.query.filter_by(client_id=cliente.id).order_by(OrdenTrabajo.fecha_creacion.desc()).first()
            if not orden:
                flash('No se encontro una orden para este cliente', 'danger')
                return redirect(url_for('sales.nueva'))
            metodo_normalizado = (metodo or 'efectivo').lower().strip()
            anticipo_branch_id = current_user.branch_id if current_user.branch_id else orden.branch_id
            anticipo = Anticipo(
                orden_id=orden.id, monto=monto, metodo_pago=metodo_normalizado,
                registrado_por_id=current_user.id, branch_id=anticipo_branch_id
            )
            db.session.add(anticipo)
            db.session.commit()
            flash('Anticipo registrado correctamente', 'success')
            return redirect(url_for('sales.nueva'))
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception('Error al guardar el anticipo')
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json:
            return jsonify({'ok': False, 'error': 'Error interno al guardar el anticipo'}), 500
        flash('Error al guardar el anticipo', 'danger')
        return redirect(url_for('sales.nueva'))


@anticipos_bp.route('/<int:anticipo_id>/delete', methods=['POST'])
@login_required
def eliminar_anticipo(anticipo_id):
    try:
        anticipo = Anticipo.query.get_or_404(anticipo_id)
        # permission: allow only admin or supervisor
        from flask_login import current_user
        if current_user.rol not in ('admin', 'supervisor'):
            return jsonify({'ok': False, 'error': 'Sin permiso para eliminar. Solo admin o supervisor pueden eliminar anticipos.'}), 403
        # Anti-IDOR via la orden duena del anticipo
        from models.models import OrdenTrabajo
        orden = OrdenTrabajo.query.get(anticipo.orden_id) if anticipo.orden_id else None
        denied = require_branch_access(orden.branch_id if orden else anticipo.branch_id)
        if denied:
            return denied
        orden_id = anticipo.orden_id
        db.session.delete(anticipo)
        db.session.commit()
        return jsonify({'ok': True, 'orden_id': orden_id})
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception('Error al eliminar anticipo')
        return jsonify({'ok': False, 'error': 'Error interno al eliminar el anticipo'}), 500


@anticipos_bp.route('/<int:anticipo_id>/editar_factura_siigo', methods=['POST'])
@login_required
def editar_factura_siigo(anticipo_id):
    """Permite editar el número de factura Siigo de un anticipo existente"""
    try:
        anticipo = Anticipo.query.get_or_404(anticipo_id)

        # Anti-IDOR via la orden duena del anticipo
        from models.models import OrdenTrabajo
        orden = OrdenTrabajo.query.get(anticipo.orden_id) if anticipo.orden_id else None
        denied = require_branch_access(orden.branch_id if orden else anticipo.branch_id)
        if denied:
            return denied

        # Verificar que sea un anticipo de Siigo (tarjeta o transferencia)
        if anticipo.caja_tramite != 'siigo':
            return jsonify({'ok': False, 'error': 'Este anticipo no fue procesado por Siigo'}), 400
        
        # Obtener el número de factura del request JSON
        data = request.get_json(silent=True) or {}
        numero_factura_siigo = (data.get('numero_factura_siigo') or '').strip()
        
        if not numero_factura_siigo:
            return jsonify({'ok': False, 'error': 'Número de factura requerido'}), 400
        
        # Actualizar el anticipo
        anticipo.numero_factura_siigo = numero_factura_siigo
        db.session.commit()
        
        return jsonify({
            'ok': True, 
            'anticipo_id': anticipo.id,
            'numero_factura_siigo': anticipo.numero_factura_siigo
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception('Error al editar factura Siigo')
        return jsonify({'ok': False, 'error': 'Error interno al actualizar'}), 500
