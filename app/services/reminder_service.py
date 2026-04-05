from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.document import Reminder


class ReminderService:
    def sync_from_deadlines(self, db: Session, user_id: int, document_id: int, deadlines: list[dict]) -> int:
        created = 0
        for item in deadlines or []:
            due_at = None
            raw_date = item.get('date')
            if raw_date:
                try:
                    due_at = datetime.fromisoformat(str(raw_date).replace('Z', '+00:00'))
                except ValueError:
                    due_at = None
            title = item.get('title') or 'Document reminder'
            existing = db.query(Reminder).filter(Reminder.user_id == user_id, Reminder.document_id == document_id, Reminder.title == title).first()
            payload = {'source': 'deadline_extraction', 'deadline': item}
            if existing:
                existing.due_at = due_at
                existing.payload = payload
                db.add(existing)
            else:
                db.add(Reminder(user_id=user_id, document_id=document_id, title=title, due_at=due_at, payload=payload))
                created += 1
        db.commit()
        return created

    def send_due_reminders(self, db: Session) -> int:
        now = datetime.now(timezone.utc)
        reminders = db.query(Reminder).filter(Reminder.status == 'scheduled', Reminder.due_at.isnot(None), Reminder.due_at <= now).all()
        count = 0
        for reminder in reminders:
            reminder.status = 'sent'
            reminder.sent_at = now
            db.add(reminder)
            count += 1
        db.commit()
        return count
