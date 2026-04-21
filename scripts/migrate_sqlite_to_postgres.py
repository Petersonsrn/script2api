"""
scripts/migrate_sqlite_to_postgres.py — Exporta dados do SQLite local para Supabase Postgres.

Uso:
    # Ativar venv e setar variáveis:
    set DATABASE_URL=postgresql://...supabase...
    python scripts/migrate_sqlite_to_postgres.py

O script:
  1. Lê o sqlite local (script2api.db)
  2. Conecta ao PostgreSQL via asyncpg
  3. Insere usuários e uploads em ordem (respeita FK)
  4. Ignora conflitos (ON CONFLICT DO NOTHING) — seguro de reexecutar
"""
from __future__ import annotations

import asyncio
import os
import sqlite3
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import asyncpg
from dotenv import load_dotenv

load_dotenv()

SQLITE_PATH = os.getenv("SQLITE_PATH", "script2api.db")
DATABASE_URL = os.environ["DATABASE_URL"]


async def migrate():
    print(f"📂 Lendo SQLite: {SQLITE_PATH}")
    conn_sqlite = sqlite3.connect(SQLITE_PATH)
    conn_sqlite.row_factory = sqlite3.Row
    cur = conn_sqlite.cursor()

    print("📡 Conectando ao PostgreSQL…")
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=3)

    # ── Usuários ──────────────────────────────────────────────────────────────
    cur.execute("SELECT id, email, username, password, plan, created_at, stripe_customer_id FROM users")
    users = cur.fetchall()
    print(f"👥 {len(users)} usuários encontrados no SQLite.")

    async with pool.acquire() as pg:
        for u in users:
            await pg.execute(
                """
                INSERT INTO users (id, email, username, password, plan, created_at, stripe_customer_id)
                VALUES ($1,$2,$3,$4,$5,$6,$7)
                ON CONFLICT (id) DO NOTHING
                """,
                u["id"], u["email"], u["username"], u["password"],
                u["plan"] or "free", u["created_at"], u["stripe_customer_id"],
            )
        print(f"✅ Usuários migrados.")

        # ── Uploads ───────────────────────────────────────────────────────────
        cur.execute("SELECT id, user_id, filename, script_name, endpoints_n, status, error_msg, created_at FROM uploads")
        uploads = cur.fetchall()
        print(f"📤 {len(uploads)} uploads encontrados no SQLite.")

        for up in uploads:
            await pg.execute(
                """
                INSERT INTO uploads (id, user_id, filename, script_name, endpoints_n, status, error_msg, created_at)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
                ON CONFLICT (id) DO NOTHING
                """,
                up["id"], up["user_id"], up["filename"], up["script_name"] or "",
                up["endpoints_n"] or 0, up["status"] or "success",
                up["error_msg"] or "", up["created_at"],
            )
        print("✅ Uploads migrados.")

    conn_sqlite.close()
    await pool.close()
    print("\n🎉 Migração completa! Verifique os dados no painel do Supabase.")


if __name__ == "__main__":
    asyncio.run(migrate())
