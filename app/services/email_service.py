from __future__ import annotations

import smtplib
from email.message import EmailMessage

from app.core.config import settings


class EmailService:
    def is_configured(self) -> bool:
        return bool(settings.SMTP_HOST and settings.SMTP_FROM)

    def send_email(self, *, to: str, subject: str, html: str, text: str | None = None) -> bool:
        if not self.is_configured():
            return False

        message = EmailMessage()
        message['From'] = settings.SMTP_FROM
        message['To'] = to
        message['Subject'] = subject
        message.set_content(text or 'Please view this email in an HTML-capable client.')
        message.add_alternative(html, subtype='html')

        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=20) as smtp:
            if settings.SMTP_STARTTLS:
                smtp.starttls()
            if settings.SMTP_USER and settings.SMTP_PASSWORD:
                smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            smtp.send_message(message)
        return True
