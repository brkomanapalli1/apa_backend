from datetime import datetime, timedelta, timezone
from uuid import uuid4

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from jose import jwt
from passlib.context import CryptContext

from app.core.config import settings

pwd_context = CryptContext(schemes=['bcrypt'], deprecated='auto')
ALGORITHM = 'HS256'


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def create_access_token(subject: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode = {'sub': subject, 'type': 'access', 'exp': expire}
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(subject: str, jti: str | None = None) -> tuple[str, str, datetime]:
    token_id = jti or str(uuid4())
    expire = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode = {'sub': subject, 'type': 'refresh', 'jti': token_id, 'exp': expire}
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM), token_id, expire


def decode_token(token: str) -> dict:
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])


class PasswordResetTokenService:
    def __init__(self) -> None:
        self.serializer = URLSafeTimedSerializer(settings.SECRET_KEY, salt='password-reset')

    def create(self, email: str) -> str:
        return self.serializer.dumps({'email': email})

    def verify(self, token: str) -> str:
        try:
            payload = self.serializer.loads(token, max_age=settings.PASSWORD_RESET_TOKEN_MAX_AGE_SECONDS)
        except SignatureExpired as exc:
            raise ValueError('Password reset token expired') from exc
        except BadSignature as exc:
            raise ValueError('Password reset token invalid') from exc
        email = payload.get('email')
        if not email:
            raise ValueError('Password reset token invalid')
        return email
