"""
APA Configuration — All environment settings with validation.
Every feature from the 6-phase roadmap has a flag here.
"""
from __future__ import annotations
from typing import Literal
from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True, extra="ignore")

    MINIO_REGION: str = "us-east-1"
    # ── App ────────────────────────────────────────────────────────────────
    APP_NAME: str = "AI Paperwork Assistant"
    APP_VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    ENVIRONMENT: Literal["development", "staging", "production"] = "development"

    # ── Security ───────────────────────────────────────────────────────────
    SECRET_KEY: str = "change-me-generate-with-openssl-rand-hex-64"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    PASSWORD_RESET_TOKEN_MAX_AGE_SECONDS: int = 3600
    MAX_LOGIN_ATTEMPTS: int = 5
    LOCKOUT_DURATION_MINUTES: int = 15

    # ── Rate Limiting ──────────────────────────────────────────────────────
    RATE_LIMIT_REQUESTS_PER_MINUTE: int = 60
    RATE_LIMIT_AUTH_PER_MINUTE: int = 10
    RATE_LIMIT_UPLOAD_PER_MINUTE: int = 5
    RATE_LIMIT_AI_PER_MINUTE: int = 20

    # ── CORS ───────────────────────────────────────────────────────────────
    CORS_ORIGINS: list[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    # ── Database ───────────────────────────────────────────────────────────
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/paperwork_db"
    DATABASE_POOL_SIZE: int = 10
    DATABASE_MAX_OVERFLOW: int = 20
    DATABASE_POOL_TIMEOUT: int = 30
    DATABASE_POOL_RECYCLE: int = 3600

    # ── Redis ──────────────────────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"

    # ── Frontend ───────────────────────────────────────────────────────────
    FRONTEND_URL: str = "http://localhost:3000"

    # ── Storage (MinIO / S3) ───────────────────────────────────────────────
    MINIO_INTERNAL_ENDPOINT: str = "http://127.0.0.1:9000"
    MINIO_PUBLIC_ENDPOINT: str = "http://127.0.0.1:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_BUCKET: str = "documents"
    MINIO_SECURE: bool = False
    PRESIGNED_UPLOAD_EXPIRE_SECONDS: int = 900
    PRESIGNED_DOWNLOAD_EXPIRE_SECONDS: int = 600
    MAX_UPLOAD_SIZE_BYTES: int = 50 * 1024 * 1024  # 50 MB
    MAX_PAGES_PER_DOCUMENT: int = 50

    # ── AI / LLM ───────────────────────────────────────────────────────────
    LLM_PROVIDER: Literal["anthropic", "openai", "mock"] = "mock"

    # Anthropic Claude (primary — recommended)
    ANTHROPIC_API_KEY: str | None = None
    ANTHROPIC_MODEL: str = "claude-sonnet-4-20250514"

    # OpenAI (fallback)
    OPENAI_API_KEY: str | None = None
    OPENAI_MODEL: str = "gpt-4.1-mini"

    # LLM settings
    LLM_MAX_TOKENS: int = 4096
    LLM_TEMPERATURE: float = 0.1
    LLM_TIMEOUT_SECONDS: int = 60
    LLM_MAX_RETRIES: int = 3
    LLM_MAX_INPUT_CHARS: int = 12000

    # ── OCR ────────────────────────────────────────────────────────────────
    OCR_ENABLED: bool = True
    OCR_ENGINE: Literal["tesseract", "paddleocr", "textract"] = "tesseract"
    OCR_MAX_PAGES: int = 20
    OCR_LANGUAGE: str = "eng"
    AWS_TEXTRACT_REGION: str = "us-east-1"
    AWS_ACCESS_KEY_ID: str | None = None
    AWS_SECRET_ACCESS_KEY: str | None = None

    # ── Email ──────────────────────────────────────────────────────────────
    SMTP_HOST: str | None = None
    SMTP_PORT: int = 587
    SMTP_USER: str | None = None
    SMTP_PASSWORD: str | None = None
    SMTP_FROM: str = "no-reply@aipaperworkassistant.com"
    SMTP_FROM_NAME: str = "AI Paperwork Assistant"
    SMTP_STARTTLS: bool = True

    # ── Push Notifications (Expo) ──────────────────────────────────────────
    EXPO_ACCESS_TOKEN: str | None = None

    # ── SMS (Twilio) ───────────────────────────────────────────────────────
    TWILIO_ACCOUNT_SID: str | None = None
    TWILIO_AUTH_TOKEN: str | None = None
    TWILIO_FROM_NUMBER: str | None = None

    # ── Billing (Stripe) ───────────────────────────────────────────────────
    STRIPE_SECRET_KEY: str | None = None
    STRIPE_WEBHOOK_SECRET: str | None = None
    STRIPE_PRICE_ID_MONTHLY: str | None = None
    STRIPE_PRICE_ID_ANNUAL: str | None = None
    STRIPE_PRICE_ID_FAMILY: str | None = None

    # ── Malware Scanning (ClamAV) ──────────────────────────────────────────
    CLAMAV_HOST: str = "clamav"
    CLAMAV_PORT: int = 3310
    MALWARE_SCANNING_ENABLED: bool = True

    # ── Auth ───────────────────────────────────────────────────────────────
    MFA_ISSUER_NAME: str = "AI Paperwork Assistant"
    GOOGLE_CLIENT_ID: str | None = None
    GOOGLE_CLIENT_SECRET: str | None = None
    GOOGLE_REDIRECT_URI: str = "http://localhost:8000/api/v1/auth/sso/google/callback"
    OAUTH_STATE_MAX_AGE_SECONDS: int = 600

    # ── Voice (Phase 2) ────────────────────────────────────────────────────
    VOICE_ENABLED: bool = False
    WHISPER_API_KEY: str | None = None  # OpenAI Whisper for STT
    TTS_PROVIDER: Literal["openai", "azure", "disabled"] = "disabled"
    AZURE_SPEECH_KEY: str | None = None
    AZURE_SPEECH_REGION: str = "eastus"

    # ── Translation (Phase 2) ──────────────────────────────────────────────
    TRANSLATION_ENABLED: bool = False
    TRANSLATION_PROVIDER: Literal["google", "deepl", "openai", "disabled"] = "disabled"
    GOOGLE_TRANSLATE_API_KEY: str | None = None
    DEEPL_API_KEY: str | None = None
    SUPPORTED_LANGUAGES: list[str] = ["en", "es", "zh", "hi", "vi", "ko", "ar", "fr", "pt", "ru"]

    # ── Scam Detection (Phase 2) ───────────────────────────────────────────
    SCAM_DETECTION_ENABLED: bool = True
    SCAM_CONFIDENCE_THRESHOLD: float = 0.75

    # ── Medication Tracking (Phase 2) ──────────────────────────────────────
    MEDICATION_TRACKING_ENABLED: bool = True

    # ── Emergency Vault (Phase 3) ──────────────────────────────────────────
    EMERGENCY_VAULT_ENABLED: bool = True
    VAULT_ENCRYPTION_KEY: str | None = None  # Additional AES-256 key for vault docs

    # ── Admin ──────────────────────────────────────────────────────────────
    DEFAULT_ADMIN_EMAIL: str = "admin@example.com"
    DEFAULT_ADMIN_PASSWORD: str = "ChangeMe123!"

    # ── [HIPAA] Compliance ─────────────────────────────────────────────────
    AUDIT_LOG_RETENTION_DAYS: int = 2555       # 7 years (HIPAA min: 6)
    PHI_ENCRYPTION_AT_REST: bool = True
    HIPAA_MODE: bool = True                    # Enables all HIPAA safeguards
    DATA_RETENTION_MEDICAL_DAYS: int = 2555    # 7 years
    DATA_RETENTION_UTILITY_DAYS: int = 1095    # 3 years
    DATA_RETENTION_FINANCIAL_DAYS: int = 2555  # 7 years

    # ── Data Sanitization ─────────────────────────────────────────────────
    SANITIZE_INPUT: bool = True
    MAX_INPUT_LENGTH: int = 100000
    ALLOWED_HTML_TAGS: list[str] = []          # No HTML allowed in inputs

    # ── Observability ─────────────────────────────────────────────────────
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: Literal["json", "text"] = "text"
    ENABLE_METRICS: bool = True
    SENTRY_DSN: str | None = None
    SENTRY_TRACES_SAMPLE_RATE: float = 0.1

    # ── Feature Flags (phased rollout) ────────────────────────────────────
    # Phase 1
    FEATURE_DOCUMENT_UPLOAD: bool = True
    FEATURE_OCR: bool = True
    FEATURE_AI_SUMMARY: bool = True
    FEATURE_DEADLINE_DETECTION: bool = True
    FEATURE_DASHBOARD: bool = True

    # Phase 2
    FEATURE_BILL_TRACKING: bool = True
    FEATURE_SCAM_DETECTION: bool = True
    FEATURE_MEDICATION_TRACKING: bool = True
    FEATURE_VOICE: bool = False
    FEATURE_SMART_REMINDERS: bool = True

    # Phase 3
    FEATURE_CAREGIVER_PORTAL: bool = True
    FEATURE_EMERGENCY_VAULT: bool = True
    FEATURE_RENEWAL_TRACKING: bool = True

    # Phase 4
    FEATURE_FORM_FILLING: bool = False
    FEATURE_FINANCIAL_ANALYSIS: bool = False
    FEATURE_BENEFITS_NAVIGATOR: bool = False

    # Phase 5
    FEATURE_AUTO_CLASSIFICATION: bool = True
    FEATURE_TIMELINE: bool = False
    FEATURE_TRANSLATION: bool = False

    @field_validator("SECRET_KEY")
    @classmethod
    def validate_secret_key(cls, v: str) -> str:
        import os
        if os.environ.get("ENVIRONMENT") == "production":
            if len(v) < 64 or "change-me" in v.lower():
                raise ValueError("SECRET_KEY must be a strong random value in production (openssl rand -hex 64)")
        return v

    @model_validator(mode="after")
    def validate_llm_config(self) -> "Settings":
        import warnings
        if self.LLM_PROVIDER == "anthropic" and not self.ANTHROPIC_API_KEY:
            warnings.warn("LLM_PROVIDER=anthropic but ANTHROPIC_API_KEY not set — using mock mode")
        if self.LLM_PROVIDER == "openai" and not self.OPENAI_API_KEY:
            warnings.warn("LLM_PROVIDER=openai but OPENAI_API_KEY not set — using mock mode")
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

    @property
    def voice_available(self) -> bool:
        return self.FEATURE_VOICE and self.VOICE_ENABLED and bool(self.WHISPER_API_KEY)

    @property
    def translation_available(self) -> bool:
        return self.FEATURE_TRANSLATION and self.TRANSLATION_ENABLED and self.TRANSLATION_PROVIDER != "disabled"


settings = Settings()
