# routes/sales.py

from flask import Blueprint, render_template, redirect, url_for, flash, request, send_file, session, current_app, make_response, jsonify
import os
from extensions import db
from models.models import Venta, DetalleVenta, Client, Product, Branch, OrdenTrabajo, IdempotencyKey, SolicitudEliminacionVenta, Notification, User
from forms.sales_form import VentaForm
from io import BytesIO
import openpyxl
from openpyxl.styles import Font
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy import or_
from utils.sequences import get_next_sequence
from flask_login import current_user, login_required
from datetime import datetime
from utils.timezone_utils import get_local_now, db_to_local
from utils.decorators import role_required, require_branch_access, scoped_branch_param
from types import SimpleNamespace


def _db_has_columns(table_name, columns):
    """Check if the given columns exist in the database table (information_schema).

    Returns a set of column names that exist.
    """
    try:
        found = set()
        for col in columns:
            row = db.session.execute(
                text("SELECT 1 FROM information_schema.columns WHERE table_name = :t AND column_name = :c"),
                {'t': table_name, 'c': col}
            ).first()
            if row:
                found.add(col)
        return found
    except Exception:
        return set()


def _fetch_detalles_safe_raw(venta_id):
    """Return a list of lightweight objects representing detalles for a venta.

    This uses a raw SQL query to avoid SQLAlchemy ORM lazy-loading which may
    request columns that are not yet present in the DB schema.
    """
    try:
        current_app.logger.info(f"Fetching detalles for venta {venta_id}")
        sql = text(
            "SELECT d.id, d.venta_id, d.producto_id, d.cantidad, d.precio_unitario, "
            "COALESCE(d.nombre_producto, p.nombre) AS producto_nombre, p.sku AS producto_sku, "
            "d.descuento_porcentaje, d.descuento_valor "
            "FROM detalle_venta d LEFT JOIN products p ON p.id = d.producto_id WHERE d.venta_id = :vid"
        )
        rows = db.session.execute(sql, {'vid': venta_id}).mappings().all()
        current_app.logger.info(f"Found {len(rows)} detalle rows for venta {venta_id}")
        out = []
        for r in rows:
            obj = SimpleNamespace()
            obj.id = r.get('id')
            obj.venta_id = r.get('venta_id')
            obj.producto_id = r.get('producto_id')
            obj.cantidad = int(r.get('cantidad') or 0)
            # precio_unitario stored as numeric -> convert to float
            obj.precio_unitario = float(r.get('precio_unitario') or 0)
            # Calculate subtotal as cantidad * precio_unitario (since subtotal column may not exist)
            obj.subtotal = obj.cantidad * obj.precio_unitario
            obj.nombre_producto = r.get('producto_nombre')
            # simple producto namespace to emulate relationship when needed
            prod = SimpleNamespace()
            prod.nombre = r.get('producto_nombre')
            prod.sku = r.get('producto_sku')
            obj.producto = prod
            obj.descuento_porcentaje = r.get('descuento_porcentaje')
            obj.descuento_valor = r.get('descuento_valor')
            def _name_display(o=obj):
                name = o.nombre_producto or (o.producto.nombre if getattr(o, 'producto', None) else 'Producto eliminado')
                return name.upper() if name else 'PRODUCTO ELIMINADO'
            obj.get_nombre_display = _name_display
            out.append(obj)
        return out
    except Exception as e:
        current_app.logger.error(f"Error fetching detalles for venta {venta_id}: {e}")
        return []

bp = Blueprint('sales', __name__, url_prefix='/ventas')

