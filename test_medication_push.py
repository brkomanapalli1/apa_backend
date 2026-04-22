from dotenv import load_dotenv
load_dotenv()

from app.db.session import SessionLocal
from app.models.user import User
from app.models.document import Document
from app.services.alert_service import AlertService

db = SessionLocal()
alert_svc = AlertService()

# Get user
user = db.query(User).first()
print(f"User: {user.email}")
print(f"Push token: {user.push_token}")

if not user.push_token:
    print("ERROR: No push token — log in on mobile app first")
    db.close()
    exit()

# Get prescription document
doc = db.query(Document).filter(
    Document.name.ilike("%prescription%")
).order_by(Document.id.desc()).first()

if not doc:
    print("No prescription found")
    db.close()
    exit()

fields = doc.extracted_fields or {}
medications = fields.get("medications", [])
print(f"\nMedications found: {len(medications)}")

if not medications:
    print("No medications in document — re-upload the prescription first")
    db.close()
    exit()

# Send push notification for each medication
for med in medications:
    name = med.get("name", "medication")
    instructions = med.get("instructions", f"Take {name}")
    reminder_times = med.get("reminder_times", [])
    
    print(f"\nSending push for: {name}")
    print(f"  Instructions: {instructions}")
    print(f"  Reminder times: {reminder_times}")
    
    results = alert_svc.send_medication_reminder(
        db=db,
        user=user,
        medication_name=name,
        dosage=med.get("dosage"),
        instruction=instructions,
        with_food=med.get("with_food"),
    )
    
    for r in results:
        print(f"  {r.channel}: {'OK' if r.success else 'FAILED — ' + str(r.error)}")

db.close()
print("\nDone — check your phone for push notifications")