from __future__ import annotations
import logging
from app.core.config import settings

logger = logging.getLogger(__name__)


class EmailService:
    def is_configured(self) -> bool:
        return bool(getattr(settings, "RESEND_API_KEY", None) and settings.SMTP_FROM)

    def send_email(self, *, to: str, subject: str, html: str, text: str | None = None) -> bool:
        """Send a single email via Resend API. Returns True on success."""
        if not self.is_configured():
            logger.debug("Email skipped — Resend not configured")
            return False
        try:
            import resend
            resend.api_key = settings.RESEND_API_KEY

            from_address = f"{settings.SMTP_FROM_NAME} <{settings.SMTP_FROM}>"

            params: dict = {
                "from": from_address,
                "to": [to],
                "subject": subject,
                "html": html,
            }
            if text:
                params["text"] = text

            response = resend.Emails.send(params)
            logger.info("Email sent to %s: %s (id=%s)", to, subject, response.get("id"))
            return True
        except Exception as exc:
            logger.error("Email to %s failed: %s", to, exc)
            return False

    def send_caregiver_invitation(
        self, to: str, inviter_name: str, role: str,
        personal_message: str | None, invitation_token: str,
    ) -> bool:
        accept_url = f"{settings.FRONTEND_URL}/invitations/accept/{invitation_token}"
        html = f"""
        <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px">
          <div style="background:#7c3aed;color:white;padding:20px;border-radius:12px 12px 0 0">
            <h1 style="margin:0;font-size:20px">You've been invited to help!</h1>
          </div>
          <div style="background:#f5f3ff;padding:20px;border-radius:0 0 12px 12px;border:1px solid #ddd6fe">
            <p style="color:#374151;font-size:16px"><strong>{inviter_name}</strong> has invited you
            to help manage their paperwork as a <strong>{role}</strong>.</p>
            {f'<p style="color:#6b7280;font-style:italic">&ldquo;{personal_message}&rdquo;</p>' if personal_message else ""}
            <div style="margin:20px 0;text-align:center">
              <a href="{accept_url}" style="background:#7c3aed;color:white;padding:14px 28px;border-radius:8px;text-decoration:none;font-weight:bold;font-size:16px">Accept Invitation</a>
            </div>
            <p style="color:#9ca3af;font-size:12px">As a <strong>{role}</strong>, you will be able to
            help {inviter_name} understand and manage important paperwork using AI assistance.</p>
          </div>
        </div>"""
        return self.send_email(
            to=to, subject=f"{inviter_name} invited you to AI Paperwork Assistant",
            html=html, text=f"{inviter_name} invited you as {role}. Accept: {accept_url}",
        )