@bp.route('/nueva', methods=['GET', 'POST'])
@login_required
@role_required('admin', 'vendedor', 'bodega', 'supervisor')
def nueva():
    form = VentaForm()
    # Removed loading all clients for performance - client search is handled via AJAX in frontend
    # form.cliente_id.choices = [(c.id, c.nombre) for c in Client.query.order_by(Client.nombre).all()]

    cliente_generico = Client.query.filter_by(cc="222222222").first()
    if not cliente_generico:
        cliente_generico = Client(
            nombre="Generico",
            cc="222222222",
            correo="correo@correo.com",
            telefono="6044440801"
        )
        db.session.add(cliente_generico)
        db.session.commit()

    branch_id = session.get("branch_id")
    if not branch_id:
        flash("Debes seleccionar una sucursal antes de continuar", "warning")
        return redirect(url_for("sales.seleccionar_sucursal"))

    sucursal_activa = None
    if branch_id:
        sucursal_activa = Branch.query.get(branch_id)

    if request.method == 'POST':
        def is_ajax():
            return request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.accept_mimetypes['application/json'] > 0

        try:
            # DB-backed idempotency: attempt to reserve the key, or return existing venta
            idempotency_key = request.form.get('idempotency_key') or None
            if idempotency_key:
                try:
                    # Try to create a placeholder row for this key. If it already exists
                    # another request is processing or already processed it.
                    new_key = IdempotencyKey(key=idempotency_key, venta_id=None)
                    db.session.add(new_key)
                    db.session.flush()
                    current_app.logger.debug(f"Reserved idempotency key {idempotency_key}")
                    reserved_key_obj = new_key
                except IntegrityError:
                    # Another process inserted the same key first. Find the existing mapping.
                    db.session.rollback()
                    existing = IdempotencyKey.query.get(idempotency_key)
                    if existing and existing.venta_id:
                        if is_ajax():
                            return {"success": True, "venta_id": existing.venta_id, "factura": f"FAC-{Venta.query.get(existing.venta_id).numero_factura if Venta.query.get(existing.venta_id) else ''}"}
                        return redirect(url_for('sales.ver', venta_id=existing.venta_id))
                    # If existing.venta_id is None, it means another process is likely creating the venta.
                    # We'll wait briefly and then try to read the mapping.
                    import time
                    for _ in range(10):
                        existing = IdempotencyKey.query.get(idempotency_key)
                        if existing and existing.venta_id:
                            if is_ajax():
                                return {"success": True, "venta_id": existing.venta_id, "factura": f"FAC-{Venta.query.get(existing.venta_id).numero_factura if Venta.query.get(existing.venta_id) else ''}"}
                            return redirect(url_for('sales.ver', venta_id=existing.venta_id))
                        time.sleep(0.05)
                    # if still not present, proceed — but try to insert again in a fresh transaction
                    try:
                        new_key = IdempotencyKey(key=idempotency_key, venta_id=None)
                        db.session.add(new_key)
                        db.session.flush()
                        reserved_key_obj = new_key
                    except IntegrityError:
                        db.session.rollback()
                        existing = IdempotencyKey.query.get(idempotency_key)
                        if existing and existing.venta_id:
                            if is_ajax():
                                return {"success": True, "venta_id": existing.venta_id, "factura": f"FAC-{Venta.query.get(existing.venta_id).numero_factura if Venta.query.get(existing.venta_id) else ''}"}
                            return redirect(url_for('sales.ver', venta_id=existing.venta_id))
            cliente_id_raw = request.form.get("cliente_id", "").strip()
            # If no client selected in the POS UI (empty input), treat as generic client
            if not cliente_id_raw.isdigit():
                # Use the previously ensured generic client
                cliente_id = cliente_generico.id
                current_app.logger.debug(f"No client selected in POS form, falling back to generic client id={cliente_id}")
            else:
                cliente_id = int(cliente_id_raw)

            # Verificar si hay una orden asociada
            orden_id_raw = request.form.get("orden_id", "").strip()
            orden = None
            if orden_id_raw.isdigit():
                orden_id = int(orden_id_raw)
                orden = OrdenTrabajo.query.get(orden_id)
                if orden:
                    # VALIDACIÓN DE SEGURIDAD: Verificar que la OT pertenece a la sucursal activa del usuario
                    active_branch_id = session.get("branch_id")
                    if active_branch_id and orden.branch_id != active_branch_id:
                        msg = f"Error de seguridad: La orden {orden.consecutivo or orden.id} pertenece a otra sucursal y no puede ser facturada desde aquí."
                        current_app.logger.warning(f"Intento no autorizado: Usuario {current_user.id} intenta facturar OT {orden.id} de sucursal {orden.branch_id} desde sucursal {active_branch_id}")
                        if is_ajax():
                            return {"success": False, "error": msg}, 403
                        flash(msg, "danger")
                        return redirect(url_for('sales.nueva'))
                    
                    # Ensure the order is finalizada before allowing it to be billed
                    try:
                        if getattr(orden, 'estado', None) and orden.estado != 'finalizado':
                            msg = f"La orden {orden.consecutivo or orden.id} no esta finalizada y no puede ser facturada."
                            if is_ajax():
                                return {"success": False, "error": msg}, 400
                            flash(msg, "warning")
                            return redirect(url_for('sales.nueva'))
                    except Exception:
                        # If we cannot read the estado for some reason, block billing as a safety measure
                        msg = "No se pudo verificar el estado de la orden. Operacion cancelada."
                        if is_ajax():
                            return {"success": False, "error": msg}, 400
                        flash(msg, "danger")
                        return redirect(url_for('sales.nueva'))
                    # Prevent billing an OT that is already finalized
                    try:
                        already_billed = False
                        try:
                            if getattr(orden, 'venta_rel', None) is not None:
                                already_billed = True
                        except Exception:
                            already_billed = False
                        if not already_billed:
                            from models.models import Venta as _Venta
                            if _Venta.query.filter_by(orden_id=orden.id).first():
                                already_billed = True
                        if already_billed:
                            msg = f"La orden {orden.consecutivo or orden.id} ya fue facturada."
                            if is_ajax():
                                return {"success": False, "error": msg}, 400
                            flash(msg, "warning")
                            return redirect(url_for('sales.nueva'))
                    except Exception:
                        pass
                    # Validate that the order belongs to the active branch
                    if orden.branch_id != branch_id:
                        orden_label = orden.consecutivo or orden.id
                        branch_nombre = orden.branch.nombre if orden.branch else f"ID {orden.branch_id}"
                        msg = (f"La orden {orden_label} pertenece a la sucursal '{branch_nombre}' "
                               f"y no puede ser facturada desde una sucursal diferente.")
                        if is_ajax():
                            return {"success": False, "error": msg}, 400
                        flash(msg, "warning")
                        return redirect(url_for('sales.nueva'))

            detalles = []
            total = 0
            producto_encontrado = False

            for key in request.form:
                if key.startswith("producto_id_"):
                    index = key.split("_")[2]
                    producto_id_raw = request.form.get(f"producto_id_{index}", "").strip()
                    cantidad_raw = request.form.get(f"cantidad_{index}", "").strip()
                    precio_raw = request.form.get(f"precio_unitario_{index}", "").strip()
                    nombre_personalizado = request.form.get(f"nombre_producto_{index}", "").strip()
                    current_app.logger.info(f"[POS] Index={index}, ProductoID={producto_id_raw}, NombrePersonalizado='{nombre_personalizado}'")
                    
                    if not producto_id_raw.isdigit() or not cantidad_raw.isdigit():
                        continue
                    try:
                        precio = int(round(float(precio_raw)))
                    except ValueError:
                        continue
                    producto_id = int(producto_id_raw)
                    cantidad = int(cantidad_raw)
                    producto = Product.query.get(producto_id)
                    if not producto:
                        msg = "Producto no valido"
                        if is_ajax():
                            return {"success": False, "error": msg}, 400
                        flash(msg, "danger")
                        return redirect(url_for('sales.nueva'))
                    # Stock eliminado - no se valida mas el inventario
                    subtotal = precio * cantidad
                    # read per-line discount if provided by the frontend
                    try:
                        pct_raw = request.form.get(f'descuento_porcentaje_{index}', '')
                        descuento_pct = float(pct_raw) if pct_raw not in (None, '') and pct_raw != '' else 0.0
                    except Exception:
                        descuento_pct = 0.0
                    descuento_val = int(round(precio * cantidad * (max(0.0, min(100.0, descuento_pct)) / 100.0))) if descuento_pct else 0
                    detalle = DetalleVenta(
                        producto_id=producto.id,
                        cantidad=cantidad,
                        precio_unitario=int(round(precio)),
                        subtotal=int(round(subtotal)),
                        nombre_producto=nombre_personalizado if nombre_personalizado else None,
                        descuento_porcentaje=round(descuento_pct, 2),
                        descuento_valor=descuento_val
                    )
                    detalles.append(detalle)
                    total += subtotal
                    # Stock eliminado - no se actualiza inventario
                    producto_encontrado = True

            # Si hay una orden de trabajo, usar sus productos SOLO si no se agregaron productos manualmente
            if orden and not producto_encontrado:
                try:
                    detalles = []
                    total = 0
                    for p in orden.productos:
                        precio = float(p.precio_unitario)
                        cantidad = int(p.cantidad)
                        subtotal = precio * cantidad
                        # Orders don't carry per-line discount info in the same way; set to 0
                        detalle = DetalleVenta(
                            producto_id=p.producto_id,
                            cantidad=cantidad,
                            precio_unitario=int(round(precio)),
                            subtotal=int(round(subtotal)),
                            nombre_producto=p.nombre_producto if p.nombre_producto else None,
                            descuento_porcentaje=0,
                            descuento_valor=0
                        )
                        detalles.append(detalle)
                        total += subtotal
                    producto_encontrado = len(detalles) > 0
                    
                    # Fallback: Si productos_orden está vacío, parsear articulos_json
                    if not producto_encontrado and orden.articulos_json:
                        import json
                        try:
                            articulos = json.loads(orden.articulos_json)
                            for articulo in articulos:
                                productos_articulo = articulo.get('productos', [])
                                for prod in productos_articulo:
                                    # Obtener producto_id desde SKU
                                    sku = prod.get('sku')
                                    producto_id = None
                                    if sku:
                                        producto_db = Product.query.filter_by(sku=str(sku)).first()
                                        if producto_db:
                                            producto_id = producto_db.id
                                    
                                    # Si no se encuentra por SKU, buscar por nombre
                                    if not producto_id:
                                        nombre_custom = prod.get('nombreCustom') or prod.get('nombre')
                                        if nombre_custom:
                                            producto_db = Product.query.filter(Product.nombre.ilike(f"%{nombre_custom}%")).first()
                                            if producto_db:
                                                producto_id = producto_db.id
                                    
                                    # Si aún no hay producto_id, crear producto genérico
                                    if not producto_id:
                                        current_app.logger.warning(f"Producto no encontrado para SKU {sku}, usando producto genérico")
                                        # Buscar o crear producto genérico "SERVICIO"
                                        producto_generico = Product.query.filter_by(nombre='SERVICIO').first()
                                        if producto_generico:
                                            producto_id = producto_generico.id
                                    
                                    if producto_id:
                                        cantidad = int(prod.get('cantidad', 1))
                                        precio = int(round(float(prod.get('precio', 0))))
                                        subtotal = precio * cantidad
                                        nombre_producto = prod.get('nombreCustom') or prod.get('nombre') or 'PRODUCTO'
                                        
                                        detalle = DetalleVenta(
                                            producto_id=producto_id,
                                            cantidad=cantidad,
                                            precio_unitario=precio,
                                            subtotal=subtotal,
                                            nombre_producto=nombre_producto,
                                            descuento_porcentaje=0,
                                            descuento_valor=0
                                        )
                                        detalles.append(detalle)
                                        total += subtotal
                                        producto_encontrado = True
                        except Exception as ex_json:
                            current_app.logger.exception("Error parseando articulos_json en venta")
                    
                    current_app.logger.info(f"Factura para OT {orden.id}: total calculado desde OT = {total}")
                except Exception as ex:
                    current_app.logger.exception("Error reconstruyendo detalles desde OT")

            # Validación final: SIEMPRE debe haber al menos un producto
            if not producto_encontrado or len(detalles) == 0:
                msg = "No se puede crear una venta sin productos. Debe agregar al menos un producto valido."
                current_app.logger.error(f"Intento de crear venta sin productos. Usuario: {current_user.id}, Orden: {orden.id if orden else 'N/A'}")
                if is_ajax():
                    return {"success": False, "error": msg}, 400
                flash(msg, "danger")
                return redirect(url_for('sales.nueva'))

            numero_factura = get_next_sequence(branch_id, "factura")
            # Keep the sale total as the gross total calculated from details or the order.
            # Do NOT subtract anticipos here to avoid double-discounting. The anticipo
            # will be recorded separately (anticipo_total) and the saldo will be calculated
            # as total - anticipo_total below.
            total_final = float(total)
            if orden:
                try:
                    current_app.logger.info(f"Orden anticipos total (informational): {orden.total_anticipado()}")
                except Exception:
                    pass
            # caja_tramite: se asigna según lo que el usuario seleccione en el POS
            # Debe definirse antes de cualquier uso (corrige bug de NameError)
            caja_tramite = request.form.get('caja_tramite', 'appot').strip()

            # Determine anticipo_total
            # Priorizar el anticipo_monto enviado desde el frontend (lo que el usuario vio en la preview)
            # Fallback a calcular desde anticipos de la orden (todos, sin filtrar por caja_tramite)
            anticipo_total = 0.0
            anticipo_monto_frontend = float(request.form.get('anticipo_monto', 0) or 0)
            
            try:
                if anticipo_monto_frontend > 0:
                    anticipo_total = anticipo_monto_frontend
                    current_app.logger.info(f"Usando anticipo_monto del frontend: {anticipo_total}")
                elif orden:
                    anticipos_orden = getattr(orden, 'anticipos', []) or []
                    anticipo_total = float(sum([a.monto for a in anticipos_orden]) or 0)
                    if anticipos_orden:
                        current_app.logger.info(f"Anticipos de la orden: {len(anticipos_orden)}, total: {anticipo_total}")
            except Exception as e:
                current_app.logger.warning(f"Error calculando anticipo: {e}")
                anticipo_total = anticipo_monto_frontend

            saldo_calc = max(0.0, float(total_final) - float(anticipo_total))
            estado_pago = 'pagada' if saldo_calc == 0 else 'pendiente'

            # Compute discount: prefer explicit global percentage if provided, otherwise
            # sum per-item discounts sent as descuento_porcentaje_<index> alongside
            # precio_unitario_<index> and cantidad_<index>.
            descuento_amount = 0.0
            try:
                # Legacy/global discount (single percentage applies to entire sale)
                pct_raw = request.form.get('descuento_porcentaje', '')
                if pct_raw != '':
                    pct = float(pct_raw)
                    pct = max(0.0, min(100.0, pct))
                    descuento_amount = round(float(total_final) * (pct / 100.0))
                else:
                    # Look for per-item discount fields: descuento_porcentaje_0, _1, ...
                    for key in list(request.form.keys()):
                        if key.startswith('descuento_porcentaje_'):
                            try:
                                idx = key.split('_')[-1]
                                pct_val = float(request.form.get(key, 0) or 0)
                                if pct_val <= 0:
                                    continue
                                precio_raw = request.form.get(f'precio_unitario_{idx}', '')
                                cant_raw = request.form.get(f'cantidad_{idx}', '')
                                precio = float(precio_raw) if precio_raw not in (None, '') else 0.0
                                cantidad = int(cant_raw) if cant_raw not in (None, '') else 0
                                linea_desc = round(precio * cantidad * (max(0.0, min(100.0, pct_val)) / 100.0))
                                descuento_amount += linea_desc
                            except Exception:
                                # ignore malformed index/values for robustness
                                continue
            except Exception:
                descuento_amount = 0.0

            # Create Venta without assigning descuento directly to avoid DB errors
            # when the column hasn't been added via migrations yet.
            
            nueva_venta = Venta(
                cliente_id=cliente_id,
                total=total_final,
                numero_factura=numero_factura,
                branch_id=branch_id,
                detalles=detalles,
                anticipo_total=anticipo_total,
                saldo=saldo_calc,
                estado_pago=estado_pago,
                caja_tramite=caja_tramite
            )
            # Assign descuento only if the column exists in the model/table mapping
            try:
                if 'descuento' in Venta.__table__.columns.keys():
                    nueva_venta.descuento = descuento_amount
            except Exception:
                # If anything goes wrong, continue without setting descuento
                pass
            try:
                nueva_venta.usuario_id = current_user.id
            except Exception:
                pass
            db.session.add(nueva_venta)
            # If this sale is for an order, link any anticipos of the order to this venta
            try:
                if orden:
                    # flush to get nueva_venta.id
                    db.session.flush()
                    anticipos_list = getattr(orden, 'anticipos') or []
                    anticipos_vinculados = 0
                    monto_vinculado = 0
                    
                    for anticipo in anticipos_list:
                        try:
                            if anticipo.venta_id is None:
                                # Vincular anticipo sin importar su caja_tramite
                                # El estado "Aplicado" solo depende de que esté facturado
                                anticipo.venta_id = nueva_venta.id
                                db.session.add(anticipo)
                                anticipos_vinculados += 1
                                monto_vinculado += anticipo.monto
                                current_app.logger.info(
                                    f"Anticipo ID {anticipo.id} (${anticipo.monto}) [{getattr(anticipo, 'caja_tramite', 'appot')}] vinculado a Venta ID {nueva_venta.id} [{caja_tramite}]"
                                )
                        except Exception as e:
                            current_app.logger.error(
                                f"Error vinculando anticipo {anticipo.id} a venta: {str(e)}", 
                                exc_info=True
                            )
                    
                    if anticipos_vinculados > 0:
                        current_app.logger.info(
                            f"Orden {orden.id}: {anticipos_vinculados} anticipos vinculados a Venta {nueva_venta.id}"
                        )
                    elif anticipos_list:
                        current_app.logger.warning(
                            f"Orden {orden.id} tiene {len(anticipos_list)} anticipos pero ninguno fue vinculado (posiblemente ya facturados)"
                        )
            except Exception:
                current_app.logger.exception('Error en proceso de vinculación de anticipos a la venta')
            try:
                if orden:
                    # Tras generar la venta, marcar la orden como 'facturado'
                    # Precondición: la orden debe estar 'finalizado' para poder facturar (ver comprobación arriba)
                    orden.estado = 'facturado'
                    orden.entregado = True
                    orden.fecha_entrega = get_local_now()
                    try:
                        nueva_venta.orden_id = orden.id
                    except Exception:
                        pass
                    if 'numero_factura' in OrdenTrabajo.__table__.columns.keys():
                        try:
                            orden.numero_factura = str(numero_factura)
                        except Exception:
                            pass
            except Exception:
                pass
            try:
                current_app.logger.info(f"Venta diagnostic: total={total}, detalles={len(detalles)}, orden_id={orden.id if orden else None}")
                if orden:
                    try:
                        current_app.logger.info(f"Orden anticipos total: {orden.total_anticipado()}")
                    except Exception:
                        current_app.logger.info('Orden anticipos: error al leer')
                db.session.commit()
                # associate idempotency key with the created venta so future reposts return the same
                try:
                    if idempotency_key:
                        try:
                            # update row in a new transaction to avoid locking the current commit
                            ik = IdempotencyKey.query.get(idempotency_key)
                            if ik:
                                ik.venta_id = nueva_venta.id
                                db.session.add(ik)
                                db.session.commit()
                        except Exception:
                            db.session.rollback()
                except Exception:
                    pass
                # register idempotency_key as processed so later reposts return the same result
                try:
                    if idempotency_key:
                        proc = session.setdefault('processed_sales', {})
                        proc[idempotency_key] = nueva_venta.id
                        session.modified = True
                except Exception:
                    pass
            except IntegrityError as db_err:
                db.session.rollback()
                current_app.logger.exception("IntegrityError al guardar Venta")
                msg = str(db_err.orig) if getattr(db_err, 'orig', None) else str(db_err)
                # Detectar el tipo especifico de error de integridad
                if 'uq_numero_factura' in msg.lower() or 'numero_factura' in msg.lower():
                    msg = 'Error: El numero de factura ya existe en esta sucursal. Por favor, contacte al administrador.'
                elif 'ux_venta_orden_id' in msg or ('orden_id' in msg.lower() and 'unique' in msg.lower()):
                    msg = 'No se pudo registrar la venta: la orden ya fue facturada por otro proceso.'
                else:
                    msg = 'Error de integridad al guardar la venta en la base de datos.'
                if is_ajax():
                    return {"success": False, "error": msg}, 400
                flash(msg, 'danger')
                return redirect(url_for('sales.nueva'))
            except Exception as db_err:
                db.session.rollback()
                current_app.logger.exception("Error inesperado al guardar Venta")
                msg = f'Error al guardar la venta en la base de datos: {db_err}'
                if is_ajax():
                    return {"success": False, "error": msg}, 400
                flash(msg, 'danger')
                return redirect(url_for('sales.nueva'))

            if is_ajax():
                return {"success": True, "venta_id": nueva_venta.id, "factura": f"FAC-{numero_factura}", "print_url": url_for('sales.reimprimir', venta_id=nueva_venta.id)}
            flash(f"Venta registrada correctamente: FAC-{numero_factura}", "success")
            return redirect(url_for('sales.ver', venta_id=nueva_venta.id))

        except Exception as e:
            db.session.rollback()
            current_app.logger.exception("Error al registrar la venta")
            msg = f"Error al registrar la venta: {e}"
            if request.method == 'POST' and (request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.accept_mimetypes['application/json'] > 0):
                return {"success": False, "error": msg}, 500
            flash(msg, "danger")
            return redirect(url_for('sales.nueva'))

    numero_factura = get_next_sequence(branch_id, "factura")
    return render_template("sales/nueva.html", form=form, cliente_generico=cliente_generico, numero_factura=numero_factura, sucursal_activa=sucursal_activa)

