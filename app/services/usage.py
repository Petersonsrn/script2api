"""
app/services/usage.py — Centraliza lógica de rate-limit e uso mensal.

Evita duplicação entre routers (convert, auth, etc.).
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException

from app.core.config import settings
from app.db import count_uploads_this_month

FREE_LIMIT = settings.free_tier_monthly_limit


def monthly_limit(plan: str) -> int:
    """Retorna o limite mensal de conversões para o plano informado."""
    return FREE_LIMIT if plan == "free" else 999_999


def resets_on() -> str:
    """Retorna a data ISO (YYYY-MM-DD) em que o contador mensal reseta."""
    now = datetime.now(timezone.utc)
    if now.month == 12:
        return f"{now.year + 1}-01-01"
    return f"{now.year}-{now.month + 1:02d}-01"


async def check_rate_limit(user: dict) -> dict:
    """
    Verifica o limite mensal do usuário.

    Levanta HTTPException 429 se o usuário free excedeu o limite.
    Retorna dict de usage para incluir na response.
    """
    user_id = user.get("sub") or user.get("id", "anonymous")
    plan = user.get("plan", "free")
    limit = monthly_limit(plan)

    used = await count_uploads_this_month(user_id)
    remaining = max(0, limit - used)
    reset_date = resets_on()

    if plan == "free" and used >= limit:
        raise HTTPException(
            status_code=429,
            detail={
                "message": f"Limite mensal atingido ({used}/{limit}). Faca upgrade para Pro!",
                "plan": plan,
                "used": used,
                "limit": limit,
                "resets_on": reset_date,
            },
        )

    return {
        "user_id": user_id,
        "plan": plan,
        "used": used,
        "limit": limit if plan == "free" else None,
        "remaining": remaining if plan == "free" else None,
        "resets_on": reset_date,
    }


async def build_usage(user_id: str, plan: str) -> dict:
    """Retorna informações de uso mensal sem bloquear (uso em perfil, dashboards)."""
    used = await count_uploads_this_month(user_id)
    limit = monthly_limit(plan)
    return {
        "used": used,
        "limit": limit if plan == "free" else None,
        "remaining": max(0, limit - used) if plan == "free" else None,
        "plan": plan,
        "resets_on": resets_on(),
    }
