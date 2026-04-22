"""Emergency vault API routes — Phase 3."""
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.core.deps import get_current_user, get_db
from app.models.user import User
from app.services.emergency_vault_service import EmergencyVaultService

router = APIRouter()
service = EmergencyVaultService()


class AddToVaultRequest(BaseModel):
    document_id: int
    category: str


@router.get("/items")
def get_vault_items(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get emergency vault items — alias for frontend compatibility."""
    try:
        ip = request.client.host if request.client else None
        return service.get_vault_contents(current_user.id, current_user.id, db, ip)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.get("/")
def get_vault(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get emergency vault contents."""
    try:
        ip = request.client.host if request.client else None
        return service.get_vault_contents(current_user.id, current_user.id, db, ip)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.get("/summary")
def vault_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get vault completion summary card."""
    return service.get_vault_summary_card(current_user.id, db)


@router.post("/add")
def add_to_vault(
    payload: AddToVaultRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Add a document to the emergency vault."""
    try:
        return service.add_to_vault(payload.document_id, current_user.id, payload.category, db)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{document_id}")
def remove_from_vault(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Remove a document from the vault."""
    try:
        service.remove_from_vault(document_id, current_user.id, db)
        return {"ok": True}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/caregiver/{senior_id}")
def get_vault_as_caregiver(
    senior_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Caregiver accesses a senior's vault (with audit logging)."""
    try:
        ip = request.client.host if request.client else None
        return service.get_vault_contents(senior_id, current_user.id, db, ip)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
