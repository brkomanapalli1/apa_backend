from __future__ import annotations
from typing import Literal
from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True, extra="ignore")

    APP_NAME: str = "AI Paperwork Assistant"
    API_V1_STR: str = "/api/v1"
    ENVIRONMENT: Literal["development", "staging", "production"] = "development"

    SECRET_KEY: str = "change-me-generate-with-openssl-rand-hex-64"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    PASSWORD_RESET_TOKEN_MAX_AGE_SECONDS: int = 3600
    RATE_LIMIT_REQUESTS: int = 60
    RATE_LIMIT_WINDOW_SECONDS: int = 60

    CORS_ORIGINS: list[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/paperwork"
    DATABASE_POOL_SIZE: int = 10
    DATABASE_MAX_OVERFLOW: int = 20
    DATABASE_POOL_TIMEOUT: int = 30

    REDIS_URL: str = "redis://localhost:6379/0"
    FRONTEND_URL: str = "http://localhost:3000"

    MINIO_INTERNAL_ENDPOINT: str = "http://127.0.0.1:9000"
    MINIO_PUBLIC_ENDPOINT: str = "http://127.0.0.1:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_BUCKET: str = "documents"
    MINIO_SECURE: bool = False
    PRESIGNED_UPLOAD_EXPIRE_SECONDS: int = 900
    PRESIGNED_DOWNLOAD_EXPIRE_SECONDS: int = 600
    MAX_UPLOAD_SIZE_BYTES: int = 50 * 1024 * 1024

    # AI — Claude primary, OpenAI fallback, mock default
    LLM_PROVIDER: Literal["anthropic", "openai", "mock"] = "mock"
    ANTHROPIC_API_KEY: str | None = None
    ANTHROPIC_MODEL: str = "claude-sonnet-4-20250514"
    OPENAI_API_KEY: str | None = None
    OPENAI_MODEL: str = "gpt-4.1-mini"
    OCR_ENABLED: bool = True
    OCR_MAX_PAGES: int = 20
    LLM_MAX_TOKENS: int = 2048
    LLM_TEMPERATURE: float = 0.1
    LLM_TIMEOUT_SECONDS: int = 60
    LLM_MAX_RETRIES: int = 3

    SMTP_HOST: str | None = None
    SMTP_PORT: int = 587
    SMTP_USER: str | None = None
    SMTP_PASSWORD: str | None = None
    SMTP_FROM: str = "no-reply@aipaperworkassistant.com"
    SMTP_FROM_NAME: str = "AI Paperwork Assistant"
    SMTP_STARTTLS: bool = True

    EXPO_ACCESS_TOKEN: str | None = None

    STRIPE_SECRET_KEY: str | None = None
    STRIPE_WEBHOOK_SECRET: str | None = None
    STRIPE_PRICE_ID: str | None = None

    CLAMAV_HOST: str = "clamav"
    CLAMAV_PORT: int = 3310
    MALWARE_SCANNING_ENABLED: bool = True

    MFA_ISSUER_NAME: str = "AI Paperwork Assistant"
    GOOGLE_CLIENT_ID: str | None = None
    GOOGLE_CLIENT_SECRET: str | None = None
    GOOGLE_REDIRECT_URI: str = "http://localhost:8000/api/v1/auth/sso/google/callback"
    GOOGLE_ALLOWED_DOMAIN: str | None = None
    OAUTH_STATE_MAX_AGE_SECONDS: int = 600

    DEFAULT_ADMIN_EMAIL: str = "admin@example.com"

    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: Literal["json", "text"] = "text"
    ENABLE_METRICS: bool = True
    SENTRY_DSN: str | None = None

    # [HIPAA] Audit log retention — min 6 years (2190 days), default 7 years
    AUDIT_LOG_RETENTION_DAYS: int = 2555

    FEATURE_FAMILY_DASHBOARD: bool = True
    FEATURE_BILL_ANALYZER: bool = True
    FEATURE_LETTER_GENERATOR: bool = True
    FEATURE_SMART_FORM_FILL: bool = True

    @field_validator("SECRET_KEY")
    @classmethod
    def secret_key_strength(cls, v: str) -> str:
        import os
        if os.environ.get("ENVIRONMENT") == "production" and len(v) < 32:
            raise ValueError("SECRET_KEY must be at least 32 chars in production")
        return v

    @model_validator(mode="after")
    def validate_llm(self) -> "Settings":
        import warnings
        if self.LLM_PROVIDER == "anthropic" and not self.ANTHROPIC_API_KEY:
            warnings.warn("LLM_PROVIDER=anthropic but ANTHROPIC_API_KEY not set — using mock")
        if self.LLM_PROVIDER == "openai" and not self.OPENAI_API_KEY:
            warnings.warn("LLM_PROVIDER=openai but OPENAI_API_KEY not set — using mock")
        return self

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

    @property
    def effective_llm_provider(self) -> str:
        if self.LLM_PROVIDER == "anthropic" and self.ANTHROPIC_API_KEY:
            return "anthropic"
        if self.LLM_PROVIDER == "openai" and self.OPENAI_API_KEY:
            return "openai"
        return "mock"


settings = Settings()
