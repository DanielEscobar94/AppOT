from dotenv import load_dotenv

# Cargar variables de entorno desde .env
load_dotenv()

from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from werkzeug.middleware.proxy_fix import ProxyFix
from config import config
from extensions import db, migrate, csrf
from flask_login import LoginManager, login_user, login_required
from models.models import User, OrdenTrabajo, ExportacionSiigo, EstadoExportacion
import os
import pytz
from datetime import datetime, date as date_cls
from security_middleware import add_security_headers

# Importar blueprints
from routes.dashboard import dashboard_bp
from routes.clients import clients_bp
from routes.products import products_bp
from routes.categories import categories_bp
from routes.sales import bp as sales_bp
from routes.users import users_bp
from routes.branches import branches_bp
from routes.ordenes_trabajo import ordenes_bp

login_manager = LoginManager()
login_manager.login_view = "users.login"

def create_app(config_name=None):
    """Factory para crear la aplicación Flask"""
    app = Flask(__name__)
    
    # Determinar configuración
    if config_name is None:
        config_name = os.environ.get('FLASK_ENV', 'development')
    
    app.config.from_object(config[config_name])

    # Fail-fast: en produccion la SECRET_KEY no puede ser el valor de desarrollo
    if config_name == 'production':
        secret = app.config.get('SECRET_KEY') or os.environ.get('SECRET_KEY')
        if not secret or secret == 'clave-super-secreta-cambiame-en-produccion':
            raise RuntimeError(
                'SECRET_KEY no definida: configure la variable de entorno SECRET_KEY en producción'
            )
        app.config['SECRET_KEY'] = secret
    
    # Configurar ProxyFix para Cloudflare
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
    
    # Configurar zona horaria
    try:
        tz_name = app.config.get('TIMEZONE', 'America/Bogota')
        app.config['TIMEZONE'] = pytz.timezone(tz_name)
        
        # Template filter: muestra la fecha/hora exactamente como está en la BD
        @app.template_filter('local_datetime')
        def local_datetime_filter(dt, fmt='%d/%m/%Y %H:%M'):
            """Muestra el datetime tal como está guardado en la BD (sin conversión)."""
            if dt is None:
                return '—'
            try:
                if isinstance(dt, date_cls) and not isinstance(dt, datetime):
                    dt = datetime(dt.year, dt.month, dt.day)
                # Si tiene timezone info, quitar para mostrar el valor literal
                if hasattr(dt, 'tzinfo') and dt.tzinfo is not None:
                    dt = dt.replace(tzinfo=None)
                return dt.strftime(fmt)
            except Exception as e:
                print(f"Error en local_datetime filter: {e}, dt={dt}")
                return str(dt)
        
        # Template filter para solo fecha (sin hora)
        @app.template_filter('local_date')
        def local_date_filter(dt, fmt='%d/%m/%Y'):
            """Muestra la fecha tal como está en la BD (sin conversión)."""
            if dt is None:
                return '—'
            try:
                if isinstance(dt, date_cls) and not isinstance(dt, datetime):
                    return dt.strftime(fmt)
                if hasattr(dt, 'tzinfo') and dt.tzinfo is not None:
                    dt = dt.replace(tzinfo=None)
                return dt.strftime(fmt)
            except Exception as e:
                print(f"Error en local_date filter: {e}, dt={dt}")
                return str(dt)
        
        # Template filter para solo hora
        @app.template_filter('local_time')
        def local_time_filter(dt, fmt='%H:%M'):
            """Muestra la hora tal como está en la BD (sin conversión)."""
            if dt is None:
                return '—'
            try:
                if isinstance(dt, date_cls) and not isinstance(dt, datetime):
                    dt = datetime(dt.year, dt.month, dt.day)
                if hasattr(dt, 'tzinfo') and dt.tzinfo is not None:
                    dt = dt.replace(tzinfo=None)
                return dt.strftime(fmt)
            except Exception as e:
                print(f"Error en local_time filter: {e}, dt={dt}")
                return str(dt)
        
        # Template filter para parsear JSON
        @app.template_filter('fromjson')
        def fromjson_filter(json_str):
            """Parsea una cadena JSON y retorna el objeto Python"""
            if not json_str:
                return None
            try:
                import json
                return json.loads(json_str)
            except Exception as e:
                print(f"Error en fromjson filter: {e}, json_str={json_str}")
                return None
                
    except Exception as e:
        print(f"Warning: Could not configure timezone: {e}")
    
    # Crear directorio de uploads si no existe
    os.makedirs(app.config.get('UPLOAD_FOLDER', 'static/uploads'), exist_ok=True)

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    # Proteccion CSRF global (Flask-WTF): valida todos los POST/PUT/PATCH/DELETE.
    # Los formularios deben incluir {{ form.hidden_tag() }} o {{ csrf_token() }};
    # el JS debe enviar el header X-CSRFToken (ver auth_interceptor.js).
    csrf.init_app(app)

    # Agregar headers de seguridad a todas las respuestas
    @app.after_request
    def apply_security_headers(response):
        return add_security_headers(response)

    # Manejadores de error genericos: nunca fugan stacktraces ni SQL al cliente
    @app.errorhandler(404)
    def handle_404(error):
        try:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json:
                return jsonify({'error': 'not_found', 'message': 'Recurso no encontrado'}), 404
        except RuntimeError:
            pass
        return render_template('error.html', code=404, message='Recurso no encontrado'), 404

    @app.errorhandler(500)
    def handle_500(error):
        app.logger.exception('Error interno no controlado')
        try:
            db.session.rollback()
        except Exception:
            pass
        try:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json:
                return jsonify({'error': 'internal_error', 'message': 'Error interno del servidor'}), 500
        except RuntimeError:
            pass
        return render_template('error.html', code=500, message='Error interno del servidor'), 500

    @app.errorhandler(413)
    def handle_413(error):
        try:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json:
                return jsonify({'error': 'file_too_large', 'message': 'Archivo demasiado grande (máximo 16 MB)'}), 413
        except RuntimeError:
            pass
        flash('Archivo demasiado grande (máximo 16 MB)', 'danger')
        return redirect(request.referrer or url_for('dashboard.index'))

    @app.errorhandler(403)
    def handle_403(error):
        try:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json:
                return jsonify({'error': 'forbidden', 'message': 'Acceso denegado'}), 403
        except RuntimeError:
            pass
        flash('Acceso denegado', 'danger')
        return redirect(url_for('dashboard.index'))

    # Enforce session policies:
    # - Non-admin users: expire at daily midnight (session['expires_at_midnight'])
    # - Admin users: expire after 1 minute of inactivity (session['last_activity'])
    @app.before_request
    def enforce_session_policies():
        from flask_login import current_user, logout_user
        from flask import session, redirect, url_for, flash, request
        from datetime import datetime
        import pytz

        try:
            # No aplicar a rutas públicas o recursos estáticos
            if request.endpoint in (login_manager.login_view, 'static', 'health_check'):
                return None

            if not (current_user and getattr(current_user, 'is_authenticated', False)):
                return None

            now_utc = datetime.now(pytz.utc)

            # Validar integridad de sesión: token generado en login almacenado en cookie y BD.
            # Si el token en cookie no coincide con el de la BD, la sesión fue invalidada
            # (admin cambió rol/contraseña, o el usuario inició sesión desde otro dispositivo).
            session_token = session.get('session_token')
            if session_token is not None:
                db_session_id = getattr(current_user, 'session_id', None)
                if db_session_id is None or db_session_id != session_token:
                    logout_user()
                    session.clear()
                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json or 'application/json' in request.headers.get('Accept', ''):
                        from flask import jsonify
                        return jsonify({'error': 'session_expired', 'message': 'Tu sesión fue cerrada. Inicia sesión nuevamente.'}), 401
                    flash('Tu sesión fue cerrada. Inicia sesión nuevamente.', 'info')
                    return redirect(url_for(login_manager.login_view))

            # Admin inactivity timeout (1 minute)
            if getattr(current_user, 'rol', None) == 'admin':
                last_activity_iso = session.get('last_activity')
                if last_activity_iso:
                    try:
                        last_activity = datetime.fromisoformat(last_activity_iso)
                        if last_activity.tzinfo is None:
                            last_activity = pytz.utc.localize(last_activity)
                        idle_seconds = (now_utc - last_activity).total_seconds()
                        if idle_seconds >= 1800:  # 30 minutos
                            # Forzar cierre de sesión por inactividad
                            logout_user()
                            session.clear()
                            if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json or 'application/json' in request.headers.get('Accept', ''):
                                from flask import jsonify
                                return jsonify({'error': 'session_expired', 'message': 'Sesión cerrada por inactividad (30 min).'}), 401
                            flash('La sesión ha sido cerrada por inactividad (admin).', 'info')
                            return redirect(url_for(login_manager.login_view))
                    except Exception:
                        # Si falla el parseo, no bloquear la petición
                        pass

                # Actualizar el last_activity para cada petición válida (sliding window)
                try:
                    session['last_activity'] = now_utc.isoformat()
                    session.modified = True
                except Exception:
                    pass

                return None

            # Non-admin users: daily expiry (midnight for most, noon for vendedores)
            # Para vendedores y otros no-admin usamos expiración diaria a medianoche.
            # Antes los vendedores usaban mediodía; ahora todos los vendedores
            # expirarán a la medianoche siguiente independientemente de la hora de login.
            if getattr(current_user, 'rol', None) == 'vendedor':
                expires_iso = session.get('expires_at_midnight')
                expiry_message = 'La sesión ha expirado por cierre diario (medianoche).'
            else:
                expires_iso = session.get('expires_at_midnight')
                expiry_message = 'La sesión ha expirado por cierre diario (medianoche).'
                
            if not expires_iso:
                # Si no está presente, no forzamos logout aquí
                return None

            try:
                expiry = datetime.fromisoformat(expires_iso)
                if expiry.tzinfo is None:
                    expiry = pytz.utc.localize(expiry)

                if now_utc >= expiry:
                    logout_user()
                    session.clear()
                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json or 'application/json' in request.headers.get('Accept', ''):
                        from flask import jsonify
                        return jsonify({'error': 'session_expired', 'message': expiry_message}), 401
                    flash(expiry_message, 'info')
                    return redirect(url_for(login_manager.login_view))
            except Exception:
                # No bloquear la petición si hay error en parseo
                return None
        except RuntimeError:
            return None

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # Custom unauthorized handler: return JSON 401/403 for AJAX/API requests
    @login_manager.unauthorized_handler
    def unauthorized_callback():
        from flask import request, jsonify
        try:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json or 'application/json' in request.headers.get('Accept', ''):
                return jsonify({"error": "authentication_required", "message": "Debes iniciar sesión"}), 401
        except RuntimeError:
            pass
        return redirect(url_for(login_manager.login_view))

    # Context processor to expose unread notifications to templates
    @app.context_processor
    def inject_notifications():
        try:
            from flask_login import current_user
            if current_user and getattr(current_user, 'is_authenticated', False):
                from models.models import Notification, SolicitudEliminacionVenta
                unread = Notification.query.filter_by(user_id=current_user.id, read=False).order_by(Notification.created_at.desc()).limit(5).all()
                count = Notification.query.filter_by(user_id=current_user.id, read=False).count()
                
                # Contar solicitudes de eliminación pendientes para supervisores/admins
                solicitudes_pendientes_count = 0
                if current_user.rol in ['supervisor', 'admin']:
                    solicitudes_pendientes_count = SolicitudEliminacionVenta.query.filter_by(estado='pendiente').count()
                
                return {
                    '_unread_notifications': unread, 
                    '_unread_notifications_count': count,
                    '_solicitudes_eliminacion_pendientes': solicitudes_pendientes_count
                }
        except Exception:
            pass
        return {'_unread_notifications': [], '_unread_notifications_count': 0, '_solicitudes_eliminacion_pendientes': 0}

    # Inicializar usuario admin automáticamente
    def init_default_admin():
        """Crear usuario administrador por defecto si no existe"""
        try:
            # Verificar si ya existe el usuario admin
            admin_user = User.query.filter_by(email='admin@correo.com').first()
            
            if admin_user:
                print("✅ Usuario admin ya existe")
                return admin_user
            
            # Crear usuario admin
            from werkzeug.security import generate_password_hash
            admin_user = User(
                email='admin@correo.com',
                username='admin',
                rol='admin'
            )
            # Password inicial sobreescribible por entorno (no dejar rastro en logs)
            admin_password = os.environ.get('ADMIN_INITIAL_PASSWORD', '%%S0p0rt3-741%%')
            # Usar el método set_password del modelo para compatibilidad
            admin_user.set_password(admin_password)

            db.session.add(admin_user)
            db.session.commit()

            print("Usuario administrador creado: admin@correo.com (password inicial configurada)")
            
            return admin_user
            
        except Exception as e:
            print(f"❌ Error al crear usuario admin: {e}")
            try:
                db.session.rollback()
            except:
                pass
            return None

    def init_ot_categories():
        """Crear categorías básicas de órdenes de trabajo si no existen"""
        try:
            from models.models import OTCategory
            
            categorias_basicas = [
                'Reloj',
                'Bateria', 
                'Articulo Electronico'
            ]
            
            created_count = 0
            
            for nombre_categoria in categorias_basicas:
                existe = OTCategory.query.filter_by(nombre=nombre_categoria).first()
                
                if not existe:
                    nueva_categoria = OTCategory(
                        nombre=nombre_categoria,
                        activo=True
                    )
                    db.session.add(nueva_categoria)
                    created_count += 1
            
            if created_count > 0:
                db.session.commit()
                print(f"✅ Se crearon {created_count} categorías de OT")
            
        except Exception as e:
            print(f"⚠️ Error al inicializar categorías OT: {e}")
            try:
                db.session.rollback()
            except:
                pass

    # Ejecutar inicialización después de configurar la app
    with app.app_context():
        try:
            # db.create_all()  # Comentado para evitar duplicación de tablas
            # Inicializar usuario admin
            init_default_admin()
            # Inicializar categorías de órdenes de trabajo
            init_ot_categories()
        except Exception as e:
            print(f"⚠️ Aviso durante inicialización: {e}")

    # Health check endpoint para monitoreo y Docker (publico por diseno,
    # pero minimo: sin detalles de error ni version para no dar oraculo)
    @app.route('/health')
    def health_check():
        """Endpoint de health check para monitoreo y Docker health checks"""
        try:
            # Verificar conexión a la base de datos (SQLAlchemy 2.x compatible)
            db.session.execute(db.text('SELECT 1'))
            return jsonify({'status': 'healthy'}), 200
        except Exception as e:
            app.logger.error(f'Health check failed: {e}')
            return jsonify({'status': 'unhealthy'}), 500

    # Registrar blueprints
    app.register_blueprint(clients_bp)
    app.register_blueprint(products_bp)
    app.register_blueprint(categories_bp)
    app.register_blueprint(sales_bp)
    app.register_blueprint(users_bp)
    app.register_blueprint(branches_bp)
    app.register_blueprint(dashboard_bp) 
    app.register_blueprint(ordenes_bp)
    
    # Importar y registrar blueprint de caja
    from routes.caja import bp as caja_bp
    app.register_blueprint(caja_bp)
    
    # Importar y registrar blueprint de anticipos
    from routes.anticipos import anticipos_bp
    app.register_blueprint(anticipos_bp)
    
    # Importar y registrar blueprint de reportes
    from routes.reportes import reportes_bp
    app.register_blueprint(reportes_bp)
    
    # Importar y registrar blueprint de salidas
    from routes.salidas import salidas_bp
    app.register_blueprint(salidas_bp)
    
    # Importar y registrar blueprint de permisos
    from routes.permissions import permissions_bp
    app.register_blueprint(permissions_bp)
    
    # Importar y registrar blueprint de traslados
    from routes.traslados import traslados_bp
    app.register_blueprint(traslados_bp)
   
    @app.route("/", methods=["GET", "POST"])
    @login_required
    def index():
        # If reached, user is authenticated — send to dashboard
        return redirect(url_for("dashboard.index"))
    
    # Ruta de prueba para el carrito (solo fuera de produccion)
    @app.route("/test/carrito")
    @login_required
    def test_carrito():
        if config_name == 'production' and not app.debug:
            return render_template("error.html", code=404, message="Recurso no encontrado"), 404
        return render_template("test_carrito.html")
    
    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True, port=8000)