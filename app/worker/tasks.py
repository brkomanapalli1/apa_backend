from app.db.session import SessionLocal
from app.models.document import Document,DocumentStatus
from app.services.document_service import DocumentService
from app.services.email_service import EmailService
from app.services.reminder_service import ReminderService
from app.celery_app import celery_app


@celery_app.task(bind=True)
def process_document_task(self, document_id: int) -> dict:
    db = SessionLocal()
    try:
        document = db.query(Document).filter(Document.id == document_id).first()
        if not document:
            return {"ok": False, "message": "Document not found"}

        service = DocumentService()
        service.process_document(db, document)
        return {"ok": True, "document_id": document_id}

    except Exception as exc:
        db.rollback()
        document = db.query(Document).filter(Document.id == document_id).first()
        if document:
            document.status = DocumentStatus.FAILED
            document.processing_metadata = {
                **(document.processing_metadata or {}),
                "error": str(exc),
                "mode": "celery",
            }
            db.add(document)
            db.commit()
        raise

    finally:
        db.close()


@celery_app.task
def send_due_reminders_task() -> dict:
    db = SessionLocal()
    try:
        sent = ReminderService().send_due_reminders(db)
        return {'ok': True, 'sent': sent}
    finally:
        db.close()


@celery_app.task
def send_email_task(to: str, subject: str, html: str, text: str | None = None) -> dict:
    sent = EmailService().send_email(to=to, subject=subject, html=html, text=text)
    return {'ok': sent}


@celery_app.task
def ping():
    return 'pong'
