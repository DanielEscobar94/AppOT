"""add branch_id and created_at to Anticipo

Revision ID: 0001
Revises: 
Create Date: 2026-07-08 10:21:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # 1. Eliminar UniqueConstraint restrictivo (puede fallar si no existe, usamos IF EXISTS)
    op.execute('ALTER TABLE anticipo DROP CONSTRAINT IF EXISTS uq_anticipo_orden_monto_metodo_fecha')
    
    # 2. Crear índice nuevo (menos restrictivo)
    op.create_index('ix_anticipo_orden_fecha', 'anticipo', ['orden_id', 'fecha'])
    
    # 3. Agregar branch_id (nullable por compatibilidad con datos legacy) — solo si no existe
    op.execute('ALTER TABLE anticipo ADD COLUMN IF NOT EXISTS branch_id INTEGER REFERENCES branches(id)')
    
    # 4. Agregar created_at — solo si no existe
    op.execute('ALTER TABLE anticipo ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()')


def downgrade():
    op.drop_column('anticipo', 'created_at')
    op.drop_constraint('fk_anticipo_branch', 'anticipo', type_='foreignkey')
    op.drop_column('anticipo', 'branch_id')
    op.drop_index('ix_anticipo_orden_fecha', table_name='anticipo')
    op.create_unique_constraint(
        'uq_anticipo_orden_monto_metodo_fecha',
        'anticipo',
        ['orden_id', 'monto', 'metodo_pago', 'fecha']
    )
