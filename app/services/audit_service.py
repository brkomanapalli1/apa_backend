from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.document import AuditLog


class AuditService:
    def log(
        self,
        db: Session,
        *,
        action: str,
        user_id: int | None = None,
        entity_type: str | None = None,
        entity_id: str | None = None,
        detail: dict[str, Any] | str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        request_id: str | None = None,
    ) -> AuditLog:
        payload = detail if isinstance(detail, dict) else ({'message': detail} if detail else {})
        item = AuditLog(
            user_id=user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            detail=payload,
            ip_address=ip_address,
            user_agent=user_agent,
            request_id=request_id,
        )
        db.add(item)
        db.commit()
        db.refresh(item)
        return item
