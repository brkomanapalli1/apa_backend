from __future__ import annotations

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.core.config import settings


class OAuthStateService:
    def __init__(self) -> None:
        self.serializer = URLSafeTimedSerializer(settings.SECRET_KEY, salt='google-oauth-state')

    def create(self, *, provider: str, return_to: str | None = None) -> str:
        return self.serializer.dumps({'provider': provider, 'return_to': return_to or settings.FRONTEND_URL})

    def verify(self, token: str) -> dict:
        try:
            return self.serializer.loads(token, max_age=settings.OAUTH_STATE_MAX_AGE_SECONDS)
        except SignatureExpired as exc:
            raise ValueError('OAuth state expired') from exc
        except BadSignature as exc:
            raise ValueError('OAuth state is invalid') from exc
