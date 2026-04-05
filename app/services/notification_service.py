from sqlalchemy.orm import Session

from app.models.document import Notification


class NotificationService:
    def create(self, db: Session, user_id: int, title: str, body: str, channel: str = 'in_app', payload: dict | None = None) -> Notification:
        item = Notification(user_id=user_id, title=title, body=body, channel=channel, payload=payload or {})
        db.add(item)
        db.commit()
        db.refresh(item)
        return item

    def send_push_if_available(self, user, title: str, body: str) -> bool:
        return bool(getattr(user, 'push_token', None))
