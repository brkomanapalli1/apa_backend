from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', case_sensitive=True, extra='ignore')

    APP_NAME: str = 'AI Paperwork Assistant'
    API_V1_STR: str = '/api/v1'
    SECRET_KEY: str = 'change-me'
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    PASSWORD_RESET_TOKEN_MAX_AGE_SECONDS: int = 3600

    DATABASE_URL: str
    REDIS_URL: str
    FRONTEND_URL: str = 'http://localhost:3000'

    MINIO_INTERNAL_ENDPOINT: str = "http://127.0.0.1:9000"
    MINIO_PUBLIC_ENDPOINT: str = "http://127.0.0.1:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_BUCKET: str = "documents"
    MINIO_SECURE: bool = False
    PRESIGNED_UPLOAD_EXPIRE_SECONDS: int = 900
    PRESIGNED_DOWNLOAD_EXPIRE_SECONDS: int = 600

    LLM_PROVIDER: str = 'mock'
    OPENAI_API_KEY: str | None = None
    OPENAI_MODEL: str = 'gpt-4.1-mini'
    OCR_ENABLED: bool = True

    SMTP_HOST: str | None = None
    SMTP_PORT: int = 587
    SMTP_USER: str | None = None
    SMTP_PASSWORD: str | None = None
    SMTP_FROM: str = 'no-reply@example.com'
    SMTP_STARTTLS: bool = True

    EXPO_ACCESS_TOKEN: str | None = None

    STRIPE_SECRET_KEY: str | None = None
    STRIPE_WEBHOOK_SECRET: str | None = None
    STRIPE_PRICE_ID: str | None = None

    CLAMAV_HOST: str = 'clamav'
    CLAMAV_PORT: int = 3310
    MALWARE_SCANNING_ENABLED: bool = True

    MFA_ISSUER_NAME: str = 'AI Paperwork Assistant'
    GOOGLE_CLIENT_ID: str | None = None
    GOOGLE_CLIENT_SECRET: str | None = None
    GOOGLE_REDIRECT_URI: str = 'http://localhost:8000/api/v1/auth/sso/google/callback'
    GOOGLE_ALLOWED_DOMAIN: str | None = None
    OAUTH_STATE_MAX_AGE_SECONDS: int = 600

    DEFAULT_ADMIN_EMAIL: str = 'admin@example.com'

    LOG_LEVEL: str = 'INFO'
    ENABLE_METRICS: bool = True


settings = Settings()
