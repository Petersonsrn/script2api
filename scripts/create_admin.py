"""
scripts/create_admin.py — Cria um usuário administrador no banco de dados.

Uso:
    python scripts/create_admin.py

Variáveis de ambiente necessárias (ou .env na raiz do projeto):
    DATABASE_URL
    JWT_SECRET_KEY
"""
from __future__ import annotations

import asyncio
import os
import sys

# Garante que o módulo raiz está no path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.db import init_pool, close_pool, create_user, get_user_by_email, set_user_plan
from app.services.auth import hash_password


ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@script2api.com")
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "CHANGE_ME_ON_FIRST_LOGIN")


async def main():
    print("📡 Conectando ao banco de dados…")
    await init_pool()

    existing = await get_user_by_email(ADMIN_EMAIL)
    if existing:
        print(f"⚠️  Usuário '{ADMIN_EMAIL}' já existe (id={existing.id}). Nenhuma ação necessária.")
        await close_pool()
        return

    hashed = hash_password(ADMIN_PASSWORD)
    user = await create_user(ADMIN_EMAIL, ADMIN_USERNAME, hashed)
    await set_user_plan(user.id, "pro")

    print(f"✅ Admin criado com sucesso!")
    print(f"   Email:    {ADMIN_EMAIL}")
    print(f"   Username: {ADMIN_USERNAME}")
    print(f"   Plano:    pro")
    print(f"   ID:       {user.id}")
    print("\n⚠️  TROQUE A SENHA IMEDIATAMENTE após o primeiro login!")

    await close_pool()


if __name__ == "__main__":
    asyncio.run(main())
