"""
tests/test_auth.py — Testes de autenticação (registro, login, JWT, /me).
"""
from __future__ import annotations

import pytest


# Fixtures compartilhadas vivem em tests/conftest.py

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
