"""
app/services/auth.py — Hashing de senha, JWT e dependencies FastAPI.
"""

from datetime import datetime, timedelta, timezone
from typing import Annotated

import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt

from app.core.config import settings

# ─────────────────────────────────────────────
#  CONFIGURAÇÃO
# ─────────────────────────────────────────────

_oauth2 = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)

ANONYMOUS_USER = {
    "id": "anonymous",
    "email": "",
    "username": "anonymous",
    "plan": "free",
}


# ─────────────────────────────────────────────
#  SENHA
# ─────────────────────────────────────────────

def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


# ─────────────────────────────────────────────
#  JWT
# ─────────────────────────────────────────────

def create_access_token(user_id: str, email: str, username: str, plan: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=settings.jwt_expire_hours)
    payload = {
        "sub": user_id,
        "email": email,
        "username": username,
        "plan": plan,
        "exp": expire,
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict:
    """Decodifica e valida um JWT. Lanca HTTPException 401 se invalido."""
    try:
        return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token invalido ou expirado: {e}",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ─────────────────────────────────────────────
#  FASTAPI DEPENDENCIES
# ─────────────────────────────────────────────

async def get_current_user(token: Annotated[str | None, Depends(_oauth2)]) -> dict:
    """
    Dependency que exige Bearer token valido.
    Retorna payload do JWT como dict.
    """
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de autenticacao nao fornecido.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return decode_token(token)


async def get_current_user_optional(token: Annotated[str | None, Depends(_oauth2)]) -> dict:
    """
    Dependency que aceita token opcional.
    Se nao houver token valido, retorna usuario anonimo.
    """
    if not token:
        return ANONYMOUS_USER
    try:
        return decode_token(token)
    except HTTPException:
        return ANONYMOUS_USER