@bp.route('/seleccionar-sucursal', methods=['GET', 'POST'])
@login_required
def seleccionar_sucursal():
    if request.method == 'POST':
        branch_id = request.form.get('branch_id', type=int)
        # Validar existencia (evita fijar sucursales inexistentes en sesion)
        branch = Branch.query.get(branch_id) if branch_id else None
        if not branch:
            flash('Sucursal invalida', 'danger')
            return redirect(url_for('sales.seleccionar_sucursal'))
        # Anti-IDOR: roles restringidos solo pueden operar su propia sucursal
        denied = require_branch_access(branch.id)
        if denied:
            return denied
        session['branch_id'] = branch.id
        return redirect(url_for('sales.nueva'))

    sucursales = Branch.query.order_by(Branch.nombre).all()
    return render_template('sales/seleccionar_sucursal.html', sucursales=sucursales)

@bp.route('/listar')
@login_required
@role_required('admin', 'vendedor', 'supervisor', 'bodega')
def listar():
    sucursal_id = request.args.get('sucursal', type=int)
    cliente_id = request.args.get('cliente', type=int)
    cliente_nombre = request.args.get('cliente_nombre', '').strip()
    fecha_str = request.args.get('fecha', '')
    factura = request.args.get('factura', '')

    # Por defecto, excluir ventas eliminadas (considerar NULL como no eliminada)
    query = Venta.query.filter(or_(Venta.eliminada == False, Venta.eliminada.is_(None))).order_by(Venta.numero_factura.desc())
    # Scoping por sucursal: roles restringidos solo ven su sucursal
    sucursal_id = scoped_branch_param(sucursal_id)
    if sucursal_id:
        query = query.filter(Venta.branch_id == sucursal_id)
    if cliente_id:
        query = query.filter(Venta.cliente_id == cliente_id)
    elif cliente_nombre:
        # Buscar clientes cuyo nombre contiene el texto
        clientes = Client.query.filter(Client.nombre.ilike(f'%{cliente_nombre}%')).all()
        if clientes:
            ids = [c.id for c in clientes]
            query = query.filter(Venta.cliente_id.in_(ids))
    if fecha_str:
        try:
            fecha_dt = datetime.strptime(fecha_str, '%Y-%m-%d')
            fecha_fin = fecha_dt.replace(hour=23, minute=59, second=59)
            query = query.filter(Venta.fecha >= fecha_dt, Venta.fecha <= fecha_fin)
        except Exception:
            pass
    if factura:
        query = query.filter(Venta.numero_factura.like(f'%{factura}%'))
    ventas = query.all()
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        # Solo devolver la tabla para AJAX
        return render_template("sales/listar.html", ventas=ventas, Branch=Branch, Client=Client, ajax=True)
    return render_template("sales/listar.html", ventas=ventas, Branch=Branch, Client=Client)


