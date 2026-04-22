"""
renewal_tracking.py — Smart Renewal Tracking (Phase 3)

Tracks expiration dates for:
  - Medicare enrollment periods (Annual Enrollment: Oct 15 – Dec 7)
  - Insurance renewal dates
  - Medicaid annual renewal
  - Driver's license expiration
  - Passport expiration
  - Benefits eligibility re-verification
  - HOA and lease renewals

Sends reminders at: 90 days, 60 days, 30 days, 14 days, 7 days before expiry.
"""
from __future__ import annotations

import re
from datetime import datetime, date, timezone, timedelta
from typing import Any

from sqlalchemy.orm import Session

# Annual Medicare enrollment windows (federal fixed dates)
MEDICARE_ENROLLMENT_WINDOWS = [
    {"name": "Annual Enrollment Period (AEP)", "start": "10-15", "end": "12-07",
     "description": "Change Medicare Advantage or Part D drug plan"},
    {"name": "General Enrollment Period (GEP)", "start": "01-01", "end": "03-31",
     "description": "Enroll in Medicare Part A and/or Part B if you missed your initial window"},
    {"name": "Medicare Advantage Open Enrollment", "start": "01-01", "end": "03-31",
     "description": "Switch Medicare Advantage plans or return to Original Medicare"},
]

# Standard reminder schedule (days before expiry)
REMINDER_SCHEDULE = [90, 60, 30, 14, 7, 1]


class RenewalItem:
    def __init__(
        self,
        name: str,
        expiry_date: str,
        category: str,
        source: str = "manual",
        document_id: int | None = None,
        notes: str = "",
    ):
        self.name = name
        self.expiry_date = expiry_date
        self.category = category
        self.source = source
        self.document_id = document_id
        self.notes = notes

    @property
    def days_until_expiry(self) -> int | None:
        try:
            expiry = datetime.strptime(self.expiry_date[:10], "%Y-%m-%d").date()
            return (expiry - date.today()).days
        except (ValueError, TypeError):
            return None

    def is_urgent(self) -> bool:
        days = self.days_until_expiry
        return days is not None and days <= 30

    def to_dict(self) -> dict[str, Any]:
        days = self.days_until_expiry
        return {
            "name": self.name,
            "expiry_date": self.expiry_date,
            "category": self.category,
            "days_until_expiry": days,
            "is_urgent": self.is_urgent(),
            "is_expired": days is not None and days < 0,
            "status": self._status_label(days),
            "source": self.source,
            "document_id": self.document_id,
            "notes": self.notes,
        }

    def _status_label(self, days: int | None) -> str:
        if days is None:
            return "unknown"
        if days < 0:
            return "expired"
        if days <= 7:
            return "critical"
        if days <= 30:
            return "urgent"
        if days <= 90:
            return "upcoming"
        return "ok"


class RenewalTrackingService:
    """Tracks renewals and sends timely reminders."""

    def get_renewals_for_user(
        self, user_id: int, db: Session,
    ) -> dict[str, Any]:
        """Get all tracked renewals for a user."""
        from app.models.document import Document
        from app.db.enums import DocumentStatus

        renewals: list[RenewalItem] = []

        # Extract renewals from processed documents
        docs = (
            db.query(Document)
            .filter(
                Document.owner_id == user_id,
                Document.status == DocumentStatus.PROCESSED,
            )
            .all()
        )

        for doc in docs:
            extracted = self._extract_renewals_from_doc(doc)
            renewals.extend(extracted)

        # Add Medicare enrollment windows
        medicare_windows = self._get_upcoming_medicare_windows()
        for window in medicare_windows:
            renewals.append(RenewalItem(
                name=window["name"],
                expiry_date=window["end"],
                category="medicare_enrollment",
                source="federal_calendar",
                notes=window["description"],
            ))

        # Sort by urgency
        renewals.sort(key=lambda r: (r.days_until_expiry or 9999))

        # Categorize
        expired = [r.to_dict() for r in renewals if (r.days_until_expiry or 0) < 0]
        urgent = [r.to_dict() for r in renewals if 0 <= (r.days_until_expiry or 9999) <= 30]
        upcoming = [r.to_dict() for r in renewals if 30 < (r.days_until_expiry or 9999) <= 90]
        future = [r.to_dict() for r in renewals if (r.days_until_expiry or 0) > 90]

        return {
            "user_id": user_id,
            "expired": expired,
            "urgent": urgent,
            "upcoming": upcoming,
            "future": future,
            "total": len(renewals),
            "needs_immediate_action": len(expired) + len(urgent),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    def _extract_renewals_from_doc(self, doc) -> list[RenewalItem]:
        """Extract renewal dates from a processed document."""
        renewals = []
        fields = doc.extracted_fields or {}
        doc_type = str(doc.document_type)

        # Medicaid renewal
        if doc_type == "medicaid_notice":
            renewal_date = fields.get("renewal_due_date")
            if renewal_date:
                renewals.append(RenewalItem(
                    name="Medicaid Renewal",
                    expiry_date=str(renewal_date),
                    category="medicaid",
                    source="document",
                    document_id=doc.id,
                    notes="Missing renewal may cause coverage gap",
                ))

        # Insurance renewal
        if doc_type in ("home_insurance_bill", "explanation_of_benefits"):
            for deadline in (doc.deadlines or []):
                if "renewal" in (deadline.get("title") or "").lower():
                    renewals.append(RenewalItem(
                        name=f"Insurance Renewal: {doc.name}",
                        expiry_date=str(deadline.get("date", "")),
                        category="insurance",
                        source="document",
                        document_id=doc.id,
                    ))

        # Lease renewal
        if doc_type == "rent_statement":
            lease_end = fields.get("lease_end_date")
            if lease_end:
                renewals.append(RenewalItem(
                    name="Lease Renewal",
                    expiry_date=str(lease_end),
                    category="housing",
                    source="document",
                    document_id=doc.id,
                ))

        # Medicare prescription renewal
        if doc_type == "prescription_drug_notice":
            for deadline in (doc.deadlines or []):
                renewals.append(RenewalItem(
                    name=f"Prescription: {deadline.get('title', 'Renewal')}",
                    expiry_date=str(deadline.get("date", "")),
                    category="medication",
                    source="document",
                    document_id=doc.id,
                ))

        return [r for r in renewals if r.expiry_date and r.expiry_date != "None"]

    def _get_upcoming_medicare_windows(self) -> list[dict[str, Any]]:
        """Get this year's Medicare enrollment windows."""
        year = date.today().year
        windows = []
        for window in MEDICARE_ENROLLMENT_WINDOWS:
            end_date = datetime.strptime(f"{year}-{window['end']}", "%Y-%m-%d").date()
            if end_date >= date.today():
                windows.append({
                    "name": window["name"],
                    "end": str(end_date),
                    "description": window["description"],
                })
        return windows

    def schedule_renewal_reminders(
        self, user_id: int, db: Session,
    ) -> int:
        """
        Schedule reminder notifications for all upcoming renewals.
        Called by Celery beat daily.
        Returns number of reminders scheduled.
        """
        from app.services.alert_service import AlertService
        alerts = AlertService()
        renewal_data = self.get_renewals_for_user(user_id, db)
        count = 0

        for item in renewal_data.get("urgent", []):
            days = item.get("days_until_expiry", 0)
            if days in REMINDER_SCHEDULE:
                alerts.send_renewal_reminder(
                    user_id=user_id,
                    renewal_type=item["name"],
                    expiry_date=item["expiry_date"],
                    days_until=days,
                    db=db,
                )
                count += 1

        return count
