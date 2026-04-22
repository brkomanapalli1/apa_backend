"""Caregiver portal API routes — Phase 3."""
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from app.core.deps import get_current_user, get_db
from app.models.user import User
from app.services.caregiver_service import CaregiverService

router = APIRouter()
service = CaregiverService()


@router.get("/members")
def list_caregiver_members(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all caregivers who have access to current user's documents."""
    from app.models.document import Invitation
    invitations = (
        db.query(Invitation)
        .filter(Invitation.inviter_id == current_user.id)
        .order_by(Invitation.created_at.desc())
        .all()
    )
    return [
        {
            "id": inv.id,
            "email": inv.invitee_email,
            "full_name": inv.invitee_user.full_name if getattr(inv, "invitee_user", None) else None,
            "role": str(inv.role),
            "accepted": inv.accepted,
            "revoked": inv.revoked,
            "created_at": str(inv.created_at),
        }
        for inv in invitations
    ]


@router.get("/dashboard")
def caregiver_dashboard(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get caregiver dashboard — all seniors and their pending items."""
    return service.get_caregiver_dashboard(current_user.id, db)


@router.get("/seniors/{senior_id}/activity")
def senior_activity_feed(
    senior_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get recent activity feed for a senior (caregiver view)."""
    try:
        return service.get_senior_activity_feed(current_user.id, senior_id, db)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
