"""
app/db.py — Camada de acesso ao PostgreSQL via asyncpg.

Tabelas gerenciadas:
  users                   — contas de usuário
  uploads                 — histórico de conversões/execuções
  billing_subscriptions   — assinaturas Stripe
  webhook_events          — log idempotente de webhooks

Notas de produção:
  - Todas as queries usam placeholders ($1, $2 ...) — imunes a SQL Injection.
  - Pool criado uma vez no startup e fechado no shutdown.
  - created_at = ISO 8601 UTC string (mantém retrocompatibilidade).
"""

from __future__ import annotations

import uuid
import asyncpg
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Any

from app.core.config import settings

DATABASE_URL = settings.database_url
_pool: asyncpg.Pool | None = None


# ─────────────────────────────────────────────
#  DATACLASSES
# ─────────────────────────────────────────────

@dataclass
class User:
    id: str
    email: str
    username: str
    password: str
    plan: str = "free"
    created_at: str = ""
    stripe_customer_id: str | None = None


@dataclass
class Upload:
    id: str
    user_id: str
    filename: str
    script_name: str
    endpoints_n: int
    status: str
    error_msg: str
    created_at: str


@dataclass
class BillingSubscription:
    id: str
    user_id: str
    stripe_subscription_id: str
    status: str
    current_period_end: str | None
    created_at: str


@dataclass
class WebhookEvent:
    id: int
    event_id: str
    event_type: str
    processed: bool
    created_at: str


# ─────────────────────────────────────────────
#  POOL
# ─────────────────────────────────────────────

async def init_pool() -> None:
    global _pool
    _pool = await asyncpg.create_pool(
        DATABASE_URL,
        min_size=2,
        max_size=10,
        command_timeout=30,
    )


async def close_pool() -> None:
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("Pool de banco de dados não inicializado. Chame init_pool() primeiro.")
    return _pool


# ─────────────────────────────────────────────
#  SCHEMA — DDL
# ─────────────────────────────────────────────

_CREATE_USERS = """
CREATE TABLE IF NOT EXISTS users (
    id                  TEXT PRIMARY KEY,
    email               TEXT UNIQUE NOT NULL,
    username            TEXT UNIQUE NOT NULL,
    password            TEXT NOT NULL,
    plan                TEXT NOT NULL DEFAULT 'free',
    created_at          TEXT NOT NULL,
    stripe_customer_id  TEXT
);
CREATE INDEX IF NOT EXISTS idx_users_email ON users (email);
CREATE INDEX IF NOT EXISTS idx_users_stripe ON users (stripe_customer_id);
"""

_CREATE_UPLOADS = """
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
CREATE INDEX IF NOT EXISTS idx_uploads_user_created ON uploads (user_id, created_at DESC);
"""

_CREATE_BILLING_SUBSCRIPTIONS = """
CREATE TABLE IF NOT EXISTS billing_subscriptions (
    id                       TEXT PRIMARY KEY,
    user_id                  TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    stripe_subscription_id   TEXT UNIQUE NOT NULL,
    status                   TEXT NOT NULL DEFAULT 'active',
    current_period_end       TEXT,
    created_at               TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_billing_user ON billing_subscriptions (user_id);
CREATE INDEX IF NOT EXISTS idx_billing_stripe_sub ON billing_subscriptions (stripe_subscription_id);
"""

_CREATE_WEBHOOK_EVENTS = """
CREATE TABLE IF NOT EXISTS webhook_events (
    id           SERIAL PRIMARY KEY,
    event_id     TEXT UNIQUE NOT NULL,
    event_type   TEXT NOT NULL,
    payload      TEXT NOT NULL,
    processed    BOOLEAN NOT NULL DEFAULT FALSE,
    created_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_webhook_event_id ON webhook_events (event_id);
"""


# ─────────────────────────────────────────────
#  INIT
# ─────────────────────────────────────────────

async def init_db() -> None:
    """Cria todas as tabelas caso não existam. Idempotente."""
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(_CREATE_USERS)
        await conn.execute(_CREATE_UPLOADS)
        await conn.execute(_CREATE_BILLING_SUBSCRIPTIONS)
        await conn.execute(_CREATE_WEBHOOK_EVENTS)


# ─────────────────────────────────────────────
#  USERS — CRUD
# ─────────────────────────────────────────────

def _row_to_user(row: asyncpg.Record) -> User:
    return User(
        id=row["id"],
        email=row["email"],
        username=row["username"],
        password=row["password"],
        plan=row["plan"],
        created_at=row["created_at"],
        stripe_customer_id=row.get("stripe_customer_id"),
    )


async def create_user(email: str, username: str, hashed_password: str) -> User:
    user_id = str(uuid.uuid4())
    now = _now()
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO users (id, email, username, password, plan, created_at) "
            "VALUES ($1,$2,$3,$4,$5,$6)",
            user_id, email.lower(), username, hashed_password, "free", now,
        )
    return User(id=user_id, email=email.lower(), username=username,
                password=hashed_password, plan="free", created_at=now)


