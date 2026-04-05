from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.user import RefreshToken, User


class AuthService:
    def issue_refresh_token(self, db: Session, user: User, token_jti: str, expires_at) -> RefreshToken:
        record = RefreshToken(user_id=user.id, token_jti=token_jti, expires_at=expires_at)
        db.add(record)
        db.commit()
        db.refresh(record)
        return record

    def get_valid_refresh_token(self, db: Session, token_jti: str) -> RefreshToken | None:
        return db.query(RefreshToken).filter(RefreshToken.token_jti == token_jti, RefreshToken.is_revoked.is_(False)).first()

    def revoke_refresh_token(self, db: Session, token_jti: str) -> None:
        record = db.query(RefreshToken).filter(RefreshToken.token_jti == token_jti).first()
        if record:
            record.is_revoked = True
            db.add(record)
            db.commit()

    def revoke_all_for_user(self, db: Session, user_id: int) -> int:
        rows = db.query(RefreshToken).filter(RefreshToken.user_id == user_id, RefreshToken.is_revoked.is_(False)).all()
        for item in rows:
            item.is_revoked = True
            db.add(item)
        db.commit()
        return len(rows)
