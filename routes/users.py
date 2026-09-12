import secrets
from flask import Blueprint, render_template, redirect, url_for, request, flash, session
from utils.decorators import admin_required, role_required
from flask_login import login_user, logout_user, login_required, current_user
from extensions import db
from models.models import User, Branch, Notification
from forms.user_form import UserForm, DeleteForm, EditUserForm
from flask import jsonify
from security_middleware import rate_limit_decorator

users_bp = Blueprint("users", __name__, url_prefix="/users")

@users_bp.route("/")
@login_required
@role_required('admin', 'supervisor')
def listar():
    usuarios = User.query.order_by(User.email.asc()).all()
    delete_form = DeleteForm()
    return render_template("users/listar.html", usuarios=usuarios, delete_form=delete_form)

@users_bp.route("/nuevo", methods=["GET", "POST"])
@login_required
@role_required('admin')
def nuevo():
    form = UserForm()
    form.branch_id.choices = [(0, "Sin Sucursal")] + [(b.id, b.nombre) for b in Branch.query.order_by(Branch.nombre).all()]

    if form.validate_on_submit():
        # ensure branch_id is None if not selected
        branch_id = form.branch_id.data if form.branch_id.data and form.branch_id.data > 0 else None
        user = User(
            username=form.username.data.strip(),
            email=form.email.data.strip(),
            rol=form.rol.data,
            branch_id=branch_id
        )
        user.set_password(form.password.data)

        # check username/email uniqueness
        existing_user = User.query.filter((User.username == user.username) | (User.email == user.email)).first()
        if existing_user:
            flash("El nombre de usuario o correo ya esta en uso", "danger")
            return render_template("users/nuevo.html", form=form)

        try:
            db.session.add(user)
            db.session.commit()
            flash("Usuario creado correctamente", "success")
            return redirect(url_for("users.listar"))
        except Exception as e:
            db.session.rollback()
            flash(f"Error al guardar: {e}", "danger")

    return render_template("users/nuevo.html", form=form, is_edit=False)


