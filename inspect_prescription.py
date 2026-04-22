from dotenv import load_dotenv
load_dotenv()

from app.db.session import SessionLocal
from app.models.document import Document, Reminder
import json

db = SessionLocal()

# Find the prescription document
doc = db.query(Document).filter(
    Document.name.ilike("%prescription%")
).order_by(Document.id.desc()).first()

if not doc:
    print("No prescription document found")
    db.close()
    exit()

print(f"Document: {doc.name} (ID: {doc.id})")
print(f"Type: {doc.document_type}")
print(f"Status: {doc.status}")
print(f"\nDeadlines ({len(doc.deadlines or [])}):")
for d in (doc.deadlines or []):
    print(f"  - {d}")

fields = doc.extracted_fields or {}
print(f"\nMedications in extracted_fields:")
meds = fields.get("medications", [])
print(f"  Count: {len(meds)}")
for m in meds:
    print(f"  - {m}")

print(f"\nReminders for this document:")
reminders = db.query(Reminder).filter(Reminder.document_id == doc.id).all()
for r in reminders:
    print(f"  ID:{r.id} | {r.title} | due:{r.due_at} | status:{r.status}")
    print(f"    payload: {r.payload}")

db.close()