@bp.route('/ver/<int:venta_id>')
@login_required
def ver(venta_id):
    v = Venta.query.get_or_404(venta_id)
    # Anti-IDOR: solo la sucursal duena (admin/supervisor global)
    denied = require_branch_access(v.branch_id)
    if denied:
        return denied

    # Verificar si es vista POS o vista normal
    pos_mode = request.args.get('pos', '0')  # Por defecto vista normal (detalle)
    is_pos = pos_mode not in ('0', 'false', 'no')
    
    # Helper: when DB schema doesn't include per-line discount columns, load a safe
    # detalle list with the legacy columns only and None for new fields to avoid
    # SQLAlchemy ProgrammingError. Returns a list of objects compatible with templates.
    def _load_detalles_safe(vid):
        # If the model/table already has the new columns, use the ORM relationship
        # Check actual DB columns (not the SQLAlchemy model) to determine whether
        # the descuento columns were created by migrations. If they exist, we can
        # safely use the ORM relationship. Otherwise use a safe raw query.
        try:
            existing = _db_has_columns('detalle_venta', ['descuento_porcentaje', 'descuento_valor'])
            if 'descuento_porcentaje' in existing and 'descuento_valor' in existing:
                return None  # Use ORM relationship
        except Exception:
            pass
        # Fallback raw query selecting only known columns
        return _fetch_detalles_safe_raw(vid)

    # Always provide a safe 'detalles' list to the template to avoid any
    # lazy-loading of ORM relationships that may reference columns not present
    # in older DB schemas.
    # Prefer ORM detalles when DB schema includes the new descuento columns; otherwise use raw safe fetch
    try:
        existing = _db_has_columns('detalle_venta', ['descuento_porcentaje', 'descuento_valor'])
        if 'descuento_porcentaje' in existing and 'descuento_valor' in existing:
            detalles = v.detalles
        else:
            detalles = _fetch_detalles_safe_raw(v.id)
    except Exception:
        detalles = _fetch_detalles_safe_raw(v.id)

    current_app.logger.info(f"Venta {venta_id} exists: {v is not None}")
    current_app.logger.info(f"Venta total: {v.total}")
    current_app.logger.info(f"Venta descuento: {getattr(v, 'descuento', None)}")
    current_app.logger.info(f"Detalles loaded: {len(detalles) if detalles else 0} items")

    # Si la venta tiene una orden asociada, pasar sitios de reparación
    sitios_dict = {}
    if v.orden_id:
        from models.models import User
        sitios_dict = {u.id: u.username for u in User.query.filter_by(es_sitio_reparacion=True).all()}

    if not is_pos:
        # Vista normal (detalle de venta)
        return render_template('sales/detalle.html', venta=v, pos=False, detalles=detalles, sitios_dict=sitios_dict)
    
    # Vista POS (ticket)
    # Leer datos de empresa desde instance/company.json
    import json
    company_path = os.path.join(os.getcwd(), 'instance', 'company.json')
    company_data = {'name': 'Mi Empresa', 'address': '', 'phone': ''}
    if os.path.exists(company_path):
        try:
            with open(company_path, 'r', encoding='utf-8') as f:
                company_data = json.load(f)
        except Exception:
            pass
    company_name = company_data.get('name', 'Mi Empresa')
    company_address = company_data.get('address', '')
    company_phone = company_data.get('phone', '')
    pos_cfg = {
        'ticket_width': '88',
        'font_size': 12,
        'show_company': True,
        'include_address': True,
        'auto_print': True,
        'header_text': ''
    }
    try:
        config_path = os.path.join(os.getcwd(), 'instance', 'sales_formats.json')
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                all_cfg = json.load(f)
            key = str(v.branch_id) if v.branch_id else 'default'
            branch_cfg = all_cfg.get(key) or all_cfg.get('default') or {}
            pos_cfg.update(branch_cfg)
    except Exception:
        pass

    # Si la venta tiene una orden asociada, pasar sitios de reparación
    sitios_dict = {}
    if v.orden_id:
        from models.models import User
        sitios_dict = {u.id: u.username for u in User.query.filter_by(es_sitio_reparacion=True).all()}

    show_invoice = request.args.get('show_invoice')
    show_invoice = show_invoice is not None and str(show_invoice) not in ('0', 'false', 'no')
    return render_template('sales/pos_ticket.html', venta=v, pos=True, company_name=company_name, company_address=company_address, company_phone=company_phone, pos_cfg=pos_cfg, show_invoice=show_invoice, detalles=detalles, sitios_dict=sitios_dict)





