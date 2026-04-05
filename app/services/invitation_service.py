from secrets import token_urlsafe

from sqlalchemy.orm import Session

from app.models.document import Invitation
from app.models.user import User
from app.services.email_service import EmailService
from app.worker.tasks import send_email_task


class InvitationService:
    def __init__(self) -> None:
        self.email = EmailService()

    def create_invitation(self, db: Session, inviter: User, invitee_email: str, role: str, frontend_url: str) -> Invitation:
        invitation = Invitation(inviter_id=inviter.id, invitee_email=invitee_email, token=token_urlsafe(24), role=role, accepted=False)
        db.add(invitation)
        db.commit()
        db.refresh(invitation)

        accept_url = f'{frontend_url}/invitations/accept/{invitation.token}'
        html = f'<p>{inviter.full_name} invited you to collaborate as <b>{role}</b>.</p><p><a href="{accept_url}">Accept invitation</a></p>'
        text = f'{inviter.full_name} invited you to collaborate as {role}. Accept: {accept_url}'
        try:
            send_email_task.delay(invitee_email, 'You have been invited to AI Paperwork Assistant', html, text)
        except Exception:
            self.email.send_email(to=invitee_email, subject='You have been invited to AI Paperwork Assistant', html=html, text=text)
        return invitation


    def resend_invitation(self, invitation: Invitation, inviter_name: str, frontend_url: str) -> None:
        accept_url = f'{frontend_url}/invitations/accept/{invitation.token}'
        html = f'<p>{inviter_name} re-sent your invitation to collaborate as <b>{invitation.role}</b>.</p><p><a href="{accept_url}">Accept invitation</a></p>'
        text = f'{inviter_name} re-sent your invitation to collaborate as {invitation.role}. Accept: {accept_url}'
        try:
            send_email_task.delay(invitation.invitee_email, 'Reminder: invitation to AI Paperwork Assistant', html, text)
        except Exception:
            self.email.send_email(to=invitation.invitee_email, subject='Reminder: invitation to AI Paperwork Assistant', html=html, text=text)
