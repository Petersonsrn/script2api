"""
app/db.py — Camada de acesso ao PostgreSQL via asyncpg.

Tabelas:
  users   — contas cadastradas
  uploads — historico de cada conversao/execucao
"""

import uuid
import asyncpg
from datetime import datetime, timezone
from dataclasses import dataclass

from app.core.config import settings

DATABASE_URL = settings.database_url
_pool = None

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


# ─────────────────────────────────────────────
#  POOL
# ─────────────────────────────────────────────

async def init_pool() -> None:
    global _pool
    # Ignorar erro caso rodemos sem db_url nos testes, o asyncpg reclamara sozinho.
    _pool = await asyncpg.create_pool(DATABASE_URL)

async def close_pool() -> None:
    global _pool
    if _pool:
        await _pool.close()


# ─────────────────────────────────────────────
#  SCHEMA
# ─────────────────────────────────────────────

_CREATE_USERS = """
CREATE TABLE IF NOT EXISTS users (
    id         TEXT PRIMARY KEY,
    email      TEXT UNIQUE NOT NULL,
    username   TEXT UNIQUE NOT NULL,
    password   TEXT NOT NULL,
    plan       TEXT NOT NULL DEFAULT 'free',
    created_at TEXT NOT NULL,
    stripe_customer_id TEXT
);
"""

_CREATE_UPLOADS = """
CREATE TABLE IF NOT EXISTS uploads (
    id           TEXT PRIMARY KEY,
    user_id      TEXT NOT NULL REFERENCES users(id),
    filename     TEXT NOT NULL,
    script_name  TEXT NOT NULL DEFAULT '',
    endpoints_n  INTEGER DEFAULT 0,
    status       TEXT NOT NULL DEFAULT 'success',
    error_msg    TEXT DEFAULT '',
    created_at   TEXT NOT NULL
);
"""


# ─────────────────────────────────────────────
#  INIT
# ─────────────────────────────────────────────

async def init_db() -> None:
    """Cria as tabelas se nao existirem na nuvem."""
    async with _pool.acquire() as conn:
        await conn.execute(_CREATE_USERS)
        await conn.execute(_CREATE_UPLOADS)


# ─────────────────────────────────────────────
#  USERS
# ─────────────────────────────────────────────

def _row_to_user(row) -> User:
    return User(
        id=row['id'], email=row['email'], username=row['username'],
        password=row['password'], plan=row['plan'], created_at=row['created_at'],
        stripe_customer_id=row['stripe_customer_id'] if 'stripe_customer_id' in row else None
    )


async def create_user(email: str, username: str, hashed_password: str) -> User:
    user_id = str(uuid.uuid4())
    now = _now()
    async with _pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO users (id, email, username, password, plan, created_at) VALUES ($1,$2,$3,$4,$5,$6)",
            user_id, email.lower(), username, hashed_password, "free", now
        )
    return User(id=user_id, email=email.lower(), username=username,
                password=hashed_password, plan="free", created_at=now)


async def get_user_by_email(email: str) -> User | None:
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, email, username, password, plan, created_at, stripe_customer_id FROM users WHERE email = $1",
            email.lower()
        )
    return _row_to_user(row) if row else None


async def get_user_by_id(user_id: str) -> User | None:
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, email, username, password, plan, created_at, stripe_customer_id FROM users WHERE id = $1",
            user_id
        )
    return _row_to_user(row) if row else None


async def get_user_by_stripe_id(customer_id: str) -> User | None:
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, email, username, password, plan, created_at, stripe_customer_id FROM users WHERE stripe_customer_id = $1",
            customer_id
        )
    return _row_to_user(row) if row else None


async def set_user_plan(user_id: str, plan: str) -> None:
    async with _pool.acquire() as conn:
        await conn.execute("UPDATE users SET plan = $1 WHERE id = $2", plan, user_id)


async def update_user_stripe_id(user_id: str, customer_id: str) -> None:
    async with _pool.acquire() as conn:
        await conn.execute("UPDATE users SET stripe_customer_id = $1 WHERE id = $2", customer_id, user_id)


# ─────────────────────────────────────────────
#  UPLOADS / HISTORY
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
    async with _pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO uploads
               (id, user_id, filename, script_name, endpoints_n, status, error_msg, created_at)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8)""",
            upload_id, user_id, filename, script_name, endpoints_n, status, error_msg, now
        )
    return Upload(
        id=upload_id, user_id=user_id, filename=filename,
        script_name=script_name, endpoints_n=endpoints_n,
        status=status, error_msg=error_msg, created_at=now,
    )


async def count_uploads_this_month(user_id: str) -> int:
    now = datetime.now(timezone.utc)
    month_start = f"{now.year}-{now.month:02d}-01"
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT COUNT(*) FROM uploads WHERE user_id = $1 AND created_at >= $2 AND status = 'success'",
            user_id, month_start
        )
    return row[0] if row else 0


async def get_user_history(user_id: str, limit: int = 20) -> list[Upload]:
    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT id, user_id, filename, script_name, endpoints_n, status, error_msg, created_at
               FROM uploads WHERE user_id = $1 ORDER BY created_at DESC LIMIT $2""",
            user_id, limit
        )
    return [
        Upload(id=r['id'], user_id=r['user_id'], filename=r['filename'], script_name=r['script_name'],
               endpoints_n=r['endpoints_n'], status=r['status'], error_msg=r['error_msg'], created_at=r['created_at'])
        for r in rows
    ]


# ─────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
