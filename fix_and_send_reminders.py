from dotenv import load_dotenv
load_dotenv()

from datetime import datetime, timezone
from app.db.session import SessionLocal
from app.models.document import Reminder
from app.services.reminder_service import ReminderService

db = SessionLocal()

# Fix existing reminders that have due_at=None by reading date from payload
fixed = 0
for r in db.query(Reminder).filter(Reminder.due_at == None).all():
    payload = r.payload or {}
    deadline = payload.get("deadline", {})
    raw_date = deadline.get("date")
    parsed = ReminderService._parse_date(raw_date)
    if parsed:
        r.due_at = parsed
        db.add(r)
        fixed += 1
        print(f"Fixed reminder {r.id}: '{r.title}' → due {parsed.date()}")
    else:
        print(f"Could not parse date for reminder {r.id}: '{r.title}' raw='{raw_date}'")

db.commit()
print(f"\nFixed {fixed} reminders")

# Show all reminders now
print("\nAll reminders:")
for r in db.query(Reminder).all():
    print(f"  ID:{r.id} | {r.title} | due:{r.due_at} | status:{r.status}")

# Force-send all reminders that are due (including future ones for testing)
print("\nForce-sending all scheduled reminders for testing...")
from app.services.alert_service import AlertService
from app.models.user import User

alert_svc = AlertService()
sent = 0
for r in db.query(Reminder).filter(Reminder.status == "scheduled").all():
    if r.due_at:
        user = db.get(User, r.user_id)
        if user:
            print(f"Sending reminder '{r.title}' to {user.email}...")
            results = alert_svc.send_reminder_alert(db, r)
            for res in results:
                print(f"  {res.channel}: {'OK' if res.success else 'FAILED - ' + str(res.error)}")
            r.status = "sent"
            db.add(r)
            sent += 1

db.commit()
db.close()
print(f"\nSent {sent} reminder emails")