"""add monetization fields

Revision ID: d3ee1472ca68
Revises: 17565f04d583
Create Date: 2026-04-24 22:22:48.958082

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd3ee1472ca68'
down_revision: Union[str, Sequence[str], None] = '17565f04d583'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Adiciona campos de monetização: credits e referrer_id."""
    # Adicionar coluna credits (INTEGER DEFAULT 0)
    op.execute("""
        ALTER TABLE users 
        ADD COLUMN IF NOT EXISTS credits INTEGER DEFAULT 0
    """)
    
    # Adicionar coluna referrer_id (TEXT, FK para users.id)
    op.execute("""
        ALTER TABLE users 
        ADD COLUMN IF NOT EXISTS referrer_id TEXT 
        REFERENCES users(id) ON DELETE SET NULL
    """)
    
    # Criar índice para referrer_id
    op.execute("CREATE INDEX IF NOT EXISTS idx_users_referrer ON users (referrer_id);")


def downgrade() -> None:
    """Remove campos de monetização."""
    op.execute("DROP INDEX IF EXISTS idx_users_referrer;")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS referrer_id;")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS credits;")
