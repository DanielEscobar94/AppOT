#!/bin/bash
set -e

# =============================================================================
# APPOT Production Entrypoint - Optimizado para Dokploy
# =============================================================================

# Verificar si las dependencias ya están instaladas (volumen persistente /root/.local)
# Si están, NO se vuelven a instalar (redeploys más rápidos).
echo "[APPOT] Checking Python dependencies..."
if python -c "import flask, flask_sqlalchemy, flask_login, flask_wtf, psycopg2, sqlalchemy, pandas, openpyxl, pytz, gunicorn" 2>/dev/null; then
    echo "[APPOT] Dependencies already installed - skipping install"
else
    echo "[APPOT] Installing dependencies..."
    pip install --user --no-cache-dir -r requirements.txt
    echo "[APPOT] Dependencies installed"
fi

# Esperar conexión a base de datos (usando psycopg2 directo para evitar cargar los modelos)
echo "[APPOT] Waiting for database..."
python -c "
import os, sys, time, psycopg2
url = os.environ['DATABASE_URL']
max_retries = 30
for i in range(max_retries):
    try:
        conn = psycopg2.connect(url)
        conn.close()
        sys.exit(0)
    except Exception as e:
        if i >= max_retries - 1:
            print(f'[ERROR] Database unavailable after {max_retries} retries: {e}', file=sys.stderr)
            sys.exit(1)
        time.sleep(1)
"

# 1. Crear todas las tablas si no existen (primer deploy)
# create_app() llama a init_default_admin() que falla (error capturado) si la tabla user no existe.
# Eso es esperado: el error se captura, create_all() crea todo, y el seed de abajo puebla los datos.
echo "[APPOT] Creating tables if needed..."
python -c "
from app import create_app
from extensions import db
app = create_app('production')
with app.app_context():
    db.create_all()
    print('[APPOT] All tables created (or already exist)')
"

# 2. Migrar esquema: agregar columnas faltantes
echo "[APPOT] Running schema migration..."
python -c "
import os, psycopg2
url = os.environ['DATABASE_URL']
conn = psycopg2.connect(url)
cur = conn.cursor()

# Verificar si anticipo existe
cur.execute(\"SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name='anticipo')\")
if cur.fetchone()[0]:
    cur.execute(\"SELECT column_name FROM information_schema.columns WHERE table_name='anticipo' AND column_name='branch_id'\")
    if cur.fetchone() is None:
        cur.execute('ALTER TABLE anticipo DROP CONSTRAINT IF EXISTS uq_anticipo_orden_monto_metodo_fecha')
        cur.execute('ALTER TABLE anticipo ADD COLUMN branch_id INTEGER REFERENCES branches(id)')
        cur.execute('ALTER TABLE anticipo ADD COLUMN created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()')
        cur.execute('CREATE INDEX IF NOT EXISTS ix_anticipo_orden_fecha ON anticipo (orden_id, fecha)')
        conn.commit()
        print('[APPOT] Columns branch_id and created_at added to anticipo table')
    else:
        print('[APPOT] Schema already up to date')

    # Stamped migration en alembic_version
    cur.execute(\"SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name='alembic_version')\")
    if cur.fetchone()[0]:
        cur.execute(\"SELECT version_num FROM alembic_version WHERE version_num='0001'\")
        if cur.fetchone() is None:
            cur.execute(\"INSERT INTO alembic_version (version_num) VALUES ('0001')\")
            conn.commit()
            print('[APPOT] Migration 0001 stamped in alembic_version')
else:
    print('[APPOT] anticipo table will be created by create_all above')
cur.close()
conn.close()
"

# Sembrar datos por defecto (sin cargar create_app para evitar conflictos de esquema)
echo "[APPOT] Seeding default data..."
python << 'EOF'
import sys, os
import psycopg2
from werkzeug.security import generate_password_hash

url = os.environ['DATABASE_URL']
conn = psycopg2.connect(url)
cur = conn.cursor()

try:
    # Crear usuario admin si no existe
    cur.execute("SELECT id FROM \"user\" WHERE email = 'admin@correo.com'")
    if cur.fetchone() is None:
        pw = generate_password_hash('%%S0p0rt3-741%%')
        cur.execute(
            "INSERT INTO \"user\" (email, username, rol, password_hash) VALUES (%s, %s, %s, %s)",
            ('admin@correo.com', 'admin', 'admin', pw)
        )
        print('[APPOT] Admin user created')
    else:
        print('[APPOT] Admin user already exists')

    # Crear categorías básicas de OT si no existen
    for cat in ['Reloj', 'Bateria', 'Articulo Electronico']:
        cur.execute("SELECT id FROM ot_category WHERE nombre = %s", (cat,))
        if cur.fetchone() is None:
            cur.execute("INSERT INTO ot_category (nombre, activo) VALUES (%s, TRUE)", (cat,))
            print(f'[APPOT] Category \"{cat}\" created')

    conn.commit()
except Exception as e:
    conn.rollback()
    print(f'[ERROR] Seeding failed: {e}', file=sys.stderr)
    sys.exit(1)
finally:
    cur.close()
    conn.close()
EOF

echo "[APPOT] Starting application..."
exec "$@"
