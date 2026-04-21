from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    app_name: str = "Script2API"
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    secret_key: str = "change-me"
    cors_origins: str = "http://localhost:3000,http://localhost:5500"
    free_tier_limit: int = 10
    openai_api_key: str = ""

    # Sandbox execution settings
    sandbox_timeout: float = 5.0
    sandbox_max_source_kb: int = 50

    # JWT auth
    jwt_secret_key: str = "change-me-jwt-secret-32-chars-min"
    jwt_algorithm: str = "HS256"
    jwt_expire_hours: int = 24

    # Database
    database_url: str = "postgresql://postgres:postgres@localhost:5432/script2api"

    # Usage limits
    free_tier_monthly_limit: int = 5   # conversions per calendar month

    # Stripe Monetization
    stripe_api_key: str = "sk_test_..."
    stripe_webhook_secret: str = "whsec_..."
    stripe_pro_price_id: str = "price_something_here"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",")]

settings = Settings()
