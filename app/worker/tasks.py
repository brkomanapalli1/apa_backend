from app.db.session import SessionLocal
from app.models.document import Document
from app.services.document_service import DocumentService
from app.services.email_service import EmailService
from app.services.reminder_service import ReminderService
from app.worker import celery_app


@celery_app.task(bind=True)
def process_document_task(self, document_id: int) -> dict:
    db = SessionLocal()
    try:
        document = db.query(Document).filter(Document.id == document_id).first()
        if not document:
            return {'ok': False, 'message': 'Document not found'}
        service = DocumentService()
        service.process_document(db, document)
        return {'ok': True, 'document_id': document_id}
    except Exception as exc:
        document = db.query(Document).filter(Document.id == document_id).first()
        if document:
          DocumentService().mark_failed(db, document, str(exc))
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
