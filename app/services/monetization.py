"""
app/services/monetization.py — Sistema completo de monetização.

Features:
- Multi-tier: Free, Starter ($9), Pro ($29), Enterprise ($99)
- Pay-as-you-go: Créditos para execuções além do limite
- Referral system: Créditos por indicar amigos
- Add-ons: Timeout extra, priority queue
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException

from app.core.config import settings
from app.db import count_uploads_this_month, get_user_by_id, update_user_credits

# Tier configuration
TIER_CONFIG = {
    "free": {
        "limit": settings.free_tier_monthly_limit,
        "price": 0,
        "features": ["sandbox_5s", "basic_support"],
    },
    "starter": {
        "limit": settings.starter_tier_monthly_limit,
        "price": 9,
        "features": ["sandbox_10s", "email_support", "analytics_basic"],
    },
    "pro": {
        "limit": settings.pro_tier_monthly_limit,
        "price": 29,
        "features": ["sandbox_30s", "priority_queue", "analytics_advanced", "webhooks"],
    },
    "enterprise": {
        "limit": settings.enterprise_tier_monthly_limit,
        "price": 99,
        "features": ["sandbox_unlimited", "dedicated_support", "sla", "custom_domain", "api_keys"],
    },
}

PAYG_CREDITS_PACK = {
    "price": 5,  # $5
    "credits": 50,  # 50 execuções
}


def get_tier_limit(plan: str) -> int:
    """Retorna limite mensal do tier."""
    return TIER_CONFIG.get(plan, TIER_CONFIG["free"])["limit"]


def get_tier_features(plan: str) -> list[str]:
    """Retorna features disponíveis no tier."""
    return TIER_CONFIG.get(plan, TIER_CONFIG["free"])["features"]


def resets_on() -> str:
    """Data de reset do contador mensal."""
    now = datetime.now(timezone.utc)
    if now.month == 12:
        return f"{now.year + 1}-01-01"
    return f"{now.year}-{now.month + 1:02d}-01"


async def get_user_credits(user_id: str) -> int:
    """Busca créditos pay-as-you-go do usuário."""
    user = await get_user_by_id(user_id)
    if not user:
        return 0
    # Assumindo que User tem campo 'credits' ou similar
    return getattr(user, 'credits', 0) or 0


async def check_rate_limit_with_credits(user: dict, consume_credit: bool = False) -> dict:
    """
    Verifica limite mensal e créditos pay-as-you-go.
    
    Args:
        user: Dict com sub (user_id), plan, etc.
        consume_credit: Se True, consome 1 crédito se usar payg
    
    Returns:
        Dict com usage info
    
    Raises:
        HTTPException 429 se sem limite e sem créditos
    """
    user_id = user.get("sub") or user.get("id", "anonymous")
    plan = user.get("plan", "free")
    limit = get_tier_limit(plan)
    
    used = await count_uploads_this_month(user_id)
    remaining_monthly = max(0, limit - used)
    
    # Se ainda tem limite mensal
    if remaining_monthly > 0:
        return {
            "user_id": user_id,
            "plan": plan,
            "used": used,
            "limit": limit,
            "remaining_monthly": remaining_monthly,
            "credits_used": 0,
            "credits_remaining": await get_user_credits(user_id),
            "resets_on": resets_on(),
            "payg_available": False,
        }
    
    # Sem limite mensal - verificar créditos pay-as-you-go
    credits = await get_user_credits(user_id)
    
    if credits > 0:
        if consume_credit:
            await update_user_credits(user_id, -1)
            credits -= 1
        return {
            "user_id": user_id,
            "plan": plan,
            "used": used,
            "limit": limit,
            "remaining_monthly": 0,
            "credits_used": 1 if consume_credit else 0,
            "credits_remaining": credits,
            "resets_on": resets_on(),
            "payg_available": True,
        }
    
    # Sem limite e sem créditos
    raise HTTPException(
        status_code=429,
        detail={
            "message": f"Limite mensal atingido ({used}/{limit}). Compre créditos ou faça upgrade!",
            "plan": plan,
            "used": used,
            "limit": limit,
            "credits_remaining": 0,
            "resets_on": resets_on(),
            "upgrade_url": "/billing/create-checkout-session",
            "buy_credits_url": "/billing/buy-credits",
        },
    )


async def build_usage_with_credits(user_id: str, plan: str) -> dict:
    """Build usage info incluindo créditos payg."""
    used = await count_uploads_this_month(user_id)
    limit = get_tier_limit(plan)
    credits = await get_user_credits(user_id)
    
    return {
        "used": used,
        "limit": limit if plan != "enterprise" else None,
        "remaining_monthly": max(0, limit - used) if plan != "enterprise" else None,
        "plan": plan,
        "features": get_tier_features(plan),
        "credits": credits,
        "resets_on": resets_on(),
        "can_use_credits": credits > 0 and used >= limit,
    }


# Referral System
async def apply_referral_bonus(referrer_id: str, new_user_id: str) -> dict:
    """
    Aplica bônus de referral:
    - Quem indicou ganha referral_bonus_credits
    - Novo usuário ganha referral_signup_credits
    """
    if not settings.referral_enabled:
        return {"enabled": False}
    
    # Adicionar créditos ao referrer
    await update_user_credits(referrer_id, settings.referral_bonus_credits)
    
    # Adicionar créditos ao novo usuário
    await update_user_credits(new_user_id, settings.referral_signup_credits)
    
    return {
        "enabled": True,
        "referrer_bonus": settings.referral_bonus_credits,
        "new_user_bonus": settings.referral_signup_credits,
    }


def calculate_addon_price(addons: list[str]) -> int:
    """Calcula preço total dos add-ons."""
    prices = {
        "timeout_extra": 5,  # $5
        "priority_queue": 10,  # $10/mês
    }
    return sum(prices.get(a, 0) for a in addons)
