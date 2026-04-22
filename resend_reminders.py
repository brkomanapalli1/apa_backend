from dotenv import load_dotenv
load_dotenv()

from app.db.session import SessionLocal
from app.models.document import Reminder
from app.models.user import User
from app.services.alert_service import AlertService

db = SessionLocal()
alert_svc = AlertService()
sent = 0

# Send ALL reminders regardless of status (for testing)
for r in db.query(Reminder).all():
    user = db.get(User, r.user_id)
    if not user:
        print(f"Skipping reminder {r.id} — no user found")
        continue
    print(f"\nSending '{r.title}' → {user.email} (due: {r.due_at})")
    results = alert_svc.send_reminder_alert(db, r)
    for res in results:
        print(f"  {res.channel}: {'OK' if res.success else 'FAILED — ' + str(res.error)}")
    sent += 1

db.close()
print(f"\nDone — sent {sent} reminders. Check your inbox.")