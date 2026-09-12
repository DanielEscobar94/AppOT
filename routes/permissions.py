from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from flask_login import login_required
from utils.decorators import role_required
from extensions import db
import json
import os

permissions_bp = Blueprint("permissions", __name__, url_prefix="/permissions")

# Archivo JSON para almacenar configuracion de permisos
PERMISSIONS_FILE = os.path.join('instance', 'permissions.json')

# Permisos por defecto del sistema
DEFAULT_PERMISSIONS = {
    'admin': {
        'clientes': {'ver': True, 'crear': True, 'editar': True, 'eliminar': True, 'exportar': True},
        'productos': {'ver': True, 'crear': True, 'editar': True, 'eliminar': True, 'exportar': True},
        'ventas': {'ver': True, 'crear': True, 'editar': True, 'eliminar': True},
        'ordenes': {'ver': True, 'crear': True, 'editar': True, 'eliminar': True},
        'salidas': {'ver': True, 'crear': True, 'editar': True, 'eliminar': True},
        'reportes': {'ventas': True, 'reparaciones': True},
        'usuarios': {'ver': True, 'crear': True, 'editar': True, 'eliminar': True},
        'sucursales': {'ver': True, 'crear': True, 'editar': True, 'eliminar': True},
        'caja': {'ver': True, 'crear': True, 'editar': True},
        'anticipos': {'ver': True, 'crear': True, 'editar': True}
    },
    'supervisor': {
        'clientes': {'ver': True, 'crear': True, 'editar': True, 'eliminar': True, 'exportar': True},
        'productos': {'ver': True, 'crear': True, 'editar': True, 'eliminar': True, 'exportar': True},
        'ventas': {'ver': True, 'crear': True, 'editar': True, 'eliminar': True},
        'ordenes': {'ver': True, 'crear': True, 'editar': True, 'eliminar': True},
        'salidas': {'ver': True, 'crear': True, 'editar': True, 'eliminar': True},
        'reportes': {'ventas': True, 'reparaciones': True},
        'usuarios': {'ver': False, 'crear': False, 'editar': False, 'eliminar': False},
        'sucursales': {'ver': True, 'crear': False, 'editar': False, 'eliminar': False},
        'caja': {'ver': True, 'crear': True, 'editar': True},
        'anticipos': {'ver': True, 'crear': True, 'editar': True}
    },
    'vendedor': {
        'clientes': {'ver': True, 'crear': True, 'editar': True, 'eliminar': False, 'exportar': False},
        'productos': {'ver': False, 'crear': False, 'editar': False, 'eliminar': False, 'exportar': False},
        'ventas': {'ver': True, 'crear': True, 'editar': True, 'eliminar': False},
        'ordenes': {'ver': True, 'crear': True, 'editar': True, 'eliminar': False},
        'salidas': {'ver': False, 'crear': False, 'editar': False, 'eliminar': False},
        'reportes': {'ventas': True, 'reparaciones': True},
        'usuarios': {'ver': False, 'crear': False, 'editar': False, 'eliminar': False},
        'sucursales': {'ver': False, 'crear': False, 'editar': False, 'eliminar': False},
        'caja': {'ver': False, 'crear': False, 'editar': False},
        'anticipos': {'ver': False, 'crear': False, 'editar': False}
    },
    'tecnico': {
        'clientes': {'ver': True, 'crear': True, 'editar': True, 'eliminar': False, 'exportar': False},
        'productos': {'ver': False, 'crear': False, 'editar': False, 'eliminar': False, 'exportar': False},
        'ventas': {'ver': False, 'crear': False, 'editar': False, 'eliminar': False},
        'ordenes': {'ver': True, 'crear': True, 'editar': True, 'eliminar': False},
        'salidas': {'ver': False, 'crear': False, 'editar': False, 'eliminar': False},
        'reportes': {'ventas': True, 'reparaciones': True},
        'usuarios': {'ver': False, 'crear': False, 'editar': False, 'eliminar': False},
        'sucursales': {'ver': False, 'crear': False, 'editar': False, 'eliminar': False},
        'caja': {'ver': False, 'crear': False, 'editar': False},
        'anticipos': {'ver': False, 'crear': False, 'editar': False}
    }
}

# Cache en memoria para evitar lecturas de disco en cada petición.
# Se invalida automáticamente cuando el archivo cambia (mtime).
_permissions_cache = None
_permissions_cache_mtime = 0.0