@bp.route('/reimprimir/<int:venta_id>')
@login_required
def reimprimir(venta_id):
    v = Venta.query.get_or_404(venta_id)
    # Anti-IDOR: el ticket expone datos de facturacion de la sucursal duena
    denied = require_branch_access(v.branch_id)
    if denied:
        return denied
    # Leer datos de empresa desde instance/company.json
    import json
    company_path = os.path.join(os.getcwd(), 'instance', 'company.json')
    company_data = {'name': 'Mi Empresa', 'address': '', 'phone': ''}
    if os.path.exists(company_path):
        try:
            with open(company_path, 'r', encoding='utf-8') as f:
                company_data = json.load(f)
        except Exception:
            pass
    company_name = company_data.get('name', 'Mi Empresa')
    company_address = company_data.get('address', '')
    company_phone = company_data.get('phone', '')
    pos_cfg = {'ticket_width': '88', 'font_size': 16, 'show_company': True, 'include_address': True, 'auto_print': True, 'header_text': ''}
    try:
        config_path = os.path.join(os.getcwd(), 'instance', 'sales_formats.json')
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                all_cfg = json.load(f)
            key = str(v.branch_id) if v.branch_id else 'default'
            branch_cfg = all_cfg.get(key) or all_cfg.get('default') or {}
            pos_cfg.update(branch_cfg)
    except Exception:
        pass
    show_invoice = request.args.get('show_invoice')
    show_invoice = show_invoice is not None and str(show_invoice) not in ('0', 'false', 'no')
    # Ensure safe detalles for older schemas
    # For reimprimir: prefer ORM when schema updated, otherwise raw
    try:
        existing = _db_has_columns('detalle_venta', ['descuento_porcentaje', 'descuento_valor'])
        if 'descuento_porcentaje' in existing and 'descuento_valor' in existing:
            detalles = v.detalles
        else:
            detalles = _fetch_detalles_safe_raw(venta_id)
    except Exception:
        detalles = _fetch_detalles_safe_raw(venta_id)
    rendered = render_template('sales/pos_ticket.html', venta=v, imprimir=True, pos=True, company_name=company_name, company_address=company_address, company_phone=company_phone, pos_cfg=pos_cfg, show_invoice=show_invoice, detalles=detalles)
    # Prevent caching so browsers always fetch the latest venta when reimprimiendo
    resp = make_response(rendered)
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'
    return resp

