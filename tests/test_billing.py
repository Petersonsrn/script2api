"""
tests/test_billing.py — Testes dos endpoints de billing (Stripe).

Mockamos a biblioteca stripe para evitar chamadas reais à API.
"""
from __future__ import annotations

import json
import pytest
import stripe
from unittest.mock import MagicMock, patch


@pytest.fixture
def mock_stripe():
    with patch("app.routers.billing.stripe") as m:
        # Preserva classes de exceção reais para que `except` no código funcione
        m.SignatureVerificationError = stripe.SignatureVerificationError
        yield m


@pytest.fixture
async def auth_client(client):
    """Retorna um cliente autenticado (com token JWT)."""
    res = await client.post("/auth/register", json={
        "email": "billing@example.com",
        "username": "billinguser",
        "password": "senha123",
    })
    token = res.json()["access_token"]
    client.headers["Authorization"] = f"Bearer {token}"
    return client


@pytest.mark.asyncio
async def test_create_checkout_session_requires_auth(client):
    res = await client.post("/billing/create-checkout-session")
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_create_checkout_session_success(mock_stripe, client):
    # Cria usuário e autentica
    reg = await client.post("/auth/register", json={
        "email": "checkout@example.com",
        "username": "chkuser",
        "password": "senha123",
    })
    token = reg.json()["access_token"]

    fake_session = MagicMock()
    fake_session.url = "https://checkout.stripe.com/fake"
    mock_stripe.checkout.Session.create.return_value = fake_session

    res = await client.post(
        "/billing/create-checkout-session",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    assert res.json()["url"] == "https://checkout.stripe.com/fake"


@pytest.mark.asyncio
async def test_create_checkout_session_already_pro(mock_stripe, client):
    reg = await client.post("/auth/register", json={
        "email": "pro@example.com",
        "username": "prouser",
        "password": "senha123",
    })
    token = reg.json()["access_token"]

    # Upgrade para pro via endpoint de demo
    await client.post(
        "/auth/upgrade",
        json={"plan": "pro"},
        headers={"Authorization": f"Bearer {token}"},
    )

    res = await client.post(
        "/billing/create-checkout-session",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 400
    assert "já possui" in res.json()["detail"]


@pytest.mark.asyncio
async def test_webhook_invalid_signature(mock_stripe, client):
    mock_stripe.Webhook.construct_event.side_effect = stripe.SignatureVerificationError(
        "fail", "body"
    )
    res = await client.post(
        "/billing/webhook",
        content=b"{}",
        headers={"stripe-signature": "bad"},
    )
    assert res.status_code == 400


@pytest.mark.asyncio
async def test_webhook_checkout_completed(mock_stripe, client):
    event = {
        "id": "evt_123",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "client_reference_id": "user-001",
                "customer": "cus_001",
                "subscription": "sub_001",
                "metadata": {"user_id": "user-001"},
            }
        },
    }
    mock_stripe.Webhook.construct_event.return_value = event

    res = await client.post(
        "/billing/webhook",
        content=json.dumps(event).encode(),
        headers={"stripe-signature": "good"},
    )
    assert res.status_code == 200
