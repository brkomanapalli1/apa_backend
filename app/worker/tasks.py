"""
worker/tasks.py — Complete Celery task registry for APA.

Tasks:
  Phase 1:
    process_document_task       — OCR + AI analysis pipeline
    send_due_reminders_task     — daily deadline reminders
    send_email_task             — async email delivery

  Phase 2:
    scan_for_scams_task         — re-scan documents for scam patterns
    send_medication_reminders   — daily medication reminders
    send_sms_task               — async SMS via Twilio

  Phase 3:
    notify_caregivers_task      — alert caregivers on new documents
    renewal_check_task          — weekly renewal deadline scan

  Scheduled (Celery Beat):
    daily_reminders             — 8:00 AM daily
    weekly_renewal_check        — Monday 9:00 AM
    cleanup_expired_tokens      — midnight daily
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from app.celery_app import celery_app
from app.db.session import SessionLocal
from app.models.document import Document, DocumentStatus
from app.services.document_service import DocumentService

logger = logging.getLogger(__name__)


# ── Phase 1: Core Processing ──────────────────────────────────────────────

@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def process_document_task(self, document_id: int) -> dict:
    """OCR + AI analysis pipeline for uploaded documents."""
    db = SessionLocal()
    try:
        document = db.query(Document).filter(Document.id == document_id).first()
        if not document:
            return {"ok": False, "message": "Document not found"}

        service = DocumentService()
        service.process_document(db, document)
        logger.info("Document %d processed successfully", document_id)
        return {"ok": True, "document_id": document_id}

    except Exception as exc:
        db.rollback()
        document = db.query(Document).filter(Document.id == document_id).first()
        if document:
            document.status = DocumentStatus.FAILED
            document.processing_metadata = {
                **(document.processing_metadata or {}),
                "error": str(exc), "mode": "celery",
            }
            db.add(document); db.commit()
        logger.error("Document %d processing failed: %s", document_id, exc)
        try:
            raise self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            return {"ok": False, "error": str(exc)}
    finally:
        db.close()


@celery_app.task
def send_due_reminders_task() -> dict:
    """Send email/SMS reminders for due deadlines. Runs daily at 8 AM."""
    db = SessionLocal()
    try:
        from app.services.alert_service import AlertService
        from app.services.reminder_service import ReminderService

        reminders = ReminderService().get_due_reminders(db)
        alert_svc = AlertService()
        sent = 0

        for reminder in reminders:
            try:
                alert_svc.send_reminder_alert(db, reminder)
                sent += 1
            except Exception as e:
                logger.warning("Reminder %d failed: %s", reminder.id, e)

        logger.info("Sent %d reminders", sent)
        return {"ok": True, "sent": sent}
    finally:
        db.close()


@celery_app.task
def send_email_task(to: str, subject: str, html: str, text: str | None = None) -> dict:
    """Async email delivery."""
    from app.services.email_service import EmailService
    try:
        sent = EmailService().send_email(to=to, subject=subject, html=html, text=text)
        return {"ok": sent}
    except Exception as exc:
        logger.error("Email to %s failed: %s", to, exc)
        return {"ok": False, "error": str(exc)}


# ── Phase 2: Smart Assistant ───────────────────────────────────────────────

@celery_app.task
def send_sms_task(to: str, message: str) -> dict:
    """Async SMS delivery via Twilio."""
    from app.core.config import settings
    if not settings.TWILIO_ACCOUNT_SID:
        logger.warning("Twilio not configured — SMS not sent")
        return {"ok": False, "reason": "Twilio not configured"}
    try:
        from twilio.rest import Client
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        msg = client.messages.create(body=message, from_=settings.TWILIO_FROM_NUMBER, to=to)
        return {"ok": True, "sid": msg.sid}
    except Exception as exc:
        logger.error("SMS to %s failed: %s", to, exc)
        return {"ok": False, "error": str(exc)}


@celery_app.task
def send_medication_reminders_task() -> dict:
    """Send daily medication reminders. Runs at 7:30 AM, noon, 5:30 PM, 8:30 PM."""
    db = SessionLocal()
    try:
        from app.services.alert_service import AlertService
        from app.models.document import Document, DocumentType
        from app.models.user import User
        import json

        alert_svc = AlertService()
        sent = 0
        current_hour = datetime.now(timezone.utc).strftime("%H")

        # Find all documents with medications
        docs = db.query(Document).filter(
            Document.status == DocumentStatus.PROCESSED,
            Document.extracted_fields.isnot(None),
        ).all()

        for doc in docs:
            fields = doc.extracted_fields or {}
            medications = fields.get("medications", [])
            if not medications:
                continue

            owner = db.get(User, doc.owner_id)
            if not owner:
                continue

            for med in medications:
                reminder_times = med.get("reminder_times", [])
                for time_str in reminder_times:
                    # Check if current hour matches reminder hour
                    if time_str.startswith(current_hour):
                        try:
                            alert_svc.send_medication_reminder(
                                db=db,
                                user=owner,
                                medication_name=med.get("name", "medication"),
                                dosage=med.get("dosage"),
                                instruction=med.get("instructions", ""),
                                with_food=med.get("with_food"),
                            )
                            sent += 1
                        except Exception as e:
                            logger.warning("Med reminder failed for user %d: %s", owner.id, e)

        return {"ok": True, "sent": sent}
    finally:
        db.close()


@celery_app.task
def scan_for_scams_task(document_id: int) -> dict:
    """Re-scan a document for scam patterns after processing."""
    db = SessionLocal()
    try:
        doc = db.query(Document).filter(Document.id == document_id).first()
        if not doc or not doc.extracted_text:
            return {"ok": False, "reason": "No text to scan"}

        from app.services.scam_detection import analyze_for_scams
        result = analyze_for_scams(doc.extracted_text, doc.document_type.value if doc.document_type else "")

        # Store scam analysis in extracted_fields
        fields = dict(doc.extracted_fields or {})
        fields["scam_analysis"] = {
            "is_suspicious": result.is_suspicious,
            "confidence": result.confidence,
            "risk_level": result.risk_level,
            "warning_message": result.warning_message,
            "safe_message": result.safe_message,
            "recommended_actions": result.recommended_actions,
            "signals": [{"category": s.category, "description": s.description, "severity": s.severity} for s in result.signals],
        }
        doc.extracted_fields = fields
        db.add(doc); db.commit()

        # Alert user if suspicious
        if result.is_suspicious:
            from app.services.alert_service import AlertService
            from app.models.user import User
            owner = db.get(User, doc.owner_id)
            if owner:
                AlertService().send_scam_alert(db, owner, doc.name, result.risk_level, result.warning_message)

        return {"ok": True, "risk_level": result.risk_level}
    finally:
        db.close()


# ── Phase 3: Caregiver ─────────────────────────────────────────────────────

@celery_app.task
def notify_caregivers_task(document_id: int, event_type: str = "new_document") -> dict:
    """Notify all caregivers when a senior uploads or processes a document."""
    db = SessionLocal()
    try:
        from app.services.alert_service import AlertService
        from app.models.document import Document, Invitation
        from app.models.user import User

        doc = db.query(Document).filter(Document.id == document_id).first()
        if not doc:
            return {"ok": False}

        owner = db.get(User, doc.owner_id)
        if not owner:
            return {"ok": False}

        # Find all active caregivers
        caregivers = db.query(Invitation).filter(
            Invitation.inviter_id == owner.id,
            Invitation.accepted == True,
            Invitation.revoked == False,
        ).all()

        if not caregivers:
            return {"ok": True, "notified": 0}

        alert_svc = AlertService()
        notified = 0

        for cg in caregivers:
            try:
                alert_svc.send_caregiver_document_alert(
                    db=db,
                    caregiver_email=cg.invitee_email,
                    senior_name=owner.full_name or owner.email,
                    document_name=doc.name,
                    document_type=doc.document_type.value if doc.document_type else "unknown",
                    event_type=event_type,
                    has_deadlines=bool(doc.deadlines),
                    is_suspicious=bool((doc.extracted_fields or {}).get("scam_analysis", {}) and
                                      (doc.extracted_fields or {}).get("scam_analysis", {}).get("is_suspicious")),
                )
                notified += 1
            except Exception as e:
                logger.warning("Caregiver notification failed for %s: %s", cg.invitee_email, e)

        return {"ok": True, "notified": notified}
    finally:
        db.close()


@celery_app.task
def renewal_check_task() -> dict:
    """Weekly scan for upcoming renewal deadlines. Runs Monday 9 AM."""
    db = SessionLocal()
    try:
        from app.services.renewal_tracking import check_upcoming_renewals
        from app.services.alert_service import AlertService
        from app.models.user import User

        users = db.query(User).filter(User.is_active == True).all()
        alerts_sent = 0

        for user in users:
            try:
                renewals = check_upcoming_renewals(db, user.id)
                for renewal in renewals:
                    if renewal.get("days_until", 999) <= 30:
                        AlertService().send_renewal_reminder(db, user, renewal)
                        alerts_sent += 1
            except Exception as e:
                logger.warning("Renewal check failed for user %d: %s", user.id, e)

        return {"ok": True, "alerts_sent": alerts_sent}
    finally:
        db.close()


@celery_app.task
def cleanup_expired_tokens_task() -> dict:
    """Clean up expired refresh tokens. Runs at midnight."""
    db = SessionLocal()
    try:
        from app.models.user import RefreshToken
        cutoff = datetime.now(timezone.utc) - timedelta(days=1)
        deleted = db.query(RefreshToken).filter(
            RefreshToken.expires_at < cutoff
        ).delete()
        db.commit()
        return {"ok": True, "deleted": deleted}
    finally:
        db.close()


# ── Celery Beat Schedule ───────────────────────────────────────────────────

from celery.schedules import crontab

celery_app.conf.beat_schedule = {
    # Daily reminders at 8:00 AM
    "daily-reminders": {
        "task": "app.worker.tasks.send_due_reminders_task",
        "schedule": crontab(hour=8, minute=0),
    },
    # Medication reminders 4x daily
    "medication-reminders-morning": {
        "task": "app.worker.tasks.send_medication_reminders_task",
        "schedule": crontab(hour=7, minute=30),
    },
    "medication-reminders-noon": {
        "task": "app.worker.tasks.send_medication_reminders_task",
        "schedule": crontab(hour=12, minute=0),
    },
    "medication-reminders-evening": {
        "task": "app.worker.tasks.send_medication_reminders_task",
        "schedule": crontab(hour=17, minute=30),
    },
    "medication-reminders-bedtime": {
        "task": "app.worker.tasks.send_medication_reminders_task",
        "schedule": crontab(hour=20, minute=30),
    },
    # Weekly renewal check Monday 9 AM
    "weekly-renewal-check": {
        "task": "app.worker.tasks.renewal_check_task",
        "schedule": crontab(hour=9, minute=0, day_of_week=1),
    },
    # Midnight cleanup
    "cleanup-tokens": {
        "task": "app.worker.tasks.cleanup_expired_tokens_task",
        "schedule": crontab(hour=0, minute=0),
    },
}
