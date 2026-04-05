from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_current_user, get_db
from app.models.document import Invitation
from app.schemas.document import InvitationRequest
from app.services.audit_service import AuditService
from app.services.invitation_service import InvitationService

router = APIRouter()
service = InvitationService()
audit = AuditService()


def _serialize(invitation: Invitation) -> dict:
    return {
        'id': invitation.id,
        'invitee_email': invitation.invitee_email,
        'role': invitation.role,
        'accepted': invitation.accepted,
        'revoked': invitation.revoked,
        'revoked': invitation.revoked,
        'token': invitation.token,
        'created_at': invitation.created_at.isoformat() if invitation.created_at else None,
    }


@router.get('')
def list_invitations(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    invitations = db.query(Invitation).filter(Invitation.inviter_id == current_user.id).order_by(Invitation.created_at.desc()).all()
    return [_serialize(inv) for inv in invitations]


@router.get('/preview/{token}')
def preview(token: str, db: Session = Depends(get_db)):
    invitation = db.query(Invitation).filter(Invitation.token == token).first()
    if not invitation or invitation.revoked:
        return {'exists': False}
    return {
        'exists': True,
        'invitee_email': invitation.invitee_email,
        'role': invitation.role,
        'accepted': invitation.accepted,
        'revoked': invitation.revoked,
    }


@router.post('')
def invite(payload: InvitationRequest, request: Request, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    invitation = service.create_invitation(db, current_user, payload.invitee_email, payload.role, settings.FRONTEND_URL)
    audit.log(db, action='invitation.created', user_id=current_user.id, entity_type='invitation', entity_id=str(invitation.id), detail=payload.invitee_email, ip_address=request.client.host if request.client else None)
    return {'message': 'Invitation created', 'token': invitation.token, 'role': invitation.role}


@router.post('/accept/{token}')
def accept(token: str, request: Request, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    invitation = db.query(Invitation).filter(Invitation.token == token).first()
    if invitation and not invitation.revoked and invitation.invitee_email == current_user.email:
        invitation.accepted = True
        db.add(invitation)
        db.commit()
        audit.log(db, action='invitation.accepted', user_id=current_user.id, entity_type='invitation', entity_id=str(invitation.id), detail=token, ip_address=request.client.host if request.client else None)
        return {'accepted': True, 'role': invitation.role}
    return {'accepted': False}


@router.post('/{invitation_id}/resend')
def resend(invitation_id: int, request: Request, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    invitation = db.query(Invitation).filter(Invitation.id == invitation_id, Invitation.inviter_id == current_user.id).first()
    if not invitation:
        return {'resent': False}
    service.resend_invitation(invitation, current_user.full_name, settings.FRONTEND_URL)
    audit.log(db, action='invitation.resent', user_id=current_user.id, entity_type='invitation', entity_id=str(invitation.id), detail=invitation.invitee_email, ip_address=request.client.host if request.client else None)
    return {'resent': True}


@router.post('/{invitation_id}/revoke')
def revoke(invitation_id: int, request: Request, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    invitation = db.query(Invitation).filter(Invitation.id == invitation_id, Invitation.inviter_id == current_user.id).first()
    if not invitation:
        return {'revoked': False}
    invitation.revoked = True
    db.add(invitation)
    db.commit()
    audit.log(db, action='invitation.revoked', user_id=current_user.id, entity_type='invitation', entity_id=str(invitation.id), detail=invitation.invitee_email, ip_address=request.client.host if request.client else None)
    return {'revoked': True}