def load_permissions():
    """Cargar permisos desde archivo JSON con cache basado en mtime."""
    global _permissions_cache, _permissions_cache_mtime
    if os.path.exists(PERMISSIONS_FILE):
        try:
            mtime = os.path.getmtime(PERMISSIONS_FILE)
            if _permissions_cache is not None and mtime == _permissions_cache_mtime:
                return _permissions_cache
            with open(PERMISSIONS_FILE, 'r', encoding='utf-8') as f:
                _permissions_cache = json.load(f)
                _permissions_cache_mtime = mtime
                return _permissions_cache
        except Exception as e:
            print(f"Error cargando permisos: {e}")
            return DEFAULT_PERMISSIONS
    return DEFAULT_PERMISSIONS

def save_permissions(permissions):
    """Guardar permisos en archivo JSON y actualizar cache."""
    global _permissions_cache, _permissions_cache_mtime
    try:
        os.makedirs('instance', exist_ok=True)
        with open(PERMISSIONS_FILE, 'w', encoding='utf-8') as f:
            json.dump(permissions, f, indent=2, ensure_ascii=False)
        # Actualizar cache inmediatamente para reflejar el cambio
        _permissions_cache = permissions
        try:
            _permissions_cache_mtime = os.path.getmtime(PERMISSIONS_FILE)
        except Exception:
            pass
        return True
    except Exception as e:
        print(f"Error guardando permisos: {e}")
        return False

@permissions_bp.route('/')
@login_required
@role_required('admin')
def index():
    """Pagina principal de gestion de permisos"""
    permissions = load_permissions()
    
    # Informacion de modulos disponibles
    modules_info = {
        'clientes': {'nombre': 'Clientes', 'icono': 'bi-people'},
        'productos': {'nombre': 'Productos', 'icono': 'bi-box-seam'},
        'ventas': {'nombre': 'Ventas', 'icono': 'bi-cart'},
        'ordenes': {'nombre': 'Ordenes de Trabajo', 'icono': 'bi-tools'},
        'salidas': {'nombre': 'Salidas de Productos', 'icono': 'bi-box-arrow-right'},
        'reportes': {'nombre': 'Reportes', 'icono': 'bi-graph-up'},
        'usuarios': {'nombre': 'Usuarios', 'icono': 'bi-person-badge'},
        'sucursales': {'nombre': 'Sucursales', 'icono': 'bi-shop'},
        'caja': {'nombre': 'Caja', 'icono': 'bi-cash-stack'},
        'anticipos': {'nombre': 'Anticipos', 'icono': 'bi-wallet2'}
    }
    
    roles_info = {
        'admin': {'nombre': 'Administrador', 'color': 'danger'},
        'supervisor': {'nombre': 'Supervisor', 'color': 'warning'},
        'vendedor': {'nombre': 'Vendedor', 'color': 'info'},
        'tecnico': {'nombre': 'Tecnico', 'color': 'primary'}
    }
    
    return render_template('permissions/index.html', 
                         permissions=permissions,
                         modules_info=modules_info,
                         roles_info=roles_info)

@permissions_bp.route('/update', methods=['POST'])
@login_required
@role_required('admin')
def update():
    """Actualizar permisos de un rol especifico"""
    try:
        data = request.get_json()
        rol = data.get('rol')
        modulo = data.get('modulo')
        permiso = data.get('permiso')
        valor = data.get('valor', False)
        
        if not all([rol, modulo, permiso]):
            return jsonify({'success': False, 'message': 'Datos incompletos'}), 400
        
        permissions = load_permissions()
        
        # Crear estructura si no existe
        if rol not in permissions:
            permissions[rol] = {}
        if modulo not in permissions[rol]:
            permissions[rol][modulo] = {}
        
        # Actualizar permiso
        permissions[rol][modulo][permiso] = valor
        
        # Guardar
        if save_permissions(permissions):
            return jsonify({'success': True, 'message': 'Permiso actualizado correctamente'})
        else:
            return jsonify({'success': False, 'message': 'Error al guardar permisos'}), 500
            
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@permissions_bp.route('/reset', methods=['POST'])
@login_required
@role_required('admin')
def reset():
    """Restaurar permisos a valores por defecto"""
    try:
        if save_permissions(DEFAULT_PERMISSIONS):
            flash('Permisos restaurados a valores por defecto', 'success')
        else:
            flash('Error al restaurar permisos', 'danger')
    except Exception as e:
        flash(f'Error: {str(e)}', 'danger')
    
    return redirect(url_for('permissions.index'))

def check_permission(user, module, action):
    """
    Verificar si un usuario tiene un permiso especifico
    user: objeto User
    module: str (ej: 'clientes', 'productos')
    action: str (ej: 'ver', 'crear', 'editar', 'eliminar')
    """
    permissions = load_permissions()
    
    if not user or not user.is_authenticated:
        return False
    
    rol = user.rol
    
    if rol not in permissions:
        return False
    
    if module not in permissions[rol]:
        return False
    
    return permissions[rol][module].get(action, False)
