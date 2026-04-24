"""initial schema

Revision ID: 17565f04d583
Revises: 
Create Date: 2026-04-24 00:15:11.695983

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '17565f04d583'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Cria schema inicial (users, uploads, billing_subscriptions, webhook_events)."""
    op.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id                  TEXT PRIMARY KEY,
            email               TEXT UNIQUE NOT NULL,
            username            TEXT UNIQUE NOT NULL,
            password            TEXT NOT NULL,
            plan                TEXT NOT NULL DEFAULT 'free',
            created_at          TEXT NOT NULL,
            stripe_customer_id  TEXT
        );
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users (email);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_users_stripe ON users (stripe_customer_id);")

    op.execute("""
        CREATE TABLE IF NOT EXISTS uploads (
            id           TEXT PRIMARY KEY,
            user_id      TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            filename     TEXT NOT NULL,
            script_name  TEXT NOT NULL DEFAULT '',
            endpoints_n  INTEGER DEFAULT 0,
            status       TEXT NOT NULL DEFAULT 'success',
            error_msg    TEXT DEFAULT '',
            created_at   TEXT NOT NULL
        );
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_uploads_user_created ON uploads (user_id, created_at DESC);")

    op.execute("""
        CREATE TABLE IF NOT EXISTS billing_subscriptions (
            id                       TEXT PRIMARY KEY,
            user_id                  TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            stripe_subscription_id   TEXT UNIQUE NOT NULL,
            status                   TEXT NOT NULL DEFAULT 'active',
            current_period_end       TEXT,
            created_at               TEXT NOT NULL
        );
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_billing_user ON billing_subscriptions (user_id);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_billing_stripe_sub ON billing_subscriptions (stripe_subscription_id);")

    op.execute("""
        CREATE TABLE IF NOT EXISTS webhook_events (
            id           SERIAL PRIMARY KEY,
            event_id     TEXT UNIQUE NOT NULL,
            event_type   TEXT NOT NULL,
            payload      TEXT NOT NULL,
            processed    BOOLEAN NOT NULL DEFAULT FALSE,
            created_at   TEXT NOT NULL
        );
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_webhook_event_id ON webhook_events (event_id);")


def downgrade() -> None:
    """Remove schema inicial."""
    op.execute("DROP TABLE IF EXISTS webhook_events;")
    op.execute("DROP TABLE IF EXISTS billing_subscriptions;")
    op.execute("DROP TABLE IF EXISTS uploads;")
    op.execute("DROP TABLE IF EXISTS users;")
