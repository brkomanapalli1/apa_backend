from dotenv import load_dotenv
load_dotenv()

from datetime import datetime, timezone, timedelta
from app.db.session import SessionLocal
from app.models.document import Document, Reminder
from app.models.user import User
from app.services.alert_service import AlertService

db = SessionLocal()

# ── Step 1: Find the prescription document ────────────────────────────────
doc = db.query(Document).filter(
    Document.name.ilike("%prescription%")
).order_by(Document.id.desc()).first()

if not doc:
    print("No prescription document found")
    db.close()
    exit()

print(f"Document: {doc.name} (ID: {doc.id})")

# ── Step 2: Fix refill reminders — parse approximate dates ───────────────
now = datetime.now(timezone.utc)

refill_dates = {
    "Request Refill — metFORMIN HCl 750 MG":        now + timedelta(days=90),
    "Request Refill — Levothyroxine Sodium 75 MCG":  now + timedelta(days=90),
    "Replace FreeStyle Libre 3 Plus Sensor":         now + timedelta(days=14),
    "Request Refill — Cholecalciferol (Vitamin D)":  now + timedelta(days=7),
}

for r in db.query(Reminder).filter(Reminder.document_id == doc.id).all():
    if r.title in refill_dates:
        r.due_at = refill_dates[r.title]
        db.add(r)
        print(f"Fixed refill reminder: '{r.title}' → due {r.due_at.date()}")

db.commit()

# ── Step 3: Create daily dose reminders ──────────────────────────────────
MEDICATION_SCHEDULES = [
    {
        "name": "metFORMIN HCl 750 MG",
        "instructions": "Take 1 tablet by mouth twice daily with a meal",
        "times": ["08:00", "18:00"],  # morning meal + evening meal
        "doses": ["Morning dose with breakfast", "Evening dose with dinner"],
    },
    {
        "name": "Levothyroxine Sodium 75 MCG",
        "instructions": "1 tablet in the morning on an empty stomach",
        "times": ["07:00"],
        "doses": ["Morning dose — empty stomach, 30 min before eating"],
    },
    {
        "name": "FreeStyle Libre 3 Plus Sensor",
        "instructions": "Replace sensor every 14 days",
        "times": [],  # handled by refill reminder
        "doses": [],
    },
    {
        "name": "Cholecalciferol 25 MCG (Vitamin D)",
        "instructions": "1 capsule orally once daily",
        "times": ["09:00"],
        "doses": ["Daily dose with morning meal"],
    },
]

created = 0
for med in MEDICATION_SCHEDULES:
    for i, time_str in enumerate(med["times"]):
        dose_label = med["doses"][i] if i < len(med["doses"]) else med["instructions"]
        title = f"Take {med['name']}"

        # Check if already exists
        existing = db.query(Reminder).filter(
            Reminder.document_id == doc.id,
            Reminder.title == title,
            Reminder.payload["reminder_time"].astext == time_str
        ).first()

        if not existing:
            db.add(Reminder(
                user_id=doc.owner_id,
                document_id=doc.id,
                title=title,
                due_at=None,  # recurring — no fixed date
                payload={
                    "type": "medication",
                    "medication": med["name"],
                    "instructions": dose_label,
                    "reminder_time": time_str,
                    "recurring": "daily",
                }
            ))
            print(f"Created dose reminder: '{title}' at {time_str} — {dose_label}")
            created += 1

db.commit()
print(f"\nCreated {created} medication dose reminders")

# ── Step 4: Send test notifications for all reminders ────────────────────
print("\nSending all reminder notifications...")
alert_svc = AlertService()
user = db.get(User, doc.owner_id)
sent = 0

for r in db.query(Reminder).filter(Reminder.document_id == doc.id).all():
    results = alert_svc.send_reminder_alert(db, r)
    for res in results:
        status = "OK" if res.success else f"FAILED — {res.error}"
        print(f"  {r.title[:50]} | {res.channel}: {status}")
    sent += 1

db.close()
print(f"\nDone — sent {sent} notifications. Check your inbox.")