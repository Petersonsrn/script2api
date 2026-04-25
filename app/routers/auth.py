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

# ─────────────────────────────────────────────
#  GITHUB OAUTH
# ─────────────────────────────────────────────

@router.get("/github/login", summary="Redireciona para o login do GitHub")
async def github_login():
    """Redireciona o usuário para a página de autorização do GitHub."""
    if not settings.github_client_id:
        raise HTTPException(status_code=500, detail="GitHub OAuth não configurado no servidor.")
    
    # URL de autorização do GitHub
    github_auth_url = (
        f"https://github.com/login/oauth/authorize"
        f"?client_id={settings.github_client_id}"
        f"&scope=user:email"
    )
    return {"url": github_auth_url}


@router.post("/github/callback", summary="Callback do GitHub OAuth", response_model=TokenResponse)
async def github_callback(code: str):
    """
    Recebe o código do GitHub, troca por um access_token,
    busca o e-mail/perfil do usuário e cria/autentica a conta.
    """
    if not settings.github_client_id or not settings.github_client_secret:
        raise HTTPException(status_code=500, detail="GitHub OAuth não configurado.")

    import httpx
    
    async with httpx.AsyncClient() as client:
        # 1. Trocar code por token
        token_response = await client.post(
            "https://github.com/login/oauth/access_token",
            data={
                "client_id": settings.github_client_id,
                "client_secret": settings.github_client_secret,
                "code": code,
            },
            headers={"Accept": "application/json"}
        )
        token_data = token_response.json()
        
        if "error" in token_data:
            raise HTTPException(status_code=400, detail=f"Erro do GitHub: {token_data.get('error_description', 'Desconhecido')}")
        
        access_token = token_data.get("access_token")
        if not access_token:
            raise HTTPException(status_code=400, detail="Token de acesso não retornado pelo GitHub.")

        # 2. Buscar perfil do usuário
        user_response = await client.get(
            "https://api.github.com/user",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/vnd.github.v3+json",
            }
        )
        if user_response.status_code != 200:
            raise HTTPException(status_code=400, detail="Erro ao buscar dados do GitHub.")
            
        github_user = user_response.json()
        
        # 3. Buscar e-mail do usuário (pode não vir no endpoint principal se for privado)
        email = github_user.get("email")
        if not email:
            emails_response = await client.get(
                "https://api.github.com/user/emails",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github.v3+json",
                }
            )
            if emails_response.status_code == 200:
                emails = emails_response.json()
                primary_email = next((e["email"] for e in emails if e.get("primary")), None)
                email = primary_email or (emails[0]["email"] if emails else None)
                
        if not email:
            raise HTTPException(status_code=400, detail="Não foi possível obter o e-mail do GitHub.")

        # 4. Criar ou buscar usuário local
        user = await get_user_by_email(email)
        if not user:
            # Criar nova conta
            # Cria um username baseado no github_login ou e-mail
            username = github_user.get("login") or email.split("@")[0]
            # Adiciona sufixo caso já exista (simples)
            import secrets
            # Senha dummy já que fará login pelo github
            dummy_password = hash_password(secrets.token_hex(16))
            try:
                user = await create_user(email, username, dummy_password, None)
            except Exception:
                # Username conflitante, tentar outro
                username = f"{username}_{secrets.token_hex(2)}"
                user = await create_user(email, username, dummy_password, None)

        # 5. Gerar JWT do app
        app_token = create_access_token(user.id, user.email, user.username, user.plan)
        
        return TokenResponse(
            access_token=app_token,
            user={
                "id": user.id, 
                "email": user.email, 
                "username": user.username, 
                "plan": user.plan,
                "credits": user.credits,
            },
        )