@users_bp.route('/<int:id>/editar', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def editar(id):
    user = User.query.get_or_404(id)
    form = EditUserForm(obj=user)
    form.branch_id.choices = [(0, "Sin Sucursal")] + [(b.id, b.nombre) for b in Branch.query.order_by(Branch.nombre).all()]

    if form.validate_on_submit():
        # update fields
        old_rol = user.rol
        user.username = form.username.data.strip()
        user.email = form.email.data.strip()
        user.rol = form.rol.data
        user.branch_id = form.branch_id.data if form.branch_id.data and form.branch_id.data > 0 else None

        # Si cambia el rol o la contraseña de otro usuario, invalida su sesión activa
        # para que los nuevos permisos apliquen de inmediato en su próximo acceso.
        session_invalidated = False
        if user.id != current_user.id:
            if user.rol != old_rol or form.password.data:
                user.session_id = None
                session_invalidated = True

        if form.password.data:
            user.set_password(form.password.data)

        # uniqueness check
        existing = User.query.filter(((User.username == user.username) | (User.email == user.email)) & (User.id != user.id)).first()
        if existing:
            flash('El nombre de usuario o correo ya esta en uso por otro usuario', 'danger')
            return render_template('users/nuevo.html', form=form, is_edit=True)

        try:
            db.session.commit()
            if session_invalidated:
                flash('Usuario actualizado. El usuario deberá iniciar sesión nuevamente para que los cambios apliquen.', 'success')
            else:
                flash('Usuario actualizado', 'success')
            return redirect(url_for('users.listar'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error al actualizar: {e}', 'danger')

    return render_template('users/nuevo.html', form=form, is_edit=True)


@users_bp.route('/<int:id>/eliminar', methods=['POST'])
@login_required
@role_required('admin')
def eliminar(id):
    form = DeleteForm()
    if not form.validate_on_submit():
        flash('Token CSRF invalido o peticion no valida', 'danger')
        return redirect(url_for('users.listar'))

    user = User.query.get_or_404(id)
    # Prevent an admin from deleting their own account
    if current_user.is_authenticated and user.id == current_user.id:
        flash('No puedes eliminar tu propio usuario mientras estas autenticado', 'danger')
        return redirect(url_for('users.listar'))
    try:
        db.session.delete(user)
        db.session.commit()
        flash('Usuario eliminado', 'success')
    except Exception as e:
        db.session.rollback()
    return redirect(url_for('users.listar'))

@users_bp.route("/login", methods=["GET", "POST"])
@rate_limit_decorator(max_requests=20, window=60)
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        if not username or not password:
            flash("Por favor ingresa usuario y contraseña", "danger")
            return render_template("users/login.html")

        user = User.query.filter_by(email=username).first()
        if user:
            password_valid = user.check_password(password)
        if user and user.check_password(password):
                from flask import current_app
                from datetime import datetime, timedelta
                import pytz
                from models.models import LoginLog

                # Sesión única: generar token criptográfico seguro
                # El token se guarda en la cookie de sesión y en la BD.
                # Cualquier login posterior o cambio de rol/contraseña invalida la sesión anterior.
                user_token = secrets.token_hex(32)
                session['session_token'] = user_token
                user.session_id = user_token

                # Registrar login en logs
                # Obtener IP real del cliente (detrás de Cloudflare)
                ip_address = request.headers.get('CF-Connecting-IP') or request.headers.get('X-Forwarded-For', request.remote_addr)
                user_agent = request.headers.get('User-Agent')
                login_log = LoginLog(
                    user_id=user.id,
                    ip_address=ip_address,
                    user_agent=user_agent,
                    success=True
                )
                db.session.add(login_log)
                db.session.commit()

                login_user(user)

                # Lógica de expiración de sesión
                try:
                    local_tz = current_app.config.get('TIMEZONE') or pytz.timezone('America/Bogota')
                    now_utc_for_calc = datetime.now(pytz.utc)
                    now_local = now_utc_for_calc.astimezone(local_tz)
                    
                    if user.rol == 'vendedor':
                        # Para vendedores: expirar siempre a la medianoche siguiente (00:00 local)
                        next_midnight_local = (now_local + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
                        next_midnight_utc = next_midnight_local.astimezone(pytz.utc)
                        session['expires_at_midnight'] = next_midnight_utc.isoformat()
                        delta = next_midnight_utc - now_utc_for_calc
                    elif user.rol != 'admin':
                        # Para otros usuarios no admin: expirar a medianoche
                        next_midnight_local = (now_local + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
                        next_midnight_utc = next_midnight_local.astimezone(pytz.utc)
                        session['expires_at_midnight'] = next_midnight_utc.isoformat()
                        delta = next_midnight_utc - now_utc_for_calc
                    else:
                        # Para admin: sesión normal con inactividad
                        session['last_activity'] = datetime.now(pytz.utc).isoformat()
                        session.modified = True
                        # No ajustar permanent_session_lifetime para admin
                        delta = None
                    
                    if delta and user.rol != 'admin':
                        if delta.total_seconds() < 60:
                            delta = timedelta(seconds=60)
                        current_app.permanent_session_lifetime = delta
                        session.permanent = True
                        session.modified = True
                        
                except Exception as e:
                    print(f"Error configurando expiración de sesión: {e}")
                    pass
                # Si el rol es 'ventas' o 'vendedor', redirigimos al dashboard del vendedor
                # (evita redirigir automaticamente al POS). Si quieres que 'vendedor'
                # abra el POS en vez del dashboard, dilo y lo ajusto.
                if user.rol in ("ventas", "vendedor"):
                    session["branch_id"] = user.branch_id
                    return redirect(url_for("dashboard.index"))
                # Si es tecnico, redirigir al listado de ordenes
                if user.rol == "tecnico":
                    # opcional: mantener sucursal en sesion si existe
                    session["branch_id"] = user.branch_id
                    return redirect(url_for("ordenes.listar_ordenes"))
                # Si es admin, abrir el dashboard general (index.html)
                if user.rol == "admin":
                    return redirect(url_for("dashboard.index"))
                return redirect(url_for("dashboard.index"))
        else:
            # Registrar intento fallido para auditoria (deteccion de fuerza bruta).
            # user_id es NOT NULL: solo se registra si el usuario existe.
            try:
                if user:
                    from models.models import LoginLog
                    ip_address = request.headers.get('CF-Connecting-IP') or request.headers.get('X-Forwarded-For', request.remote_addr)
                    db.session.add(LoginLog(
                        user_id=user.id,
                        ip_address=ip_address,
                        user_agent=request.headers.get('User-Agent'),
                        success=False
                    ))
                    db.session.commit()
            except Exception:
                try:
                    db.session.rollback()
                except Exception:
                    pass
            flash("Usuario o contrasena incorrectos", "danger")
    return render_template("users/login.html")

@users_bp.route("/logout")
@login_required
def logout():
    try:
        if current_user.is_authenticated and current_user.session_id:
            current_user.session_id = None
            db.session.commit()
    except Exception:
        pass
    logout_user()
    flash("Sesion cerrada", "info")
    return redirect(url_for("users.login"))


@users_bp.route('/notifications')
@login_required
def notifications():
    # Return recent notifications for current user as JSON
    notifs = Notification.query.filter_by(user_id=current_user.id).order_by(Notification.created_at.desc()).limit(10).all()
    data = [
        {
            'id': n.id,
            'message': n.message,
            'link': n.link,
            'created_at': n.created_at.isoformat(),
            'read': n.read
        } for n in notifs
    ]
    return jsonify(data)


@users_bp.route('/notifications/mark_read/<int:notif_id>', methods=['POST'])
@login_required
def notifications_mark_read(notif_id):
    n = Notification.query.get_or_404(notif_id)
    if n.user_id != current_user.id:
        return jsonify({'error': 'No autorizado'}), 403
    n.read = True
    db.session.commit()
    return jsonify({'ok': True})


@users_bp.route('/notifications/mark_all', methods=['POST'])
@login_required
def notifications_mark_all():
    # Eliminar todas las notificaciones del usuario en lugar de solo marcarlas como leidas
    Notification.query.filter_by(user_id=current_user.id).delete()
    db.session.commit()
    return jsonify({'ok': True})

@users_bp.route('/login_logs')
@login_required
@role_required('admin')
def login_logs():
    from models.models import LoginLog
    from flask import request
    
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 25, type=int)
    
    # Filtros
    user_id = request.args.get('user_id', type=int)
    fecha_desde = request.args.get('fecha_desde')
    fecha_hasta = request.args.get('fecha_hasta')
    
    query = LoginLog.query.join(User)
    
    if user_id:
        query = query.filter(LoginLog.user_id == user_id)
    
    if fecha_desde:
        from datetime import datetime
        try:
            fecha_desde_dt = datetime.strptime(fecha_desde, '%Y-%m-%d')
            query = query.filter(LoginLog.login_time >= fecha_desde_dt)
        except ValueError:
            pass
    
    if fecha_hasta:
        from datetime import datetime
        try:
            fecha_hasta_dt = datetime.strptime(fecha_hasta, '%Y-%m-%d')
            fecha_hasta_dt = fecha_hasta_dt.replace(hour=23, minute=59, second=59)
            query = query.filter(LoginLog.login_time <= fecha_hasta_dt)
        except ValueError:
            pass
    
    logs_pagination = query.order_by(LoginLog.login_time.desc()).paginate(page=page, per_page=per_page, error_out=False)
    
    # Lista de usuarios para el filtro
    users = User.query.order_by(User.email).all()
    
    return render_template('users/login_logs.html', 
                         logs=logs_pagination.items,
                         logs_pagination=logs_pagination,
                         users=users,
                         filtros={
                             'user_id': user_id,
                             'fecha_desde': fecha_desde,
                             'fecha_hasta': fecha_hasta
                         })
