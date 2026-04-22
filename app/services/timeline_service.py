"""
timeline_service.py — Smart Timeline Generator (Phase 5)

Creates a chronological life-document timeline:
  May 3  — Hospital visit (discharge papers)
  May 10 — New prescription added (metformin 500mg)
  Jun 1  — Insurance plan changed (EOB shows new carrier)
  Jun 14 — Medicare renewal deadline
  Jul 1  — Electricity bill spike (+38%)

Groups events by:
  - Medical events
  - Financial changes
  - Government/benefits
  - Deadlines and renewals
  - Medications
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session


class TimelineEvent:
    def __init__(
        self,
        date: str,
        title: str,
        category: str,
        description: str,
        document_id: int | None = None,
        icon: str = "📄",
        severity: str = "normal",
    ):
        self.date = date
        self.title = title
        self.category = category
        self.description = description
        self.document_id = document_id
        self.icon = icon
        self.severity = severity

    def to_dict(self) -> dict[str, Any]:
        return {
            "date": self.date,
            "title": self.title,
            "category": self.category,
            "description": self.description,
            "document_id": self.document_id,
            "icon": self.icon,
            "severity": self.severity,
        }


CATEGORY_ICONS = {
    "medical": "🏥",
    "insurance": "📋",
    "medicare": "🏛️",
    "medication": "💊",
    "utility": "⚡",
    "financial": "💰",
    "legal": "⚖️",
    "government": "🏛️",
    "deadline": "⏰",
    "scam": "🚨",
    "general": "📄",
}


class TimelineService:
    """Generates a smart chronological document timeline for a user."""

    def get_timeline(
        self,
        user_id: int,
        db: Session,
        limit: int = 50,
        category_filter: str | None = None,
    ) -> dict[str, Any]:
        """Build a full chronological timeline for a user."""
        from app.models.document import Document

        docs = (
            db.query(Document)
            .filter(Document.owner_id == user_id)
            .order_by(Document.created_at.desc())
            .limit(200)
            .all()
        )

        events: list[TimelineEvent] = []

        for doc in docs:
            # Event for document upload/processing
            category = self._doc_type_to_category(str(doc.document_type))
            events.append(TimelineEvent(
                date=str(doc.created_at.date()),
                title=self._doc_type_to_title(str(doc.document_type), doc.name),
                category=category,
                description=doc.summary or f"{doc.name} analyzed",
                document_id=doc.id,
                icon=CATEGORY_ICONS.get(category, "📄"),
                severity=self._get_severity(doc),
            ))

            # Add deadline events
            for deadline in (doc.deadlines or []):
                if deadline.get("date"):
                    events.append(TimelineEvent(
                        date=deadline["date"],
                        title=f"⏰ Deadline: {deadline.get('title', 'Important date')}",
                        category="deadline",
                        description=deadline.get("action", "Action required"),
                        document_id=doc.id,
                        icon="⏰",
                        severity="high",
                    ))

            # Add medication events
            fields = doc.extracted_fields or {}
            medications = fields.get("medications", [])
            for med in (medications if isinstance(medications, list) else []):
                if isinstance(med, dict) and med.get("name"):
                    events.append(TimelineEvent(
                        date=str(doc.created_at.date()),
                        title=f"💊 Medication: {med['name']}",
                        category="medication",
                        description=med.get("instructions") or f"{med['name']} {med.get('dosage', '')}",
                        document_id=doc.id,
                        icon="💊",
                        severity="normal",
                    ))

            # Add scam alerts
            scam = fields.get("scam_analysis", {})
            if isinstance(scam, dict) and scam.get("risk_level") in ("high", "medium"):
                events.append(TimelineEvent(
                    date=str(doc.created_at.date()),
                    title=f"🚨 Scam detected: {doc.name}",
                    category="scam",
                    description=scam.get("warning_message", "Suspicious document detected"),
                    document_id=doc.id,
                    icon="🚨",
                    severity="urgent",
                ))

        # Sort by date descending
        events.sort(key=lambda e: e.date, reverse=True)

        # Filter by category if requested
        if category_filter:
            events = [e for e in events if e.category == category_filter]

        # Apply limit
        events = events[:limit]

        # Group by month
        grouped = self._group_by_month(events)

        return {
            "user_id": user_id,
            "total_events": len(events),
            "events": [e.to_dict() for e in events],
            "grouped_by_month": grouped,
            "categories": list(CATEGORY_ICONS.keys()),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    def _doc_type_to_category(self, doc_type: str) -> str:
        mapping = {
            "medicare_summary_notice": "medicare",
            "explanation_of_benefits": "insurance",
            "claim_denial_letter": "insurance",
            "itemized_medical_bill": "medical",
            "medicaid_notice": "government",
            "social_security_notice": "government",
            "prescription_drug_notice": "medication",
            "veterans_benefits_letter": "government",
            "electricity_bill": "utility",
            "natural_gas_bill": "utility",
            "water_sewer_bill": "utility",
            "telecom_bill": "utility",
            "credit_card_statement": "financial",
            "collection_notice": "financial",
            "irs_notice": "government",
            "property_tax_bill": "financial",
            "rent_statement": "financial",
            "mortgage_statement": "financial",
        }
        return mapping.get(doc_type, "general")

    def _doc_type_to_title(self, doc_type: str, filename: str) -> str:
        titles = {
            "medicare_summary_notice": "Medicare Summary Notice received",
            "explanation_of_benefits": "Insurance EOB received",
            "claim_denial_letter": "Insurance claim denied",
            "itemized_medical_bill": "Medical bill received",
            "medicaid_notice": "Medicaid notice received",
            "social_security_notice": "Social Security notice",
            "prescription_drug_notice": "Prescription drug notice",
            "electricity_bill": "Electricity bill",
            "natural_gas_bill": "Gas bill",
            "water_sewer_bill": "Water bill",
            "collection_notice": "Collection notice received",
            "irs_notice": "IRS notice received",
        }
        return titles.get(doc_type, f"Document uploaded: {filename}")

    def _get_severity(self, doc) -> str:
        if str(doc.document_type) in ("claim_denial_letter", "collection_notice", "irs_notice"):
            return "high"
        if doc.deadlines:
            return "medium"
        return "normal"

    def _group_by_month(self, events: list[TimelineEvent]) -> list[dict[str, Any]]:
        groups: dict[str, list[dict]] = {}
        for event in events:
            try:
                dt = datetime.strptime(event.date[:10], "%Y-%m-%d")
                key = dt.strftime("%B %Y")
            except (ValueError, TypeError):
                key = "Unknown"
            groups.setdefault(key, []).append(event.to_dict())
        return [{"month": k, "events": v} for k, v in groups.items()]
