"""
renewals.py — Smart Renewal Tracking API (Phase 3)

GET  /renewals              — All renewals for current user
GET  /renewals/urgent       — Only urgent/expiring soon
GET  /renewals/medicare     — Medicare enrollment windows
POST /renewals/manual       — Add a manual renewal item
DELETE /renewals/{id}       — Remove a manual renewal
"""
from __future__ import annotations
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.core.deps import get_current_user, get_db
from app.models.user import User

router = APIRouter()


class ManualRenewalRequest(BaseModel):
    name: str
    expiry_date: str       # ISO format YYYY-MM-DD
    category: str          # medicare, insurance, housing, medication, identity, other
    notes: str = ""


@router.get("")
def get_all_renewals(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get all tracked renewals sorted by urgency."""
    from app.services.renewal_tracking import RenewalTrackingService
    svc = RenewalTrackingService()
    return svc.get_renewals_for_user(current_user.id, db)


@router.get("/urgent")
def get_urgent_renewals(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get only renewals expiring within 30 days."""
    from app.services.renewal_tracking import RenewalTrackingService
    svc = RenewalTrackingService()
    data = svc.get_renewals_for_user(current_user.id, db)
    return {
        "expired": data["expired"],
        "urgent": data["urgent"],
        "needs_immediate_action": data["needs_immediate_action"],
    }


@router.get("/medicare")
def get_medicare_windows(current_user: User = Depends(get_current_user)):
    """Get this year's Medicare enrollment windows."""
    from app.services.renewal_tracking import RenewalTrackingService
    svc = RenewalTrackingService()
    return {"windows": svc._get_upcoming_medicare_windows()}


@router.post("/manual")
def add_manual_renewal(
    payload: ManualRenewalRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Manually add a renewal item (e.g. passport, driver's license)."""
    # Validate date
    try:
        datetime.strptime(payload.expiry_date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="expiry_date must be YYYY-MM-DD format")

    valid_categories = {"medicare", "insurance", "housing", "medication", "identity", "other"}
    if payload.category not in valid_categories:
        raise HTTPException(status_code=400, detail=f"category must be one of {valid_categories}")

    # Store in user preferences
    prefs = dict(current_user.preferences or {})
    manual_renewals = prefs.get("manual_renewals", [])
    new_item = {
        "id": len(manual_renewals) + 1,
        "name": payload.name,
        "expiry_date": payload.expiry_date,
        "category": payload.category,
        "notes": payload.notes,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    manual_renewals.append(new_item)
    prefs["manual_renewals"] = manual_renewals
    current_user.preferences = prefs
    db.add(current_user)
    db.commit()

    return {"ok": True, "renewal": new_item}


@router.delete("/manual/{renewal_id}")
def delete_manual_renewal(
    renewal_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Remove a manually added renewal."""
    prefs = dict(current_user.preferences or {})
    manual_renewals = prefs.get("manual_renewals", [])
    prefs["manual_renewals"] = [r for r in manual_renewals if r.get("id") != renewal_id]
    current_user.preferences = prefs
    db.add(current_user)
    db.commit()
    return {"ok": True}
