"""
app/core/config.py — Configuração centralizada via pydantic-settings.

Todas as variáveis de ambiente são carregadas do arquivo .env ou do ambiente do sistema.
Valores default são aceitáveis apenas para desenvolvimento local.
"""
from __future__ import annotations
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ── Core ─────────────────────────────────────────
    app_name: str = "Script2API"
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000

    # URLs públicas
    frontend_url: str = "http://localhost:3000"
    backend_url: str = "http://localhost:8000"

    # ── CORS ─────────────────────────────────────────
    # String separada por vírgula → convertida em lista via `cors_origins_list`
    cors_allowed_origins: str = "http://localhost:3000,http://localhost:5500,http://127.0.0.1:5500"

    # ── JWT ──────────────────────────────────────────
    jwt_secret_key: str = "CHANGE_THIS_IN_PRODUCTION_USE_SECRETS_TOKEN_HEX_32"
    jwt_algorithm: str = "HS256"
    jwt_expire_hours: int = 24

    # ── Banco de Dados ────────────────────────────────
    database_url: str = "postgresql://postgres:postgres@localhost:5432/script2api"

    # ── Stripe ───────────────────────────────────────
    stripe_api_key: str = "sk_test_..."
    stripe_publishable_key: str = "pk_test_..."
    stripe_webhook_secret: str = "whsec_..."
    stripe_pro_price_id: str = "price_..."

    # ── Limites e Sandbox ─────────────────────────────
    free_tier_monthly_limit: int = 5
    sandbox_timeout: float = 5.0
    sandbox_max_source_kb: int = 64

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Properties ───────────────────────────────────
    @property
    def origins_list(self) -> list[str]:
        """Lista de origens CORS (retrocompatibilidade)."""
        return [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


settings = Settings()

