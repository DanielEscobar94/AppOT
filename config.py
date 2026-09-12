import os
from datetime import timezone, timedelta
import pytz

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# Zona horaria de Colombia (America/Bogota)
COLOMBIA_TZ = pytz.timezone('America/Bogota')


class Config:
    """Configuración base"""
    SECRET_KEY = os.environ.get("SECRET_KEY") or "clave-super-secreta-cambiame-en-produccion"

    # Zona horaria
    TIMEZONE = os.environ.get("TZ") or "America/Bogota"

    # Seguridad CSRF
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = None  # Los tokens no expiran (puedes ajustar si prefieres)

    # Sesiones
    SESSION_COOKIE_SECURE = False  # True en producción con HTTPS
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    # Usar timedelta para PERMANENT_SESSION_LIFETIME (Flask espera timedelta)
    PERMANENT_SESSION_LIFETIME = timedelta(hours=24)  # 24 horas para permitir expiración personalizada

    # Base de datos (PostgreSQL)
    # No levantamos excepciones al importar el módulo para evitar fallos
    # durante la carga temprana de la aplicación. Si falta, la app fallará
    # de forma más controlada durante el arranque o migraciones.
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 300,
    }

    # Archivos y uploads
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')

    # Cache
    CACHE_TYPE = "SimpleCache"
    CACHE_DEFAULT_TIMEOUT = 300

    # Mail (configurar si es necesario)
    MAIL_SERVER = os.environ.get('MAIL_SERVER')
    MAIL_PORT = int(os.environ.get('MAIL_PORT') or 587)
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'true').lower() in ['true', 'on', '1']
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')


class DevelopmentConfig(Config):
    """Configuración para desarrollo"""
    DEBUG = True

    # Para desarrollo, asegúrate de definir DATABASE_URL en el entorno
    # apuntando a una base de datos PostgreSQL cuando ejecutes la app.


class TestingConfig(Config):
    """Configuración para testing"""
    TESTING = True
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_DATABASE_URI = None


class ProductionConfig(Config):
    """Configuración para producción"""
    DEBUG = False

    # En producción la SECRET_KEY debe venir del entorno. La verificación
    # fail-fast se hace en app.create_app() (no aqui, para no romper imports).

    # En producción se espera que estas variables estén definidas en el
    # entorno (compose / sistema), pero no las levantamos aquí para no
    # provocar errores abruptos al importar el módulo.

    # PostgreSQL optimizado para producción
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_size": 10,
        "pool_recycle": 120,
        "pool_pre_ping": True,
        "max_overflow": 20,
        "pool_timeout": 30,
    }

    # Cache con Redis
    CACHE_TYPE = "RedisCache"
    CACHE_REDIS_URL = os.environ.get("REDIS_URL") or "redis://redis:6379/0"

    # Seguridad mejorada para producción (detrás de Cloudflare con HTTPS).
    # HttpOnly=True impide robo de sesion via XSS; Secure=True exige HTTPS.
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'

    # En producción usar timedelta (24 horas para permitir expiración personalizada a medianoche)
    PERMANENT_SESSION_LIFETIME = timedelta(hours=24)

    # Forzar HTTPS (descomentar/ajustar cuando se configure SSL)
    # PREFERRED_URL_SCHEME = 'https'

    # Logging
    LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")


# Mapeo de configuraciones
config = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}