@bp.route('/debug/venta/<int:venta_id>')
@login_required
@role_required('admin')
def debug_venta(venta_id):
    v = Venta.query.get_or_404(venta_id)
    detalles = _fetch_detalles_safe_raw(v.id)
    return {
        'venta_id': v.id,
        'total': v.total,
        'descuento': getattr(v, 'descuento', None),
        'orden_id': v.orden_id,
        'detalles_count': len(detalles) if detalles else 0,
        'detalles': [{'id': d.id, 'producto': d.nombre_producto, 'cantidad': d.cantidad} for d in detalles] if detalles else []
    }
    sucursal_id = request.args.get('sucursal', type=int)
    query = Venta.query.order_by(Venta.fecha.desc())
    if sucursal_id:
        query = query.filter(Venta.branch_id == sucursal_id)
    ventas = query.all()
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Ventas"

    encabezados = ['Fecha', 'Factura', 'Sucursal', 'Cliente', 'Total', 'Productos']
    ws.append(encabezados)
    for celda in ws[1]:
        celda.font = Font(bold=True)

    for v in ventas:
        # Build products string safely: if the DB schema lacks new columns, avoid ORM lazy-loading
        try:
            existing = _db_has_columns('detalle_venta', ['descuento_porcentaje', 'descuento_valor'])
            if 'descuento_porcentaje' in existing and 'descuento_valor' in existing:
                detalles_iter = v.detalles
            else:
                detalles_iter = None
        except Exception:
            detalles_iter = None

        if detalles_iter is None:
            # Raw query joining products to get names when necessary
            sql = text("SELECT d.cantidad, d.precio_unitario, COALESCE(d.nombre_producto, p.nombre) as producto_nombre FROM detalle_venta d LEFT JOIN products p ON p.id = d.producto_id WHERE d.venta_id = :vid")
            rows = db.session.execute(sql, {'vid': v.id}).mappings().all()
            productos_str = "; ".join([
                f"{r.get('producto_nombre') or 'Producto eliminado'} ({int(r.get('cantidad') or 0)} x ${int(round(float(r.get('precio_unitario') or 0))):,.0f}".replace(",", ".") + ")"
                for r in rows
            ])
        else:
            productos_str = "; ".join([
                f"{d.producto.nombre} ({d.cantidad} x ${int(round(float(d.precio_unitario)))})"
                for d in detalles_iter
            ])
        # Convert stored datetime (UTC or naive) to local Colombia time for export
        fecha_display = v.fecha
        try:
            fecha_display = db_to_local(v.fecha)
        except Exception:
            pass
        ws.append([
            fecha_display.strftime('%d/%m/%Y %H:%M') if fecha_display else '—',
            v.numero_factura,
            v.branch.nombre if v.branch else '—',
            v.cliente.nombre,
            f"${int(round(v.total)):,.0f}".replace(",", "."),
            productos_str
        ])

    output = BytesIO()
    wb.save(output)
    output.seek(0)

    return send_file(
        output,
        download_name="ventas.xlsx",
        as_attachment=True,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

# --- Sistema de Solicitudes de Eliminaci�n de Ventas ---


@bp.route('/<int:venta_id>/solicitar_eliminacion', methods=['POST'])
@login_required
@role_required('vendedor', 'supervisor', 'admin', 'bodega')
def solicitar_eliminacion(venta_id):
    try:
        venta = Venta.query.get_or_404(venta_id)
        # Anti-IDOR: solo sobre ventas de la propia sucursal
        denied = require_branch_access(venta.branch_id)
        if denied:
            return denied
        if venta.eliminada:
            return jsonify({'ok': False, 'error': 'Esta venta ya fue eliminada'}), 400
        solicitud_existente = SolicitudEliminacionVenta.query.filter_by(venta_id=venta_id, estado='pendiente').first()
        if solicitud_existente:
            return jsonify({'ok': False, 'error': 'Ya existe una solicitud pendiente para esta venta'}), 400
        data = request.get_json(silent=True) or {}
        motivo = data.get('motivo', '').strip()
        if not motivo:
            return jsonify({'ok': False, 'error': 'El motivo es obligatorio'}), 400
        solicitud = SolicitudEliminacionVenta(venta_id=venta_id, solicitante_id=current_user.id, motivo=motivo, estado='pendiente')
        db.session.add(solicitud)
        supervisores_admins = User.query.filter(User.rol.in_(['supervisor', 'admin'])).all()
        for usuario in supervisores_admins:
            notificacion = Notification(user_id=usuario.id, message=f'Solicitud de eliminación de venta #{venta.numero_factura} por {current_user.username}', link=url_for('sales.gestionar_solicitudes'))
            db.session.add(notificacion)
        db.session.commit()
        return jsonify({'ok': True, 'message': 'Solicitud enviada correctamente'})
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception('Error al solicitar eliminacion de venta')
        return jsonify({'ok': False, 'error': 'Error interno al procesar la solicitud'}), 500


@bp.route('/solicitudes')
@login_required
@role_required('supervisor', 'admin')
def gestionar_solicitudes():
    solicitudes_pendientes = SolicitudEliminacionVenta.query.filter_by(estado='pendiente').order_by(SolicitudEliminacionVenta.fecha_solicitud.desc()).all()
    solicitudes_historial = SolicitudEliminacionVenta.query.filter(SolicitudEliminacionVenta.estado.in_(['aprobada', 'rechazada'])).order_by(SolicitudEliminacionVenta.fecha_respuesta.desc()).limit(50).all()
    return render_template('sales/solicitudes_eliminacion.html', solicitudes_pendientes=solicitudes_pendientes, solicitudes_historial=solicitudes_historial)


@bp.route('/solicitudes/<int:solicitud_id>/aprobar', methods=['POST'])
@login_required
@role_required('supervisor', 'admin')
def aprobar_solicitud(solicitud_id):
    try:
        solicitud = SolicitudEliminacionVenta.query.get_or_404(solicitud_id)
        if solicitud.estado != 'pendiente':
            return jsonify({'ok': False, 'error': 'Esta solicitud ya fue procesada'}), 400
        data = request.get_json() or {}
        comentario = data.get('comentario', '').strip()
        solicitud.estado = 'aprobada'
        solicitud.aprobador_id = current_user.id
        from utils.timezone_utils import get_local_now
        solicitud.fecha_respuesta = get_local_now()
        solicitud.comentario_respuesta = comentario or 'Aprobada'
        venta = solicitud.venta
        venta.eliminada = True
        venta.motivo_eliminacion = solicitud.motivo
        venta.fecha_eliminacion = get_local_now()
        venta.eliminada_por_id = current_user.id
        # Desvincular anticipos al eliminar venta
        try:
            for a in getattr(venta, 'anticipos', []):
                a.venta_id = None
                db.session.add(a)
        except Exception:
            pass
        notificacion = Notification(user_id=solicitud.solicitante_id, message=f'Tu solicitud de eliminación de venta #{venta.numero_factura} fue APROBADA', link=url_for('sales.ver', venta_id=venta.id))
        db.session.add(notificacion)
        db.session.commit()
        return jsonify({'ok': True, 'message': 'Solicitud aprobada y venta eliminada'})
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception('Error al aprobar solicitud de eliminacion')
        return jsonify({'ok': False, 'error': 'Error interno al procesar la solicitud'}), 500


@bp.route('/solicitudes/<int:solicitud_id>/rechazar', methods=['POST'])
@login_required
@role_required('supervisor', 'admin')
def rechazar_solicitud(solicitud_id):
    try:
        solicitud = SolicitudEliminacionVenta.query.get_or_404(solicitud_id)
        if solicitud.estado != 'pendiente':
            return jsonify({'ok': False, 'error': 'Esta solicitud ya fue procesada'}), 400
        data = request.get_json() or {}
        comentario = data.get('comentario', '').strip()
        if not comentario:
            return jsonify({'ok': False, 'error': 'Debes especificar el motivo del rechazo'}), 400
        solicitud.estado = 'rechazada'
        solicitud.aprobador_id = current_user.id
        from utils.timezone_utils import get_local_now
        solicitud.fecha_respuesta = get_local_now()
        solicitud.comentario_respuesta = comentario
        venta = solicitud.venta
        notificacion = Notification(user_id=solicitud.solicitante_id, message=f'Tu solicitud de eliminación de venta #{venta.numero_factura} fue RECHAZADA: {comentario}', link=url_for('sales.ver', venta_id=venta.id))
        db.session.add(notificacion)
        db.session.commit()
        return jsonify({'ok': True, 'message': 'Solicitud rechazada'})
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception('Error al rechazar solicitud de eliminacion')
        return jsonify({'ok': False, 'error': 'Error interno al procesar la solicitud'}), 500


@bp.route('/<int:venta_id>/cambiar_caja', methods=['POST'])
@login_required
@role_required('supervisor', 'admin')
def cambiar_caja(venta_id):
    """Cambiar la caja de trámite de una venta existente"""
    try:
        venta = Venta.query.get_or_404(venta_id)
        
        # Anti-IDOR: solo sobre ventas de la propia sucursal
        denied = require_branch_access(venta.branch_id)
        if denied:
            return denied

        # Verificar que la venta no esté eliminada
        if venta.eliminada:
            return jsonify({'ok': False, 'error': 'No se puede modificar una venta eliminada'}), 400
        
        data = request.get_json() or {}
        nueva_caja = data.get('caja_tramite', '').strip().lower()
        
        # Validar que la caja sea válida
        if nueva_caja not in ['appot', 'siigo']:
            return jsonify({'ok': False, 'error': 'Caja inválida. Debe ser "appot" o "siigo"'}), 400
        
        # Verificar que sea diferente a la actual
        if venta.caja_tramite == nueva_caja:
            return jsonify({'ok': False, 'error': f'La venta ya está en la caja {nueva_caja}'}), 400
        
        caja_anterior = venta.caja_tramite
        venta.caja_tramite = nueva_caja
        
        # Si la venta tiene una orden asociada, también actualizar la orden
        if venta.orden_id and venta.orden:
            venta.orden.caja_tramite = nueva_caja
        
        db.session.commit()
        
        return jsonify({
            'ok': True, 
            'message': f'Caja cambiada exitosamente de "{caja_anterior}" a "{nueva_caja}"',
            'caja_anterior': caja_anterior,
            'caja_nueva': nueva_caja
        })
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception('Error al cambiar caja de venta')
        return jsonify({'ok': False, 'error': 'Error interno al cambiar la caja'}), 500