async def get_user_by_email(email: str) -> User | None:
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, email, username, password, plan, created_at, stripe_customer_id "
            "FROM users WHERE email = $1",
            email.lower(),
        )
    return _row_to_user(row) if row else None


async def get_user_by_id(user_id: str) -> User | None:
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, email, username, password, plan, created_at, stripe_customer_id "
            "FROM users WHERE id = $1",
            user_id,
        )
    return _row_to_user(row) if row else None


async def get_user_by_stripe_id(customer_id: str) -> User | None:
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, email, username, password, plan, created_at, stripe_customer_id "
            "FROM users WHERE stripe_customer_id = $1",
            customer_id,
        )
    return _row_to_user(row) if row else None


async def set_user_plan(user_id: str, plan: str) -> None:
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET plan = $1 WHERE id = $2", plan, user_id)


async def update_user_stripe_id(user_id: str, customer_id: str) -> None:
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET stripe_customer_id = $1 WHERE id = $2",
            customer_id, user_id,
        )


# ─────────────────────────────────────────────
#  UPLOADS — CRUD
# ─────────────────────────────────────────────

async def log_upload(
    user_id: str,
    filename: str,
    script_name: str = "",
    endpoints_n: int = 0,
    status: str = "success",
    error_msg: str = "",
) -> Upload:
    upload_id = str(uuid.uuid4())
    now = _now()
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO uploads "
            "(id, user_id, filename, script_name, endpoints_n, status, error_msg, created_at) "
            "VALUES ($1,$2,$3,$4,$5,$6,$7,$8)",
            upload_id, user_id, filename, script_name, endpoints_n, status, error_msg, now,
        )
    return Upload(
        id=upload_id, user_id=user_id, filename=filename,
        script_name=script_name, endpoints_n=endpoints_n,
        status=status, error_msg=error_msg, created_at=now,
    )


async def count_uploads_this_month(user_id: str) -> int:
    now = datetime.now(timezone.utc)
    month_start = f"{now.year}-{now.month:02d}-01"
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT COUNT(*) FROM uploads "
            "WHERE user_id = $1 AND created_at >= $2 AND status = 'success'",
            user_id, month_start,
        )
    return row[0] if row else 0


async def get_user_history(user_id: str, limit: int = 20) -> list[Upload]:
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, user_id, filename, script_name, endpoints_n, status, error_msg, created_at "
            "FROM uploads WHERE user_id = $1 ORDER BY created_at DESC LIMIT $2",
            user_id, limit,
        )
    return [
        Upload(
            id=r["id"], user_id=r["user_id"], filename=r["filename"],
            script_name=r["script_name"], endpoints_n=r["endpoints_n"],
            status=r["status"], error_msg=r["error_msg"], created_at=r["created_at"],
        )
        for r in rows
    ]


# ─────────────────────────────────────────────
#  BILLING SUBSCRIPTIONS
# ─────────────────────────────────────────────

async def upsert_subscription(
    user_id: str,
    stripe_subscription_id: str,
    status: str,
    current_period_end: str | None = None,
) -> None:
    """Cria ou atualiza a assinatura Stripe do usuário."""
    pool = get_pool()
    async with pool.acquire() as conn:
        exists = await conn.fetchrow(
            "SELECT id FROM billing_subscriptions WHERE stripe_subscription_id = $1",
            stripe_subscription_id,
        )
        if exists:
            await conn.execute(
                "UPDATE billing_subscriptions "
                "SET status = $1, current_period_end = $2 "
                "WHERE stripe_subscription_id = $3",
                status, current_period_end, stripe_subscription_id,
            )
        else:
            sub_id = str(uuid.uuid4())
            await conn.execute(
                "INSERT INTO billing_subscriptions "
                "(id, user_id, stripe_subscription_id, status, current_period_end, created_at) "
                "VALUES ($1,$2,$3,$4,$5,$6)",
                sub_id, user_id, stripe_subscription_id, status, current_period_end, _now(),
            )


# ─────────────────────────────────────────────
#  WEBHOOK EVENTS — idempotência
# ─────────────────────────────────────────────

async def is_event_processed(event_id: str) -> bool:
    """Retorna True se o evento já foi processado (previne duplicatas)."""
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT processed FROM webhook_events WHERE event_id = $1",
            event_id,
        )
    return bool(row and row["processed"])


async def save_webhook_event(
    event_id: str,
    event_type: str,
    payload: str,
    processed: bool = False,
) -> None:
    """Salva o evento bruto para auditoria. Ignorado silenciosamente se duplicado."""
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO webhook_events (event_id, event_type, payload, processed, created_at) "
            "VALUES ($1,$2,$3,$4,$5) ON CONFLICT (event_id) DO NOTHING",
            event_id, event_type, payload, processed, _now(),
        )


async def mark_event_processed(event_id: str) -> None:
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE webhook_events SET processed = TRUE WHERE event_id = $1",
            event_id,
        )


# ─────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
