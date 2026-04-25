"""
tests/conftest.py — Fixtures compartilhadas para todos os módulos de teste.

Patcheia o banco de dados (asyncpg pool) por mocks em memória,
permitindo rodar testes sem PostgreSQL.
"""
from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

import app.db as db_module
from app.core.config import settings

_fake_users: dict[str, dict] = {}
_fake_uploads: list[dict] = []


def _fake_user_obj(user_id, email, username, password, plan="free", credits=0, referrer_id=None):
    from app.db import User
    return User(
        id=user_id,
        email=email,
        username=username,
        password=password,
        plan=plan,
        created_at="2024-01-01T00:00:00+00:00",
        credits=credits,
        referrer_id=referrer_id,
    )


@pytest.fixture(autouse=True)
def patch_db(monkeypatch):
    """Substitui funções de banco por versões em memória."""
    _fake_users.clear()
    _fake_uploads.clear()

    async def _create_user(email, username, hashed_password, referrer_id=None):
        user = _fake_user_obj("uid-001", email, username, hashed_password, credits=0, referrer_id=referrer_id)
        if referrer_id and settings.referral_enabled:
            user.credits = settings.referral_signup_credits
        _fake_users[email] = user
        return user

    async def _get_by_email(email):
        return _fake_users.get(email)

    async def _get_by_id(uid):
        for u in _fake_users.values():
            if u.id == uid:
                return u
        return None

    async def _get_by_stripe_id(cid):
        for u in _fake_users.values():
            if getattr(u, "stripe_customer_id", None) == cid:
                return u
        return None

    async def _count_uploads(*args, **kwargs):
        return 0

    async def _log_upload(*args, **kwargs):
        _fake_uploads.append(kwargs)
        from app.db import Upload

        return Upload(
            id="up-001",
            user_id=kwargs.get("user_id", "anonymous"),
            filename=kwargs.get("filename", ""),
            script_name=kwargs.get("script_name", ""),
            endpoints_n=kwargs.get("endpoints_n", 0),
            status=kwargs.get("status", "success"),
            error_msg=kwargs.get("error_msg", ""),
            created_at="2024-01-01T00:00:00+00:00",
        )

    async def _get_history(user_id, limit=20, offset=0):
        return []

    async def _set_plan(user_id, plan):
        for u in _fake_users.values():
            if u.id == user_id:
                u.plan = plan

    async def _update_stripe_id(user_id, customer_id):
        for u in _fake_users.values():
            if u.id == user_id:
                u.stripe_customer_id = customer_id

    async def _upsert_subscription(*args, **kwargs):
        pass

    async def _delete_user(user_id):
        removed = False
        for email, u in list(_fake_users.items()):
            if u.id == user_id:
                del _fake_users[email]
                removed = True
        return removed

    async def _update_user_credits(user_id, delta):
        for u in _fake_users.values():
            if u.id == user_id:
                u.credits = (u.credits or 0) + delta
                return u.credits
        return 0

    async def _get_user_referrals_count(user_id):
        count = 0
        for u in _fake_users.values():
            if getattr(u, 'referrer_id', None) == user_id:
                count += 1
        return count

    async def _get_user_by_referral_code(code):
        for u in _fake_users.values():
            if u.id.lower().startswith(code.lower()):
                return u
        return None

    async def _is_event_processed(event_id):
        return False

    async def _save_webhook_event(*args, **kwargs):
        pass

    async def _mark_event_processed(*args, **kwargs):
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
    monkeypatch.setattr(db_module, "get_user_by_stripe_id", _get_by_stripe_id)
    monkeypatch.setattr(db_module, "count_uploads_this_month", _count_uploads)
    monkeypatch.setattr(db_module, "log_upload", _log_upload)
    monkeypatch.setattr(db_module, "get_user_history", _get_history)
    monkeypatch.setattr(db_module, "set_user_plan", _set_plan)
    monkeypatch.setattr(db_module, "update_user_stripe_id", _update_stripe_id)
    monkeypatch.setattr(db_module, "upsert_subscription", _upsert_subscription)
    monkeypatch.setattr(db_module, "is_event_processed", _is_event_processed)
    monkeypatch.setattr(db_module, "save_webhook_event", _save_webhook_event)
    monkeypatch.setattr(db_module, "mark_event_processed", _mark_event_processed)
    monkeypatch.setattr(db_module, "delete_user", _delete_user)
    monkeypatch.setattr(db_module, "update_user_credits", _update_user_credits)
    monkeypatch.setattr(db_module, "get_user_referrals_count", _get_user_referrals_count)
    monkeypatch.setattr(db_module, "get_user_by_referral_code", _get_user_by_referral_code)
    monkeypatch.setattr(db_module, "init_pool", _init_pool)
    monkeypatch.setattr(db_module, "init_db", _init_db)
    monkeypatch.setattr(db_module, "close_pool", _close_pool)


@pytest_asyncio.fixture
async def client():
    from main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
