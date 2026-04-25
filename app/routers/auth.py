"""
app/routers/auth.py — Endpoints de autenticacao.

POST /auth/register  — cria conta
POST /auth/login     — retorna JWT
GET  /auth/me        — dados + uso do mes
GET  /auth/history   — historico de uploads
POST /auth/upgrade   — muda plano (demo)
"""

from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel, EmailStr, field_validator

from app.db import (
    create_user, get_user_by_email, get_user_by_id,
    get_user_history, set_user_plan, get_user_referrals_count,
    update_user_credits, get_user_by_referral_code, delete_user,
)
from app.core.config import settings
from app.services.auth import (
    hash_password, verify_password,
    create_access_token, get_current_user,
)
from app.services.usage import build_usage

router = APIRouter(prefix="/auth", tags=["auth"])


# ─────────────────────────────────────────────
#  SCHEMAS
# ─────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email: EmailStr
    username: str
    password: str
    referrer_code: str | None = None  # código de quem indicou

    @field_validator("username")
    @classmethod
    def username_valid(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 3 or len(v) > 30:
            raise ValueError("Username deve ter entre 3 e 30 caracteres")
        if not v.replace("_", "").replace("-", "").isalnum():
            raise ValueError("Username so pode conter letras, numeros, _ e -")
        return v

    @field_validator("password")
    @classmethod
    def password_valid(cls, v: str) -> str:
        if len(v) < 6:
            raise ValueError("Senha deve ter pelo menos 6 caracteres")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


class UpgradeRequest(BaseModel):
    plan: str  # "free" | "pro"


# ─────────────────────────────────────────────
#  ENDPOINTS
# ─────────────────────────────────────────────

@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Criar nova conta",
)
async def register(req: RegisterRequest):
    """Cadastra um novo usuario e retorna o access token imediatamente."""
    # Verificar duplicatas
    if await get_user_by_email(req.email):
        raise HTTPException(status_code=409, detail="E-mail ja cadastrado.")

    # Buscar referrer pelo código (primeiros 8 chars do UUID)
    referrer_id = None
    if req.referrer_code and settings.referral_enabled:
        referrer = await get_user_by_referral_code(req.referrer_code)
        if referrer:
            referrer_id = referrer.id

    hashed = hash_password(req.password)
    try:
        user = await create_user(req.email, req.username, hashed, referrer_id)
    except Exception as e:
        if "UNIQUE" in str(e):
            raise HTTPException(status_code=409, detail="Username ja em uso.")
        raise HTTPException(status_code=500, detail="Erro ao criar conta.")
    
    # Se veio de referral, adicionar bônus ao referrer
    if user.referrer_id and settings.referral_enabled:
        await update_user_credits(user.referrer_id, settings.referral_bonus_credits)

    token = create_access_token(user.id, user.email, user.username, user.plan)
    return TokenResponse(
        access_token=token,
        user={
            "id": user.id, 
            "email": user.email, 
            "username": user.username, 
            "plan": user.plan,
            "credits": user.credits,
            "referral_bonus": settings.referral_signup_credits if user.referrer_id else 0,
        },
    )


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Login e obtencao de token",
)
async def login(req: LoginRequest):
    """Autentica com e-mail + senha e retorna JWT Bearer token."""
    user = await get_user_by_email(req.email)
    if not user or not verify_password(req.password, user.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="E-mail ou senha incorretos.",
        )
    token = create_access_token(user.id, user.email, user.username, user.plan)
    return TokenResponse(
        access_token=token,
        user={"id": user.id, "email": user.email, "username": user.username, "plan": user.plan},
    )


@router.get(
    "/me",
    summary="Dados do usuario autenticado + uso do mes",
)
async def me(current: dict = Depends(get_current_user)):
    """Retorna dados do usuario e contador de uso mensal."""
    user = await get_user_by_id(current["sub"])
    if not user:
        raise HTTPException(status_code=404, detail="Usuario nao encontrado.")

    usage = await build_usage(user.id, user.plan)
    return {
        "id": user.id,
        "email": user.email,
        "username": user.username,
        "plan": user.plan,
        "member_since": user.created_at,
        "usage": usage,
    }


@router.get(
    "/history",
    summary="Historico de uploads do usuario autenticado",
)
async def history(limit: int = 20, offset: int = 0, current: dict = Depends(get_current_user)):
    """Retorna as ultimas N conversoes do usuario com paginacao."""
    records = await get_user_history(current["sub"], limit=min(limit, 50), offset=max(offset, 0))
    return {
        "total": len(records),
        "limit": limit,
        "offset": offset,
        "items": [
            {
                "id": r.id,
                "filename": r.filename,
                "script_name": r.script_name,
                "endpoints": r.endpoints_n,
                "status": r.status,
                "error": r.error_msg,
                "created_at": r.created_at,
            }
            for r in records
        ],
    }


@router.post(
    "/upgrade",
    summary="Alterar plano do usuario (demo)",
)
async def upgrade(req: UpgradeRequest, current: dict = Depends(get_current_user)):
    """Muda o plano do usuario para 'free' ou 'pro' (endpoint de demonstracao)."""
    if req.plan not in ("free", "pro"):
        raise HTTPException(status_code=422, detail="Plano invalido. Use 'free' ou 'pro'.")
    await set_user_plan(current["sub"], req.plan)
    return {"message": f"Plano alterado para '{req.plan}' com sucesso."}


@router.delete(
    "/me",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Excluir conta e todos os dados",
)
async def delete_me(current: dict = Depends(get_current_user)):
    """Exclui o usuario autenticado e todo o historico (LGPD/GDPR).

    Uploads, assinaturas e dados de billing sao removidos via CASCADE.
    """
    user_id = current["sub"]
    user = await get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuario nao encontrado.")

    await delete_user(user_id)
    return None


@router.get("/referrals", summary="Dados do programa de indicação")
async def get_referrals(current: dict = Depends(get_current_user)):
    """Retorna código de referral e contagem de indicações."""
    user_id = current["sub"]
    user = await get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuario nao encontrado.")
    
    count = await get_user_referrals_count(user_id)
    
    return {
        "enabled": settings.referral_enabled,
        "referral_code": user_id[:8],  # usar primeiros 8 chars do UUID como código
        "referral_url": f"{settings.frontend_url}/?ref={user_id[:8]}",
        "referrals_count": count,
        "bonus_per_referral": settings.referral_bonus_credits if settings.referral_enabled else 0,
        "credits": await get_user_credits(user_id),
    }


@router.post("/claim-referral", summary="Resgatar bônus de indicação")
async def claim_referral(code: str, current: dict = Depends(get_current_user)):
    """
    Aplica bônus de indicação quando um novo usuário usa código de referral.
    (Normalmente chamado automaticamente no registro)
    """
    if not settings.referral_enabled:
        raise HTTPException(status_code=400, detail="Programa de indicação desabilitado.")
    
    # Nota: O processamento real ocorre no registro
    # Este endpoint é para casos onde o referral foi perdido no signup
    return {"message": "Para usar um código de indicação, registre-se com o parâmetro referrer_code."}
