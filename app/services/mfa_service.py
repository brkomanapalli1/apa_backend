from __future__ import annotations

import pyotp

from app.core.config import settings
from app.models.user import User


class MFAService:
    def generate_secret(self) -> str:
        return pyotp.random_base32()

    def provisioning_uri(self, email: str, secret: str) -> str:
        totp = pyotp.TOTP(secret)
        return totp.provisioning_uri(name=email, issuer_name=settings.MFA_ISSUER_NAME)

    def verify(self, secret: str, otp: str) -> bool:
        return pyotp.TOTP(secret).verify(otp, valid_window=1)

    def require_mfa(self, user: User) -> bool:
        return bool(user.mfa_enabled and user.totp_secret)
