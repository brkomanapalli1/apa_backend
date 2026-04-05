from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db
from app.models.document import Notification
from app.models.user import User

router = APIRouter()


@router.get('')
def list_notifications(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    items = db.query(Notification).filter(Notification.user_id == current_user.id).order_by(Notification.created_at.desc()).limit(100).all()
    return [{'id': n.id, 'title': n.title, 'body': n.body, 'channel': str(n.channel), 'is_read': n.is_read, 'payload': n.payload or {}, 'created_at': n.created_at} for n in items]


@router.post('/{notification_id}/read')
def mark_read(notification_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    item = db.query(Notification).filter(Notification.id == notification_id, Notification.user_id == current_user.id).first()
    if not item:
        raise HTTPException(status_code=404, detail='Notification not found')
    item.is_read = True
    item.read_at = datetime.now(timezone.utc)
    db.add(item)
    db.commit()
    return {'ok': True}
