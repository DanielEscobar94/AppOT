"""
Middleware de seguridad para Flask
Agrega headers de seguridad HTTP y otras protecciones
"""

from flask import request, g
from functools import wraps
import secrets

def add_security_headers(response):
    """
    Agrega headers de seguridad HTTP a todas las respuestas
    """
    # Prevenir clickjacking: ninguna vista usa iframes
    response.headers['X-Frame-Options'] = 'DENY'

    # Prevenir MIME-sniffing
    response.headers['X-Content-Type-Options'] = 'nosniff'

    # Política de referrer
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'

    # Quitar huella del servidor
    response.headers.pop('Server', None)

    # Content Security Policy.
    # Nota: 'unsafe-inline' en scripts/estilos sigue siendo necesario por los
    # <script>/<style> inline de las plantillas; la mitigacion XSS principal
    # es el autoescape de Jinja2 + escapeHtml en el JS (ver informe SAST).
    csp = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://static.cloudflareinsights.com; "
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com; "
        "font-src 'self' https://cdn.jsdelivr.net https://fonts.gstatic.com; "
        "img-src 'self' data:; "
        "connect-src 'self' https://cdn.jsdelivr.net; "
        "object-src 'none'; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self'; "
        "upgrade-insecure-requests;"
    )
    response.headers['Content-Security-Policy'] = csp

    # HSTS solo sobre HTTPS (con ProxyFix, is_secure refleja el esquema real
    # detras de Cloudflare). Sobre HTTP el header se ignora: sin breakage.
    try:
        if request.is_secure:
            response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    except RuntimeError:
        pass

    return response


def rate_limit_decorator(max_requests=100, window=60):
    """
    Decorador simple de rate limiting
    max_requests: número máximo de requests
    window: ventana de tiempo en segundos
    """
    from collections import defaultdict
    from time import time
    
    requests_log = defaultdict(list)
    
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Usar IP del cliente como identificador
            client_id = request.remote_addr
            current_time = time()
            
            # Limpiar requests antiguos
            requests_log[client_id] = [
                req_time for req_time in requests_log[client_id]
                if current_time - req_time < window
            ]
            
            # Verificar límite
            if len(requests_log[client_id]) >= max_requests:
                from flask import jsonify
                return jsonify({
                    'error': 'rate_limit_exceeded',
                    'message': 'Demasiadas solicitudes. Intenta de nuevo en unos minutos.'
                }), 429
            
            # Registrar request actual
            requests_log[client_id].append(current_time)
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def generate_csrf_token():
    """Genera un token CSRF seguro"""
    if '_csrf_token' not in g:
        g._csrf_token = secrets.token_hex(32)
    return g._csrf_token


def validate_file_upload(file, allowed_extensions=None, max_size_mb=5):
    """
    Valida archivos subidos
    
    Args:
        file: FileStorage object
        allowed_extensions: set de extensiones permitidas (ej: {'png', 'jpg', 'pdf'})
        max_size_mb: tamaño máximo en MB
    
    Returns:
        tuple: (is_valid, error_message)
    """
    if not file or file.filename == '':
        return False, "No se seleccionó ningún archivo"
    
    # Validar extensión
    if allowed_extensions:
        filename = file.filename.lower()
        if '.' not in filename:
            return False, "El archivo debe tener una extensión"
        
        ext = filename.rsplit('.', 1)[1]
        if ext not in allowed_extensions:
            return False, f"Extensión no permitida. Permitidas: {', '.join(allowed_extensions)}"
    
    # Validar tamaño (leer en chunks para no consumir mucha memoria)
    file.seek(0, 2)  # Ir al final del archivo
    size = file.tell()
    file.seek(0)  # Volver al inicio
    
    max_size_bytes = max_size_mb * 1024 * 1024
    if size > max_size_bytes:
        return False, f"El archivo excede el tamaño máximo de {max_size_mb}MB"
    
    # Sanitizar nombre de archivo
    import re
    from werkzeug.utils import secure_filename
    
    safe_filename = secure_filename(file.filename)
    if not safe_filename or safe_filename != file.filename:
        return False, "Nombre de archivo inválido. Use solo letras, números y guiones"
    
    return True, None


def sanitize_html_input(text):
    """
    Sanitiza input HTML para prevenir XSS
    Remueve etiquetas peligrosas
    """
    import re
    if not text:
        return text
    
    # Remover scripts
    text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL | re.IGNORECASE)
    
    # Remover eventos inline (onclick, onerror, etc.)
    text = re.sub(r'\s*on\w+\s*=\s*["\'][^"\']*["\']', '', text, flags=re.IGNORECASE)
    
    # Remover javascript: URLs
    text = re.sub(r'javascript:', '', text, flags=re.IGNORECASE)
    
    return text


def validate_password_strength(password):
    """
    Valida la fortaleza de una contraseña
    
    Requisitos:
    - Mínimo 8 caracteres
    - Al menos una mayúscula
    - Al menos una minúscula
    - Al menos un número
    - Al menos un carácter especial
    
    Returns:
        tuple: (is_valid, error_message)
    """
    if len(password) < 8:
        return False, "La contraseña debe tener al menos 8 caracteres"
    
    if not any(c.isupper() for c in password):
        return False, "La contraseña debe contener al menos una mayúscula"
    
    if not any(c.islower() for c in password):
        return False, "La contraseña debe contener al menos una minúscula"
    
    if not any(c.isdigit() for c in password):
        return False, "La contraseña debe contener al menos un número"
    
    special_chars = "!@#$%^&*()_+-=[]{}|;:,.<>?"
    if not any(c in special_chars for c in password):
        return False, "La contraseña debe contener al menos un carácter especial (!@#$%^&*...)"
    
    # Verificar que no sea una contraseña común
    common_passwords = [
        'password', '12345678', 'qwerty', 'admin', 'letmein',
        'welcome', 'monkey', '1234567890', 'password123'
    ]
    if password.lower() in common_passwords:
        return False, "La contraseña es demasiado común. Elige una más segura"
    
    return True, None


def audit_log(user, action, details=None):
    """
    Registra acciones importantes para auditoría
    
    Args:
        user: Usuario que realiza la acción
        action: Descripción de la acción (ej: 'login', 'delete_product')
        details: Detalles adicionales (dict)
    """
    import logging
    from datetime import datetime
    
    logger = logging.getLogger('security_audit')
    
    log_entry = {
        'timestamp': datetime.utcnow().isoformat(),
        'user_id': user.id if user else None,
        'username': user.username if user else 'anonymous',
        'action': action,
        'ip': request.remote_addr,
        'user_agent': request.user_agent.string,
        'details': details or {}
    }
    
    logger.info(f"AUDIT: {log_entry}")
