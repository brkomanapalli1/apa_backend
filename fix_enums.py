from app.db.session import SessionLocal
from sqlalchemy import text

db = SessionLocal()

statements = [
    "ALTER TYPE document_status_enum ADD VALUE IF NOT EXISTS 'quarantined'",
    "ALTER TYPE document_status_enum ADD VALUE IF NOT EXISTS 'uploading'",
    "ALTER TYPE malware_scan_status_enum ADD VALUE IF NOT EXISTS 'skipped'",
    "ALTER TYPE workflow_state_enum ADD VALUE IF NOT EXISTS 'needs_review'",
    "ALTER TYPE workflow_state_enum ADD VALUE IF NOT EXISTS 'waiting_on_user'",
    "ALTER TYPE workflow_state_enum ADD VALUE IF NOT EXISTS 'resolved'",
]

for s in statements:
    try:
        db.execute(text(s))
        db.commit()
        print(f"OK: {s}")
    except Exception as e:
        db.rollback()
        print(f"SKIP: {e}")

db.close()
print("All done")