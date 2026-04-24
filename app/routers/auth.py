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
    get_user_history, set_user_plan,
)
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

    hashed = hash_password(req.password)
    try:
        user = await create_user(req.email, req.username, hashed)
    except Exception as e:
        if "UNIQUE" in str(e):
            raise HTTPException(status_code=409, detail="Username ja em uso.")
        raise HTTPException(status_code=500, detail="Erro ao criar conta.")

    token = create_access_token(user.id, user.email, user.username, user.plan)
    return TokenResponse(
        access_token=token,
        user={"id": user.id, "email": user.email, "username": user.username, "plan": user.plan},
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
async def history(limit: int = 20, current: dict = Depends(get_current_user)):
    """Retorna as ultimas N conversoes do usuario (padrao 20)."""
    records = await get_user_history(current["sub"], limit=min(limit, 50))
    return {
        "total": len(records),
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
