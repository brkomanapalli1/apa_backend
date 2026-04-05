from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db
from app.models.document import Reminder
from app.models.user import User

router = APIRouter()


@router.get('')
def list_reminders(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    items = db.query(Reminder).filter(Reminder.user_id == current_user.id).order_by(Reminder.due_at.asc().nulls_last(), Reminder.created_at.desc()).all()
    return [{'id': r.id, 'title': r.title, 'document_id': r.document_id, 'due_at': r.due_at, 'status': str(r.status), 'payload': r.payload or {}, 'created_at': r.created_at} for r in items]
