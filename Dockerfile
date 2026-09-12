# --- APPOT - Imagen de producción ---
# Las dependencias se instalan SOLO si no están presentes (check en entrypoint.sh),
# guardadas en un volumen persistente (/root/.local). Así el redeploy no reinstala.

FROM python:3.13-slim

LABEL maintainer="John Arcila <john.arcilav@gmail.com>"
LABEL description="APPOT - Sistema de gestión de órdenes de trabajo"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FLASK_APP=app.py \
    FLASK_ENV=production \
    PATH="/root/.local/bin:$PATH" \
    TZ=America/Bogota

# Instalar utilidades del sistema solo si faltan
RUN (command -v curl && command -v psql && dpkg -s tzdata >/dev/null 2>&1) || \
    (apt-get update && apt-get install -y \
        libpq-dev \
        postgresql-client \
        curl \
        tzdata \
        && rm -rf /var/lib/apt/lists/*)

RUN ln -sf /usr/share/zoneinfo/America/Bogota /etc/localtime \
    && echo "America/Bogota" > /etc/timezone

WORKDIR /app
COPY . .

# Dar permisos ejecutables al entrypoint
RUN chmod +x ./entrypoint.sh

# Crear directorios necesarios
RUN mkdir -p static/uploads logs instance

EXPOSE 8000

HEALTHCHECK --interval=60s --timeout=15s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["sh", "-c", "sh ./entrypoint.sh gunicorn --bind 0.0.0.0:8000 --workers 4 --timeout 120 --keep-alive 5 --max-requests 1000 --preload app:app"]
