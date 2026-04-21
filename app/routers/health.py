"""
app/routers/health.py — Endpoint de verificação de saúde e status.
"""
from __future__ import annotations

import asyncpg
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.db import get_pool

router = APIRouter(tags=["health"])


@router.get("/health", summary="Health check detalhado")
async def health():
    """Verifica a saúde da aplicação e a conectividade com o banco."""
    db_status = "ok"
    db_error = None

    try:
        pool = get_pool()
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
    except Exception as exc:
        db_status = "error"
        db_error = str(exc) if not settings.is_production else "connection failed"

    status_code = 200 if db_status == "ok" else 503

    return JSONResponse(
        status_code=status_code,
        content={
            "status": "ok" if db_status == "ok" else "degraded",
            "version": "1.2.0",
            "env": settings.app_env,
            "database": db_status,
            "db_error": db_error,
        },
    )
