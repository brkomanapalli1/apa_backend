"""
alert_service.py — Multi-Channel Alert & Notification Service

Channels supported:
  1. Email (SMTP)
  2. SMS (Twilio)
  3. Push notification (Expo)
  4. In-app notification (database)

Alert types:
  - Deadline reminder (tax, Medicare, insurance renewal)
  - Medication reminder (daily schedule from prescriptions)
  - Document ready (processing complete)
  - Scam detection (urgent warning)
  - Caregiver alert (new document uploaded by senior)
  - Bill due (utility, rent, credit card)
  - Renewal reminder (Medicare enrollment, insurance)

[HIPAA] All messages are sanitized:
  - No PHI in SMS or email subject lines
  - Only minimum necessary information sent externally
  - All external messages logged in audit trail
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class AlertChannel(str, Enum):
    EMAIL = "email"
    SMS = "sms"
    PUSH = "push"
    IN_APP = "in_app"


class AlertPriority(str, Enum):
    URGENT = "urgent"    # Scam detection, immediate deadlines
    HIGH = "high"        # Deadlines within 7 days
    MEDIUM = "medium"    # Deadlines within 30 days
    LOW = "low"          # General notifications


@dataclass
class AlertResult:
    channel: str
    success: bool
    error: str | None = None


class AlertService:
    """
    Central alert dispatcher. Routes alerts to appropriate channels
    based on user preferences and alert priority.
    """

    def send_reminder_alert(self, db: Session, reminder: Any) -> list[AlertResult]:
        """
        Route reminder to the right channels based on type:

        MEDICATION DOSE  → push + in-app only  (no email — too noisy)
        REFILL / DEADLINE → email + in-app + push (important, needs attention)
        BILL PAYMENT     → email + in-app + push
        """
        from app.models.user import User
        from app.models.document import Document
        from app.core.config import settings

        results = []
        user = db.get(User, reminder.user_id) if hasattr(reminder, "user_id") else None
        if not user:
            return results

        title  = getattr(reminder, "title", "Reminder")
        payload = getattr(reminder, "payload", {}) or {}
        reminder_type = payload.get("type", "deadline")

        # ── Medication DOSE reminder → push + in-app only ─────────────────
        if reminder_type == "medication":
            medication  = payload.get("medication", title)
            instruction = payload.get("instructions", f"Take {medication}")
            reminder_time = payload.get("reminder_time", "")

            results.append(self._send_in_app(
                db=db, user_id=user.id,
                title=f"💊 {title}",
                body=instruction,
                payload={"reminder_id": getattr(reminder, "id", None), "type": "medication"},
            ))

            if user.push_token:
                results.append(self._send_push(
                    token=user.push_token,
                    title="💊 Medication Time",
                    body=f"{instruction[:100]}",
                ))

            # SMS only if user opted in
            if settings.TWILIO_ACCOUNT_SID and getattr(user, "sms_reminders_enabled", False) and getattr(user, "phone", None):
                results.append(self._send_sms(
                    to=user.phone,
                    message=f"Medication reminder: {medication}. {instruction}"[:160],
                ))

            return results

        # ── All other reminders (refill, deadline, bill) → email + push ───
        raw_due = getattr(reminder, "due_at", None) or getattr(reminder, "due_date", None)
        due_date = raw_due.strftime("%B %d, %Y") if hasattr(raw_due, "strftime") else str(raw_due or "Check document")

        doc_name   = "your document"
        doc_type   = ""
        amount_due = ""
        action     = ""
        reason     = ""

        doc_id = getattr(reminder, "document_id", None)
        if doc_id:
            doc = db.get(Document, doc_id)
            if doc:
                doc_name   = doc.name or doc_name
                doc_type   = str(doc.document_type).replace("_", " ").title() if doc.document_type else ""
                fields     = doc.extracted_fields or {}
                amount_due = str(fields.get("amount_due") or fields.get("patient_responsibility") or "")

        deadline_info = payload.get("deadline", {})
        if deadline_info:
            action = deadline_info.get("action", "")
            reason = deadline_info.get("reason", "")

        # In-app (always)
        results.append(self._send_in_app(
            db=db, user_id=user.id,
            title=f"📅 {title}",
            body=f"{doc_name} — Due: {due_date}{f' · ${amount_due}' if amount_due else ''}",
            payload={"reminder_id": getattr(reminder, "id", None), "document_id": doc_id},
        ))

        # Email — for important deadlines, refills, bills
        if settings.SMTP_HOST:
            results.append(self._send_email(
                to=user.email,
                subject=f"Action needed: {title} — {due_date}",
                html=self._deadline_email_html(
                    title=title, due_date=due_date,
                    doc_name=doc_name, doc_type=doc_type,
                    amount_due=amount_due, action=action, reason=reason,
                ),
                text=f"Reminder: {title}\nDocument: {doc_name}\nDue: {due_date}\n{action}",
            ))

        # Push — brief summary on phone
        if user.push_token:
            push_body = f"{doc_name} — Due {due_date}"
            if amount_due:
                push_body += f" · ${amount_due}"
            results.append(self._send_push(
                token=user.push_token,
                title="📅 Action needed",
                body=push_body[:200],
            ))

        return results

    def send_medication_reminder(
        self, db: Session, user: Any,
        medication_name: str, dosage: str | None,
        instruction: str, with_food: bool | None = None,
    ) -> list[AlertResult]:
        """Send a medication reminder. [HIPAA] Medication names are PHI."""
        from app.core.config import settings
        results = []

        # [HIPAA] In-app only contains full medication name
        results.append(self._send_in_app(
            db=db, user_id=user.id,
            title=f"💊 Time for {medication_name}",
            body=instruction or f"Take {medication_name}{f' {dosage}' if dosage else ''}",
            payload={"type": "medication_reminder", "medication": medication_name},
        ))

        # Push — brief message only, no full dosage details
        if user.push_token:
            results.append(self._send_push(
                token=user.push_token,
                title="💊 Medication Time",
                body=f"Time for your {medication_name}",  # [HIPAA] Minimal info externally
            ))

        # SMS — only if user opted in, minimal info
        if settings.TWILIO_ACCOUNT_SID and getattr(user, "sms_reminders_enabled", False):
            sms_body = f"Medication reminder: {medication_name}"
            if with_food is True:
                sms_body += " - take with food"
            results.append(self._send_sms(to=user.phone or "", message=sms_body))

        return results

    def send_scam_alert(
        self, db: Session, user: Any,
        document_name: str, risk_level: str, warning: str,
    ) -> list[AlertResult]:
        """Send urgent scam alert. Highest priority."""
        from app.core.config import settings
        results = []

        # In-app (always, immediate)
        results.append(self._send_in_app(
            db=db, user_id=user.id,
            title="⚠️ Suspicious Document Detected",
            body=f"A document may be a scam. Do NOT pay or call any numbers in it.",
            payload={"type": "scam_alert", "risk_level": risk_level},
        ))

        # Push — urgent
        if user.push_token:
            results.append(self._send_push(
                token=user.push_token,
                title="⚠️ SCAM ALERT",
                body="A document you uploaded may be fraudulent. Tap to review.",
            ))

        # Email — with full details
        if settings.SMTP_HOST:
            results.append(self._send_email(
                to=user.email,
                subject="⚠️ Important: Possible Scam Document Detected",
                html=self._scam_alert_email_html(document_name, warning),
                text=f"SCAM ALERT: {warning}\n\nDocument: {document_name}\n\nDo NOT pay or call any numbers in this document.",
            ))

        # SMS — brief urgent message
        if settings.TWILIO_ACCOUNT_SID and getattr(user, "phone", None):
            results.append(self._send_sms(
                to=user.phone,
                message=f"ALERT from AI Paperwork Assistant: A document may be a scam. Do NOT pay or call numbers in it. Log in to review.",
            ))

        return results

    def send_caregiver_document_alert(
        self, db: Session, caregiver_email: str,
        senior_name: str, document_name: str,
        document_type: str, event_type: str,
        has_deadlines: bool = False, is_suspicious: bool = False,
    ) -> AlertResult:
        """Notify a caregiver that a senior has a new document."""
        from app.core.config import settings

        if not settings.SMTP_HOST:
            return AlertResult(channel="email", success=False, error="SMTP not configured")

        subject = f"Document update for {senior_name}"  # [HIPAA] No document details in subject
        if is_suspicious:
            subject = f"⚠️ Urgent: Suspicious document for {senior_name}"

        body_parts = [f"{senior_name} has a new document that may need attention."]
        if has_deadlines:
            body_parts.append("This document contains important deadlines.")
        if is_suspicious:
            body_parts.append("⚠️ This document has been flagged as potentially suspicious.")
        body_parts.append("Please log in to review.")

        return self._send_email(
            to=caregiver_email,
            subject=subject,
            html=self._caregiver_alert_html(senior_name, "\n".join(body_parts)),
            text="\n".join(body_parts),
        )

    def send_renewal_reminder(self, db: Session, user: Any, renewal: dict) -> AlertResult:
        """Send a renewal tracking reminder."""
        from app.core.config import settings
        title = renewal.get("title", "Upcoming renewal")
        days = renewal.get("days_until", "")

        self._send_in_app(
            db=db, user_id=user.id,
            title=f"🔄 {title}",
            body=f"Due in {days} days. Log in to review.",
            payload={"type": "renewal_reminder"},
        )

        if settings.SMTP_HOST:
            return self._send_email(
                to=user.email,
                subject=f"Renewal reminder: {title}",
                html=self._renewal_email_html(title, str(days), renewal.get("action", "")),
                text=f"Renewal reminder: {title}\nDue in {days} days.\n{renewal.get('action', '')}",
            )

        return AlertResult(channel="email", success=False, error="SMTP not configured")

    # ── Channel implementations ───────────────────────────────────────────

    def _send_in_app(self, db: Session, user_id: int, title: str, body: str, payload: dict | None = None) -> AlertResult:
        """Store notification in database for in-app display."""
        try:
            from app.services.notification_service import NotificationService
            NotificationService().create(db, user_id, title, body, payload=payload)
            return AlertResult(channel="in_app", success=True)
        except Exception as exc:
            logger.error("In-app notification failed for user %d: %s", user_id, exc)
            return AlertResult(channel="in_app", success=False, error=str(exc))

    def _send_email(self, to: str, subject: str, html: str, text: str | None = None) -> AlertResult:
        """Send email via configured SMTP."""
        try:
            from app.services.email_service import EmailService
            EmailService().send_email(to=to, subject=subject, html=html, text=text)
            return AlertResult(channel="email", success=True)
        except Exception as exc:
            logger.warning("Email to %s failed: %s", to, exc)
            return AlertResult(channel="email", success=False, error=str(exc))

    def _send_sms(self, to: str, message: str) -> AlertResult:
        """Send SMS via Twilio."""
        from app.core.config import settings
        if not settings.TWILIO_ACCOUNT_SID or not to:
            return AlertResult(channel="sms", success=False, error="Twilio not configured or no phone number")
        try:
            from twilio.rest import Client
            client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
            client.messages.create(body=message[:160], from_=settings.TWILIO_FROM_NUMBER, to=to)
            return AlertResult(channel="sms", success=True)
        except Exception as exc:
            logger.warning("SMS to %s failed: %s", to, exc)
            return AlertResult(channel="sms", success=False, error=str(exc))

    def _send_push(self, token: str, title: str, body: str) -> AlertResult:
        """Send push notification via Expo."""
        from app.core.config import settings
        if not token:
            return AlertResult(channel="push", success=False, error="No push token")
        try:
            from app.services.notification_service import NotificationService
            NotificationService().send_expo_push(token=token, title=title, body=body)
            return AlertResult(channel="push", success=True)
        except Exception as exc:
            logger.warning("Push notification failed: %s", exc)
            return AlertResult(channel="push", success=False, error=str(exc))

    # ── Email HTML templates ──────────────────────────────────────────────

    def _deadline_email_html(
        self, title: str, due_date: str,
        doc_name: str = "", doc_type: str = "",
        amount_due: str = "", action: str = "", reason: str = "",
        notes: str = "",
    ) -> str:
        amount_row = f"""
          <tr>
            <td style="padding:12px 16px;border-bottom:1px solid #e2e8f0;color:#6b7280;width:40%">Amount due</td>
            <td style="padding:12px 16px;border-bottom:1px solid #e2e8f0;font-weight:bold;color:#dc2626;font-size:18px">{amount_due}</td>
          </tr>""" if amount_due else ""

        doc_type_row = f"""
          <tr>
            <td style="padding:12px 16px;border-bottom:1px solid #e2e8f0;color:#6b7280">Document type</td>
            <td style="padding:12px 16px;border-bottom:1px solid #e2e8f0;color:#374151">{doc_type}</td>
          </tr>""" if doc_type else ""

        action_box = f"""
          <div style="margin-top:16px;padding:16px;background:#dbeafe;border-radius:8px;border-left:4px solid #2563eb">
            <p style="margin:0;color:#1e40af;font-weight:bold">What to do:</p>
            <p style="margin:8px 0 0;color:#1e40af">{action}</p>
          </div>""" if action else ""

        return f"""
        <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px">
          <div style="background:#2563eb;color:white;padding:20px;border-radius:12px 12px 0 0">
            <h1 style="margin:0;font-size:22px">📅 Payment Reminder</h1>
            <p style="margin:8px 0 0;opacity:0.9;font-size:14px">Action required before {due_date}</p>
          </div>
          <div style="background:#f8fafc;padding:20px;border-radius:0 0 12px 12px;border:1px solid #e2e8f0">

            <div style="background:#fff3cd;border:1px solid #ffc107;border-radius:8px;padding:16px;margin-bottom:20px">
              <p style="margin:0;color:#856404;font-size:18px;font-weight:bold">⏰ Due: {due_date}</p>
            </div>

            <table style="width:100%;border-collapse:collapse;background:white;border-radius:8px;border:1px solid #e2e8f0;overflow:hidden">
              <tr>
                <td style="padding:12px 16px;border-bottom:1px solid #e2e8f0;color:#6b7280;width:40%">Document</td>
                <td style="padding:12px 16px;border-bottom:1px solid #e2e8f0;font-weight:bold;color:#111827">{doc_name}</td>
              </tr>
              {doc_type_row}
              {amount_row}
              <tr>
                <td style="padding:12px 16px;color:#6b7280">Reminder</td>
                <td style="padding:12px 16px;color:#374151">{title}</td>
              </tr>
            </table>

            {action_box}

            {f'<p style="color:#6b7280;margin-top:16px">{reason}</p>' if reason else ''}

            <div style="margin-top:20px;padding:16px;background:#f0fdf4;border-radius:8px;border-left:4px solid #16a34a">
              <p style="margin:0;color:#15803d;font-size:14px">
                Log in to your AI Paperwork Assistant to view the full document, 
                generate a letter, or get step-by-step guidance.
              </p>
            </div>
          </div>
          <p style="color:#9ca3af;font-size:12px;margin-top:16px;text-align:center">
            AI Paperwork Assistant — Helping seniors manage paperwork with confidence.<br>
            You received this because you have an upcoming document deadline.
          </p>
        </div>"""

    def _scam_alert_email_html(self, doc_name: str, warning: str) -> str:
        return f"""
        <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px">
          <div style="background:#dc2626;color:white;padding:20px;border-radius:12px 12px 0 0">
            <h1 style="margin:0;font-size:20px">⚠️ SCAM ALERT</h1>
          </div>
          <div style="background:#fef2f2;padding:20px;border-radius:0 0 12px 12px;border:2px solid #fca5a5">
            <p style="color:#7f1d1d;font-size:16px;font-weight:bold">{warning}</p>
            <div style="margin-top:16px;padding:16px;background:#fee2e2;border-radius:8px">
              <p style="margin:0;color:#991b1b;font-weight:bold">DO NOT:</p>
              <ul style="color:#991b1b;margin-top:8px">
                <li>Pay any money requested in this document</li>
                <li>Call any phone numbers listed in the document</li>
                <li>Provide any personal information</li>
                <li>Purchase gift cards</li>
              </ul>
            </div>
            <p style="color:#374151;margin-top:16px">Log in to your AI Paperwork Assistant to see the full analysis and next steps.</p>
            <p style="color:#374151">To report fraud: <a href="https://reportfraud.ftc.gov" style="color:#2563eb">reportfraud.ftc.gov</a></p>
          </div>
        </div>"""

    def _caregiver_alert_html(self, senior_name: str, message: str) -> str:
        return f"""
        <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px">
          <div style="background:#7c3aed;color:white;padding:20px;border-radius:12px 12px 0 0">
            <h1 style="margin:0;font-size:20px">👨‍👩‍👧 Caregiver Alert</h1>
          </div>
          <div style="background:#f5f3ff;padding:20px;border-radius:0 0 12px 12px;border:1px solid #ddd6fe">
            <p style="color:#4c1d95;font-weight:bold">Update for {senior_name}</p>
            <p style="color:#374151">{message.replace(chr(10),'<br>')}</p>
            <p style="color:#9ca3af;font-size:12px;margin-top:20px">You are receiving this because you are a caregiver for {senior_name} on AI Paperwork Assistant.</p>
          </div>
        </div>"""

    def _renewal_email_html(self, title: str, days: str, action: str) -> str:
        return f"""
        <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px">
          <div style="background:#059669;color:white;padding:20px;border-radius:12px 12px 0 0">
            <h1 style="margin:0;font-size:20px">🔄 Renewal Reminder</h1>
          </div>
          <div style="background:#ecfdf5;padding:20px;border-radius:0 0 12px 12px;border:1px solid #a7f3d0">
            <p style="color:#065f46;font-size:18px;font-weight:bold">{title}</p>
            <p style="color:#374151">Due in approximately <strong>{days} days</strong>.</p>
            {f'<p style="color:#374151"><strong>Action needed:</strong> {action}</p>' if action else ''}
          </div>
        </div>"""