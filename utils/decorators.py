from functools import wraps
from flask import redirect, url_for, flash, jsonify, request
from flask_login import current_user

# Roles con visibilidad global (pueden operar sobre cualquier sucursal)
GLOBAL_ROLES = ('admin', 'supervisor')


def _is_ajax():
    """Detecta peticiones AJAX / API para responder JSON en vez de redirect."""
    try:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return True
        if request.is_json:
            return True
        accept = request.headers.get('Accept', '')
        if 'application/json' in accept:
            return True
    except RuntimeError:
        return False
    return False


def _deny_branch():
    """Respuesta 403/redirect cuando se accede a un recurso de otra sucursal."""
    if _is_ajax():
        return jsonify({"error": "forbidden", "message": "Acceso denegado: el recurso pertenece a otra sucursal"}), 403
    flash("Acceso denegado: el recurso pertenece a otra sucursal", "danger")
    return redirect(url_for("dashboard.index"))


def require_branch_access(obj_branch_id):
    """Guardia anti-IDOR por sucursal.

    Retorna None si el acceso es legitimo, o una respuesta de denegacion
    (usar como: ``denied = require_branch_access(x); if denied: return denied``).
    - admin/supervisor: acceso global.
    - demas roles: solo objetos de su propia sucursal (current_user.branch_id).
    """
    try:
        if not current_user.is_authenticated:
            return _deny_branch()
        if getattr(current_user, 'rol', None) in GLOBAL_ROLES:
            return None
        user_branch = getattr(current_user, 'branch_id', None)
        if user_branch and obj_branch_id and int(user_branch) == int(obj_branch_id):
            return None
    except (RuntimeError, TypeError, ValueError):
        pass
    return _deny_branch()


def scoped_branch_param(param_branch_id):
    """Scoping por defecto para listados/reportes.
    - admin/supervisor: respetan el parametro (o None = todas).
    - demas roles: siempre su propia sucursal (el parametro se ignora para
      evitar enumeracion cruzada entre sucursales).
    Retorna el branch_id efectivo o None."""
    try:
        if getattr(current_user, 'rol', None) not in GLOBAL_ROLES:
            return getattr(current_user, 'branch_id', None)
    except RuntimeError:
        pass
    return param_branch_id

# Decorador general para roles

def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Detect AJAX / API-style requests: X-Requested-With or JSON Accept
            def _is_ajax():
                try:
                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                        return True
                    if request.is_json:
                        return True
                    accept = request.headers.get('Accept', '')
                    if 'application/json' in accept:
                        return True
                except RuntimeError:
                    # request context not available
                    return False
                return False

            if not current_user.is_authenticated:
                if _is_ajax():
                    return jsonify({"error": "authentication_required", "message": "Debes iniciar sesion"}), 403
                flash("Debes iniciar sesion", "warning")
                return redirect(url_for("users.login"))
            if current_user.rol not in roles:
                if _is_ajax():
                    return jsonify({"error": "forbidden", "message": "Acceso denegado: no tienes permisos suficientes"}), 403
                flash("Acceso denegado: no tienes permisos suficientes", "danger")
                return redirect(url_for("dashboard.index"))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# Ejemplo: @role_required('admin', 'supervisor')
# Tambien puedes seguir usando admin_required si lo necesitas

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        def _is_ajax():
            try:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return True
                if request.is_json:
                    return True
                accept = request.headers.get('Accept', '')
                if 'application/json' in accept:
                    return True
            except RuntimeError:
                return False
            return False

        if not current_user.is_authenticated:
            if _is_ajax():
                return jsonify({"error": "authentication_required", "message": "Debes iniciar sesion"}), 403
            flash("Debes iniciar sesion", "warning")
            return redirect(url_for("users.login"))

        if current_user.rol != "admin":
            if _is_ajax():
                return jsonify({"error": "forbidden", "message": "Acceso denegado: solo administradores"}), 403
            flash("Acceso denegado: solo administradores", "danger")
            return redirect(url_for("dashboard.index"))

        return f(*args, **kwargs)
    return decorated_function
