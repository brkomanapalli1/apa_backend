from __future__ import annotations
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.models.document import Reminder


class ReminderService:
    @staticmethod
    def _parse_date(raw_date: str | None):
        """Parse date strings in any format Claude might return."""
        if not raw_date:
            return None
        raw = str(raw_date).strip()
        from datetime import timezone
        # Try formats in order of likelihood
        formats = [
            "%Y-%m-%d",           # 2026-04-30  (ISO — most common from Claude)
            "%m/%d/%Y",           # 04/30/2026
            "%B %d, %Y",          # April 30, 2026
            "%b %d, %Y",          # Apr 30, 2026
            "%m-%d-%Y",           # 04-30-2026
            "%d/%m/%Y",           # 30/04/2026
            "%Y/%m/%d",           # 2026/04/30
        ]
        for fmt in formats:
            try:
                from datetime import datetime as dt
                parsed = dt.strptime(raw, fmt)
                return parsed.replace(tzinfo=timezone.utc)
            except ValueError:
                continue
        # Last resort: fromisoformat
        try:
            from datetime import datetime as dt
            return dt.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None

    def sync_from_deadlines(self, db: Session, user_id: int, document_id: int, deadlines: list[dict]) -> int:
        """Create or update reminders from detected document deadlines."""
        created = 0
        for item in deadlines or []:
            raw_date = item.get("date")
            due_at = self._parse_date(raw_date)
            title = item.get("title") or "Document reminder"
            existing = db.query(Reminder).filter(
                Reminder.user_id == user_id,
                Reminder.document_id == document_id,
                Reminder.title == title,
            ).first()
            payload = {"source": "deadline_extraction", "deadline": item}
            if existing:
                existing.due_at = due_at
                existing.payload = payload
                db.add(existing)
            else:
                db.add(Reminder(
                    user_id=user_id, document_id=document_id,
                    title=title, due_at=due_at, payload=payload,
                ))
                created += 1
        db.commit()
        return created

    def get_due_reminders(self, db: Session) -> list[Reminder]:
        """Get all reminders that are scheduled and due now or overdue."""
        now = datetime.now(timezone.utc)
        return (
            db.query(Reminder)
            .filter(
                Reminder.status == "scheduled",
                Reminder.due_at.isnot(None),
                Reminder.due_at <= now,
            )
            .order_by(Reminder.due_at.asc())
            .all()
        )

    def send_due_reminders(self, db: Session) -> int:
        """Mark due reminders as sent. Returns count sent."""
        reminders = self.get_due_reminders(db)
        now = datetime.now(timezone.utc)
        for reminder in reminders:
            reminder.status = "sent"
            reminder.sent_at = now
            db.add(reminder)
        db.commit()
        return len(reminders)

    def create_reminder(self, db: Session, user_id: int, document_id: int | None,
                        title: str, due_at: datetime | None, notes: str | None = None) -> Reminder:
        """Manually create a reminder."""
        r = Reminder(
            user_id=user_id, document_id=document_id,
            title=title, due_at=due_at,
            payload={"notes": notes} if notes else {},
        )
        db.add(r); db.commit(); db.refresh(r)
        return r
