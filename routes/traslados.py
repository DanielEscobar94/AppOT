from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from extensions import db
from models.models import Traslado, DetalleTraslado, Branch, Product, User
from forms.traslado_form import TrasladoForm
from utils.decorators import role_required, require_branch_access
from datetime import datetime
import pytz

traslados_bp = Blueprint('traslados', __name__, url_prefix='/traslados')

@traslados_bp.route('/')
@login_required
@role_required('admin', 'supervisor', 'vendedor', 'tecnico')
def listar():
    """Listar traslados con paginación y filtros"""
    page = request.args.get('page', 1, type=int)
    per_page = 15
    
    # Filtros
    numero_traslado = request.args.get('numero_traslado', '').strip()
    branch_origen_id = request.args.get('branch_origen_id', type=int)
    branch_destino_id = request.args.get('branch_destino_id', type=int)
    fecha_inicio = request.args.get('fecha_inicio', '').strip()
    fecha_fin = request.args.get('fecha_fin', '').strip()
    
    # Query base
    query = Traslado.query
    
    # Aplicar filtros
    if numero_traslado:
        query = query.filter(Traslado.numero_traslado_siigo.ilike(f'%{numero_traslado}%'))
    
    if branch_origen_id:
        query = query.filter(Traslado.branch_origen_id == branch_origen_id)
    
    if branch_destino_id:
        query = query.filter(Traslado.branch_destino_id == branch_destino_id)
    
    if fecha_inicio:
        try:
            fecha_inicio_dt = datetime.strptime(fecha_inicio, '%Y-%m-%d')
            colombia_tz = pytz.timezone('America/Bogota')
            fecha_inicio_dt = colombia_tz.localize(fecha_inicio_dt.replace(hour=0, minute=0, second=0))
            fecha_inicio_utc = fecha_inicio_dt.astimezone(pytz.utc)
            query = query.filter(Traslado.fecha >= fecha_inicio_utc)
        except ValueError:
            pass
    
    if fecha_fin:
        try:
            fecha_fin_dt = datetime.strptime(fecha_fin, '%Y-%m-%d')
            colombia_tz = pytz.timezone('America/Bogota')
            fecha_fin_dt = colombia_tz.localize(fecha_fin_dt.replace(hour=23, minute=59, second=59))
            fecha_fin_utc = fecha_fin_dt.astimezone(pytz.utc)
            query = query.filter(Traslado.fecha <= fecha_fin_utc)
        except ValueError:
            pass
    
    # Ordenar por consecutivo SIIGO descendente (más reciente primero) y paginar
    pagination = query.order_by(Traslado.numero_traslado_siigo.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    traslados = pagination.items
    
    # Obtener sucursales para filtros
    sucursales = Branch.query.order_by(Branch.nombre).all()
    
    return render_template('traslados/listar.html',
                         traslados=traslados,
                         pagination=pagination,
                         sucursales=sucursales,
                         filtros={
                             'numero_traslado': numero_traslado,
                             'branch_origen_id': branch_origen_id,
                             'branch_destino_id': branch_destino_id,
                             'fecha_inicio': fecha_inicio,
                             'fecha_fin': fecha_fin
                         })


@traslados_bp.route('/crear', methods=['GET', 'POST'])
@login_required
@role_required('admin', 'supervisor', 'vendedor', 'tecnico')
def crear():
    """Crear nuevo traslado"""
    form = TrasladoForm()
    
    # Cargar sucursales
    sucursales = Branch.query.order_by(Branch.nombre).all()
    form.branch_origen_id.choices = [(0, 'Seleccione...')] + [(s.id, s.nombre) for s in sucursales]
    form.branch_destino_id.choices = [(0, 'Seleccione...')] + [(s.id, s.nombre) for s in sucursales]
    
    if request.method == 'POST':
        # Validar que origen y destino sean diferentes
        if form.branch_origen_id.data == form.branch_destino_id.data:
            flash('La bodega de origen y destino deben ser diferentes', 'error')
            return render_template('traslados/crear.html', form=form)
        
        # Validar que el número de traslado no exista
        traslado_existente = Traslado.query.filter_by(
            numero_traslado_siigo=form.numero_traslado_siigo.data
        ).first()
        
        if traslado_existente:
            flash(f'Ya existe un traslado con el número {form.numero_traslado_siigo.data}', 'error')
            return render_template('traslados/crear.html', form=form)
        
        try:
            # Crear traslado
            colombia_tz = pytz.timezone('America/Bogota')
            fecha_local = form.fecha.data
            
            if fecha_local.tzinfo is None:
                fecha_local = colombia_tz.localize(fecha_local)
            
            fecha_utc = fecha_local.astimezone(pytz.utc)
            
            traslado = Traslado(
                numero_traslado_siigo=form.numero_traslado_siigo.data,
                branch_origen_id=form.branch_origen_id.data,
                branch_destino_id=form.branch_destino_id.data,
                fecha=fecha_utc,
                responsable=form.responsable.data,
                observacion=form.observacion.data,
                user_id=current_user.id
            )
            
            db.session.add(traslado)
            db.session.commit()
            
            flash(f'Traslado #{traslado.numero_traslado_siigo} creado exitosamente', 'success')
            return redirect(url_for('traslados.ver', id=traslado.id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error al crear el traslado: {str(e)}', 'error')
            return render_template('traslados/crear.html', form=form)
    
    # GET - Establecer fecha actual
    colombia_tz = pytz.timezone('America/Bogota')
    form.fecha.data = datetime.now(colombia_tz)
    
    return render_template('traslados/crear.html', form=form)


@traslados_bp.route('/<int:id>')
@login_required
@role_required('admin', 'supervisor', 'vendedor', 'tecnico')
def ver(id):
    """Ver detalle de un traslado"""
    traslado = Traslado.query.get_or_404(id)
    # Anti-IDOR: debe intervenir la sucursal origen o destino (admin/supervisor global)
    denied = require_branch_access(traslado.branch_origen_id)
    if denied:
        denied = require_branch_access(traslado.branch_destino_id)
    if denied:
        return denied
    return render_template('traslados/ver.html', traslado=traslado)


@traslados_bp.route('/editar/<int:id>', methods=['GET', 'POST'])
@login_required
@role_required('admin', 'supervisor', 'vendedor', 'tecnico')
def editar(id):
    """Editar un traslado existente"""
    traslado = Traslado.query.get_or_404(id)
    # Anti-IDOR: origen o destino (admin/supervisor global)
    denied = require_branch_access(traslado.branch_origen_id)
    if denied:
        denied = require_branch_access(traslado.branch_destino_id)
    if denied:
        return denied
    form = TrasladoForm(obj=traslado)
    
    # Cargar sucursales
    sucursales = Branch.query.order_by(Branch.nombre).all()
    form.branch_origen_id.choices = [(0, 'Seleccione...')] + [(s.id, s.nombre) for s in sucursales]
    form.branch_destino_id.choices = [(0, 'Seleccione...')] + [(s.id, s.nombre) for s in sucursales]
    
    if request.method == 'GET':
        # Precargar valores del traslado
        form.numero_traslado_siigo.data = traslado.numero_traslado_siigo
        form.branch_origen_id.data = traslado.branch_origen_id
        form.branch_destino_id.data = traslado.branch_destino_id
        form.responsable.data = traslado.responsable
        form.observacion.data = traslado.observacion
        
        # Convertir fecha UTC a hora local de Colombia
        colombia_tz = pytz.timezone('America/Bogota')
        fecha_utc = traslado.fecha
        if fecha_utc.tzinfo is None:
            fecha_utc = pytz.utc.localize(fecha_utc)
        form.fecha.data = fecha_utc.astimezone(colombia_tz)
        
        return render_template('traslados/editar.html', form=form, traslado=traslado)
    
    # POST - Validaciones
    if form.branch_origen_id.data == form.branch_destino_id.data:
        flash('La bodega de origen y destino deben ser diferentes', 'error')
        return render_template('traslados/editar.html', form=form, traslado=traslado)
    
    # Validar que el número de traslado no exista en otro traslado
    traslado_existente = Traslado.query.filter(
        Traslado.numero_traslado_siigo == form.numero_traslado_siigo.data,
        Traslado.id != traslado.id
    ).first()
    
    if traslado_existente:
        flash(f'Ya existe otro traslado con el número {form.numero_traslado_siigo.data}', 'error')
        return render_template('traslados/editar.html', form=form, traslado=traslado)
    
    try:
        # Actualizar campos del traslado
        traslado.numero_traslado_siigo = form.numero_traslado_siigo.data
        traslado.branch_origen_id = form.branch_origen_id.data
        traslado.branch_destino_id = form.branch_destino_id.data
        traslado.responsable = form.responsable.data
        traslado.observacion = form.observacion.data
        
        # Convertir fecha a UTC
        colombia_tz = pytz.timezone('America/Bogota')
        fecha_local = form.fecha.data
        
        if fecha_local.tzinfo is None:
            fecha_local = colombia_tz.localize(fecha_local)
        
        traslado.fecha = fecha_local.astimezone(pytz.utc)
        
        db.session.commit()
        flash(f'Traslado #{traslado.numero_traslado_siigo} actualizado exitosamente', 'success')
        return redirect(url_for('traslados.ver', id=traslado.id))
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error al actualizar el traslado: {str(e)}', 'error')
        return render_template('traslados/editar.html', form=form, traslado=traslado)


@traslados_bp.route('/eliminar/<int:id>', methods=['POST'])
@login_required
@role_required('admin', 'supervisor')
def eliminar(id):
    """Eliminar un traslado y todos sus detalles"""
    traslado = Traslado.query.get_or_404(id)
    # Anti-IDOR: origen o destino (admin/supervisor global)
    denied = require_branch_access(traslado.branch_origen_id)
    if denied:
        denied = require_branch_access(traslado.branch_destino_id)
    if denied:
        return denied

    try:
        numero = traslado.numero_traslado_siigo
        db.session.delete(traslado)
        db.session.commit()
        flash(f'Traslado #{numero} eliminado correctamente.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al eliminar el traslado: {str(e)}', 'danger')

    return redirect(url_for('traslados.listar'))


@traslados_bp.route('/buscar-producto')
@login_required
def buscar_producto():
    """Buscar producto por nombre o SKU para autocompletado"""
    query = request.args.get('q', '').strip()
    
    if len(query) < 2:
        return jsonify([])
    
    productos = Product.query.filter(
        db.or_(
            Product.nombre.ilike(f'%{query}%'),
            Product.sku.ilike(f'%{query}%')
        )
    ).limit(10).all()
    
    resultados = [{
        'id': p.id,
        'nombre': p.nombre,
        'sku': p.sku or '',
        'display': f"{p.nombre} - {p.sku}" if p.sku else p.nombre
    } for p in productos]
    
    return jsonify(resultados)


@traslados_bp.route('/confirmar/<int:id>', methods=['POST'])
@login_required
@role_required('admin', 'supervisor', 'vendedor', 'tecnico')
def confirmar(id):
    """Confirmar recepción de un traslado"""
    traslado = Traslado.query.get_or_404(id)
    # Anti-IDOR: quien confirma debe ser de origen o destino (admin/supervisor global)
    denied = require_branch_access(traslado.branch_origen_id)
    if denied:
        denied = require_branch_access(traslado.branch_destino_id)
    if denied:
        return denied

    # Validar que no esté ya confirmado
    if traslado.estado == 'confirmado':
        return jsonify({'success': False, 'message': 'Este traslado ya ha sido confirmado'}), 400
    
    # Obtener nombre de quien confirma desde el request
    data = request.get_json() if request.is_json else request.form
    confirmado_por = data.get('confirmado_por', '').strip()
    
    if not confirmado_por:
        return jsonify({'success': False, 'message': 'Debe ingresar el nombre de quien confirma'}), 400
    
    try:
        # Actualizar traslado
        traslado.estado = 'confirmado'
        traslado.confirmado_por = confirmado_por
        traslado.fecha_confirmacion = datetime.now(pytz.timezone('America/Bogota'))
        
        db.session.commit()
        
        flash(f'Traslado #{traslado.numero_traslado_siigo} confirmado exitosamente por {confirmado_por}', 'success')
        
        if request.is_json:
            return jsonify({'success': True, 'message': 'Traslado confirmado exitosamente'})
        else:
            return redirect(url_for('traslados.ver', id=traslado.id))
        
    except Exception as e:
        db.session.rollback()
        if request.is_json:
            return jsonify({'success': False, 'message': f'Error al confirmar: {str(e)}'}), 500
        else:
            flash(f'Error al confirmar el traslado: {str(e)}', 'error')
            return redirect(url_for('traslados.ver', id=traslado.id))
