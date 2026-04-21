"""
tests/test_auth.py — Testes de autenticação (registro, login, JWT, /me).

Usa httpx.AsyncClient + pytest-asyncio.
Banco de dados: não é necessário (usamos mock ou SQLite em memória via env).
"""
from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

# ------------------------------------------------------------------
# Patch do banco ANTES de importar a aplicação
# ------------------------------------------------------------------
import asyncpg
from unittest.mock import AsyncMock, MagicMock, patch
import app.db as db_module

# Usuário fake inicial
_fake_users: dict[str, dict] = {}


def _fake_user_obj(user_id, email, username, password, plan="free"):
    from app.db import User
    return User(id=user_id, email=email, username=username,
                password=password, plan=plan, created_at="2024-01-01T00:00:00+00:00")


@pytest.fixture(autouse=True)
def patch_db(monkeypatch):
    """Substitui as funções de banco por versões em memória."""
    _fake_users.clear()

    async def _create_user(email, username, hashed_password):
        user = _fake_user_obj("uid-001", email, username, hashed_password)
        _fake_users[email] = user
        return user

    async def _get_by_email(email):
        return _fake_users.get(email)

    async def _get_by_id(uid):
        for u in _fake_users.values():
            if u.id == uid:
                return u
        return None

    async def _count_uploads(*args, **kwargs):
        return 0

    async def _log_upload(*args, **kwargs):
        pass

    async def _init_pool():
        pass

    async def _init_db():
        pass

    async def _close_pool():
        pass

    monkeypatch.setattr(db_module, "create_user", _create_user)
    monkeypatch.setattr(db_module, "get_user_by_email", _get_by_email)
    monkeypatch.setattr(db_module, "get_user_by_id", _get_by_id)
    monkeypatch.setattr(db_module, "count_uploads_this_month", _count_uploads)
    monkeypatch.setattr(db_module, "log_upload", _log_upload)
    monkeypatch.setattr(db_module, "init_pool", _init_pool)
    monkeypatch.setattr(db_module, "init_db", _init_db)
    monkeypatch.setattr(db_module, "close_pool", _close_pool)


@pytest_asyncio.fixture
async def client():
    from main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


# ------------------------------------------------------------------
# Testes
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_register_success(client):
    res = await client.post("/auth/register", json={
        "email": "test@example.com",
        "username": "testuser",
        "password": "senha123",
    })
    assert res.status_code == 201
    body = res.json()
    assert "access_token" in body
    assert body["user"]["email"] == "test@example.com"
    assert body["user"]["plan"] == "free"


@pytest.mark.asyncio
async def test_register_duplicate_email(client):
    payload = {"email": "dup@example.com", "username": "user1", "password": "senha123"}
    await client.post("/auth/register", json=payload)
    res = await client.post("/auth/register", json={**payload, "username": "user2"})
    assert res.status_code == 409


@pytest.mark.asyncio
async def test_login_success(client):
    # Registra
    await client.post("/auth/register", json={
        "email": "login@example.com", "username": "loginuser", "password": "senha123"
    })
    # Loga
    res = await client.post("/auth/login", json={
        "email": "login@example.com", "password": "senha123"
    })
    assert res.status_code == 200
    assert "access_token" in res.json()


@pytest.mark.asyncio
async def test_login_wrong_password(client):
    await client.post("/auth/register", json={
        "email": "wp@example.com", "username": "wpuser", "password": "correta"
    })
    res = await client.post("/auth/login", json={
        "email": "wp@example.com", "password": "errada"
    })
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_me_requires_token(client):
    res = await client.get("/auth/me")
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_me_with_valid_token(client):
    reg = await client.post("/auth/register", json={
        "email": "me@example.com", "username": "meuser", "password": "senha123"
    })
    token = reg.json()["access_token"]
    res = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    assert res.json()["email"] == "me@example.com"


@pytest.mark.asyncio
async def test_health_endpoint(client):
    res = await client.get("/health")
    # Pode retornar 200 ou 503 dependendo do DB mock
    assert res.status_code in (200, 503)
    body = res.json()
    assert "status" in body
    assert "version" in body
