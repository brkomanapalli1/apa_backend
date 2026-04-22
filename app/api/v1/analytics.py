"""
analytics.py — Timeline, Benefits Navigator, Financial Analysis,
               Renewal Tracking, Medication, Alerts API routes
"""
from __future__ import annotations
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.core.deps import get_current_user, get_db
from app.models.user import User

router = APIRouter()


# ── Timeline ──────────────────────────────────────────────────────────────

@router.get("/timeline")
def get_timeline(
    limit: int = Query(50, le=200),
    category: str | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Smart document timeline — chronological life-document history."""
    from app.services.timeline_service import TimelineService
    return TimelineService().get_timeline(current_user.id, db, limit=limit, category_filter=category)


# ── Benefits Navigator ────────────────────────────────────────────────────

class BenefitsProfileRequest(BaseModel):
    age: int = 65
    monthly_income: float = 0
    is_veteran: bool = False
    has_medicare: bool = True
    has_medicaid: bool = False
    owns_home: bool = False
    has_disability: bool = False
    state: str = ""


@router.get("/benefits")
def get_all_benefits(
    current_user: User = Depends(get_current_user),
):
    """Get all available government benefit programs."""
    from app.services.benefits_navigator import get_all_programs, DISCLAIMER
    return {"programs": get_all_programs(), "disclaimer": DISCLAIMER}


@router.post("/benefits/check")
def check_benefits(
    profile: BenefitsProfileRequest,
    current_user: User = Depends(get_current_user),
):
    """Check which benefits user may be eligible for based on profile."""
    from app.services.benefits_navigator import check_benefits_eligibility, DISCLAIMER
    results = check_benefits_eligibility(profile.dict())
    return {
        "potentially_eligible": results,
        "total_programs": len(results),
        "disclaimer": DISCLAIMER,
    }


# ── Financial Analysis ────────────────────────────────────────────────────

@router.get("/financial-alerts")
def financial_alerts(
    months_back: int = 6,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Financial change alerts — alias used by frontend dashboard."""
    from app.services.financial_analysis import analyze_financial_changes
    return analyze_financial_changes(current_user.id, db, months_back=months_back)


@router.get("/financial")
def financial_analysis(
    months_back: int = Query(6, ge=1, le=24),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Financial change detection — bill trends, spikes, duplicate charges."""
    from app.services.financial_analysis import analyze_financial_changes
    return analyze_financial_changes(current_user.id, db, months_back=months_back)


# ── Renewal Tracking ──────────────────────────────────────────────────────

@router.get("/renewals")
def get_renewals(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Smart renewal tracking — Medicare, insurance, Medicaid, lease, medications."""
    from app.services.renewal_tracking import RenewalTrackingService
    return RenewalTrackingService().get_renewals_for_user(current_user.id, db)


# ── Medication Tracking ───────────────────────────────────────────────────

@router.get("/medications")
def get_medications(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get all medications extracted from the user's documents
    with daily reminder schedule.
    """
    from app.models.document import Document
    from app.db.enums import DocumentStatus
    from app.services.medication_service import (
        extract_medications, format_medication_reminders, generate_medication_schedule
    )

    # Get all processed documents that may contain medications
    docs = (
        db.query(Document)
        .filter(
            Document.owner_id == current_user.id,
            Document.status == DocumentStatus.PROCESSED,
        )
        .order_by(Document.created_at.desc())
        .all()
    )

    all_medications = []
    sources = []

    for doc in docs:
        fields = doc.extracted_fields or {}
        meds_data = fields.get("medications", [])
        if meds_data and isinstance(meds_data, list) and meds_data:
            all_medications.extend(meds_data)
            sources.append({"document_id": doc.id, "document_name": doc.name})

    # Also try extracting from the latest discharge/prescription documents
    from app.services.medication_service import MedicationEntry
    structured_meds = []
    for med_dict in all_medications:
        if isinstance(med_dict, dict):
            structured_meds.append(MedicationEntry(
                name=med_dict.get("name", "Unknown"),
                dosage=med_dict.get("dosage"),
                frequency=med_dict.get("frequency"),
                reminder_times=med_dict.get("reminder_times", []),
                instructions=med_dict.get("instructions", ""),
                with_food=med_dict.get("with_food"),
                refill_date=med_dict.get("refill_date"),
            ))

    schedule = generate_medication_schedule(structured_meds)
    reminders = format_medication_reminders(structured_meds)

    return {
        "medications": all_medications,
        "daily_schedule": schedule,
        "reminders": reminders,
        "total_medications": len(all_medications),
        "sources": sources,
        "disclaimer": (
            "This information is extracted from uploaded documents for reminder purposes only. "
            "Always follow your doctor's or pharmacist's exact instructions."
        ),
    }


# ── Scam Analysis ─────────────────────────────────────────────────────────

@router.get("/scam-history")
def get_scam_history(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get history of scam detections for the user's documents."""
    from app.models.document import Document
    from app.db.enums import DocumentStatus

    docs = (
        db.query(Document)
        .filter(
            Document.owner_id == current_user.id,
            Document.status == DocumentStatus.PROCESSED,
        )
        .order_by(Document.created_at.desc())
        .all()
    )

    flagged = []
    for doc in docs:
        fields = doc.extracted_fields or {}
        scam = fields.get("scam_analysis", {})
        if isinstance(scam, dict) and scam.get("is_suspicious"):
            flagged.append({
                "document_id": doc.id,
                "document_name": doc.name,
                "risk_level": scam.get("risk_level", "unknown"),
                "confidence": scam.get("confidence", 0),
                "warning_message": scam.get("warning_message", ""),
                "detected_at": str(doc.updated_at),
            })

    return {
        "flagged_documents": flagged,
        "total_flagged": len(flagged),
        "report_fraud_url": "https://reportfraud.ftc.gov",
        "irs_fraud_url": "https://www.irs.gov/individuals/how-do-you-report-suspected-tax-fraud-activity",
    }


# ── Alerts / Notifications ────────────────────────────────────────────────

class SendTestAlertRequest(BaseModel):
    channel: str = "email"  # email | sms | push
    message: str = "Test alert from AI Paperwork Assistant"


@router.post("/alerts/test")
def send_test_alert(
    payload: SendTestAlertRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Send a test alert to verify notification settings are working."""
    from app.services.alert_service import AlertService, AlertMessage, AlertChannel, AlertPriority

    channel_map = {
        "email": AlertChannel.EMAIL,
        "sms": AlertChannel.SMS,
        "push": AlertChannel.PUSH,
    }
    channel = channel_map.get(payload.channel, AlertChannel.IN_APP)

    alert = AlertMessage(
        user_id=current_user.id,
        title="✅ Test Alert",
        body=payload.message or "This is a test notification from AI Paperwork Assistant. Your alerts are working correctly!",
        channels=[channel, AlertChannel.IN_APP],
        priority=AlertPriority.NORMAL,
        metadata={"type": "test_alert"},
    )
    results = AlertService().send(alert, db)
    return {"sent": results, "channel": payload.channel}


@router.get("/alerts/preferences")
def get_alert_preferences(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get user's notification preferences."""
    profile = current_user.profile or {}
    return {
        "email_enabled": profile.get("notify_email", True),
        "sms_enabled": profile.get("notify_sms", False),
        "push_enabled": profile.get("notify_push", True),
        "deadline_reminders": profile.get("deadline_reminders", True),
        "medication_reminders": profile.get("medication_reminders", True),
        "caregiver_alerts": profile.get("caregiver_alerts", True),
        "scam_alerts": profile.get("scam_alerts", True),
        "bill_spike_alerts": profile.get("bill_spike_alerts", True),
        "phone": profile.get("phone", ""),
    }


class UpdateAlertPreferencesRequest(BaseModel):
    email_enabled: bool = True
    sms_enabled: bool = False
    push_enabled: bool = True
    deadline_reminders: bool = True
    medication_reminders: bool = True
    caregiver_alerts: bool = True
    scam_alerts: bool = True
    bill_spike_alerts: bool = True
    phone: str = ""


@router.put("/alerts/preferences")
def update_alert_preferences(
    prefs: UpdateAlertPreferencesRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update user's notification preferences."""
    profile = dict(current_user.profile or {})
    profile.update({
        "notify_email": prefs.email_enabled,
        "notify_sms": prefs.sms_enabled,
        "notify_push": prefs.push_enabled,
        "deadline_reminders": prefs.deadline_reminders,
        "medication_reminders": prefs.medication_reminders,
        "caregiver_alerts": prefs.caregiver_alerts,
        "scam_alerts": prefs.scam_alerts,
        "bill_spike_alerts": prefs.bill_spike_alerts,
        "phone": prefs.phone,
    })
    current_user.profile = profile
    db.add(current_user)
    db.commit()
    return {"ok": True, "preferences": profile}
