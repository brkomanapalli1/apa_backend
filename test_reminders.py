from dotenv import load_dotenv
load_dotenv()

from app.db.session import SessionLocal
from app.worker.tasks import send_due_reminders_task

# First check how many reminders are in the database
db = SessionLocal()
from app.models.document import Reminder
reminders = db.query(Reminder).all()
print(f"Total reminders in database: {len(reminders)}")
for r in reminders:
    print(f"  - ID:{r.id} | {r.title} | due:{r.due_at} | status:{r.status}")
db.close()

# Now trigger the reminder task
print("\nRunning send_due_reminders_task...")
result = send_due_reminders_task()
print("Result:", result)