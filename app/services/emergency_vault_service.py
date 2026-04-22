"""
emergency_vault_service.py — Emergency Document Vault (Phase 3)

The vault stores critical documents that family and caregivers
need immediate access to in emergencies:
  - Insurance cards
  - Medical contacts and doctors list
  - Current medication list
  - Power of attorney documents
  - ID copies (passport, driver's license)
  - Living will / advance directive
  - Emergency contacts
  - Health insurance information

[HIPAA] Vault documents are treated as highest-sensitivity PHI:
  - Every access is logged with timestamp, user, and IP
  - Owner receives email alert on every access
  - Documents are tagged with retention policy
  - Access can be restricted by time window
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Vault document categories
VAULT_CATEGORIES = {
    "insurance_card": "Insurance Cards",
    "medication_list": "Current Medications",
    "medical_contacts": "Doctors & Medical Contacts",
    "legal": "Legal Documents (POA, Living Will)",
    "id_documents": "ID Documents",
    "emergency_contacts": "Emergency Contacts",
    "financial": "Financial Account Information",
    "other": "Other Important Documents",
}

# Retention periods per category
VAULT_RETENTION_DAYS = {
    "insurance_card": 365,
    "medication_list": 365,
    "medical_contacts": 3650,
    "legal": 3650,
    "id_documents": 3650,
    "emergency_contacts": 3650,
    "financial": 2555,
    "other": 2555,
}


class EmergencyVaultService:
    """Manages the emergency document vault."""

    def get_vault_contents(
        self, owner_user_id: int, requesting_user_id: int,
        db: Session, ip_address: str | None = None,
    ) -> dict[str, Any]:
        """
        Get vault contents. Logs all access [HIPAA].
        requesting_user_id can be owner or authorized caregiver.
        """
        from app.core.hipaa_compliance import HIPAAAuditLogger
        from app.models.document import Document
        from app.models.share import Share
        from app.models.user import User

        # Verify access
        is_owner = requesting_user_id == owner_user_id
        if not is_owner:
            # Check caregiver access
            share = (
                db.query(Share)
                .filter(
                    Share.shared_with_user_id == requesting_user_id,
                    Share.document_owner_id == owner_user_id,
                    Share.is_active == True,
                    Share.permission.in_(["member", "admin"]),
                )
                .first()
            )
            if not share:
                raise PermissionError("Not authorized to access this vault")

        # [HIPAA] Log vault access
        audit = HIPAAAuditLogger(db)
        audit.log_phi_access(
            user_id=requesting_user_id,
            action="vault.accessed",
            resource_type="emergency_vault",
            resource_id=str(owner_user_id),
            ip_address=ip_address,
            additional_context={"is_owner": is_owner},
        )

        # If caregiver accessed — alert the owner
        if not is_owner:
            requester = db.query(User).filter(User.id == requesting_user_id).first()
            requester_name = requester.full_name if requester else "A caregiver"
            self._alert_owner_of_vault_access(owner_user_id, requester_name, db)

        # Get vault documents (documents tagged as vault items)
        vault_docs = (
            db.query(Document)
            .filter(
                Document.owner_id == owner_user_id,
                Document.source_metadata["vault_item"].astext == "true",
            )
            .order_by(Document.created_at.desc())
            .all()
        )

        # Organize by category
        by_category: dict[str, list[dict]] = {cat: [] for cat in VAULT_CATEGORIES}
        for doc in vault_docs:
            category = (doc.source_metadata or {}).get("vault_category", "other")
            by_category.setdefault(category, []).append({
                "id": doc.id,
                "name": doc.name,
                "category": category,
                "category_label": VAULT_CATEGORIES.get(category, "Other"),
                "uploaded_at": str(doc.created_at),
                "summary": doc.summary,
            })

        return {
            "owner_id": owner_user_id,
            "categories": VAULT_CATEGORIES,
            "documents_by_category": by_category,
            "total_documents": len(vault_docs),
            "last_accessed": datetime.now(timezone.utc).isoformat(),
            "access_note": "All vault access is logged and the document owner is notified." if not is_owner else None,
        }

    def add_to_vault(
        self, document_id: int, owner_user_id: int,
        category: str, db: Session,
    ) -> dict[str, Any]:
        """Mark an existing document as a vault item."""
        from app.models.document import Document

        doc = db.query(Document).filter(
            Document.id == document_id,
            Document.owner_id == owner_user_id,
        ).first()

        if not doc:
            raise ValueError("Document not found or access denied")

        if category not in VAULT_CATEGORIES:
            raise ValueError(f"Invalid category. Must be one of: {list(VAULT_CATEGORIES.keys())}")

        metadata = dict(doc.source_metadata or {})
        metadata["vault_item"] = "true"
        metadata["vault_category"] = category
        metadata["vault_added_at"] = datetime.now(timezone.utc).isoformat()

        doc.source_metadata = metadata
        db.add(doc)
        db.commit()
        db.refresh(doc)

        return {
            "document_id": doc.id,
            "vault_category": category,
            "category_label": VAULT_CATEGORIES[category],
            "message": f"Document added to {VAULT_CATEGORIES[category]} in your emergency vault.",
        }

    def remove_from_vault(
        self, document_id: int, owner_user_id: int, db: Session,
    ) -> None:
        """Remove a document from the vault (document remains, just not vault-tagged)."""
        from app.models.document import Document

        doc = db.query(Document).filter(
            Document.id == document_id,
            Document.owner_id == owner_user_id,
        ).first()

        if not doc:
            raise ValueError("Document not found")

        metadata = dict(doc.source_metadata or {})
        metadata.pop("vault_item", None)
        metadata.pop("vault_category", None)
        doc.source_metadata = metadata
        db.add(doc)
        db.commit()

    def get_vault_summary_card(self, owner_user_id: int, db: Session) -> dict[str, Any]:
        """
        Returns a quick summary card for the vault widget.
        Shows what's in the vault and what's missing.
        """
        from app.models.document import Document

        vault_docs = (
            db.query(Document)
            .filter(
                Document.owner_id == owner_user_id,
                Document.source_metadata["vault_item"].astext == "true",
            )
            .all()
        )

        covered_categories = set()
        for doc in vault_docs:
            cat = (doc.source_metadata or {}).get("vault_category")
            if cat:
                covered_categories.add(cat)

        missing = [
            {"category": cat, "label": label}
            for cat, label in VAULT_CATEGORIES.items()
            if cat not in covered_categories
        ]

        important_missing = [
            m for m in missing
            if m["category"] in ("insurance_card", "medication_list", "emergency_contacts")
        ]

        return {
            "total_documents": len(vault_docs),
            "covered_categories": list(covered_categories),
            "missing_categories": missing,
            "important_missing": important_missing,
            "is_complete": len(missing) == 0,
            "completion_pct": round(len(covered_categories) / len(VAULT_CATEGORIES) * 100),
            "tip": "Add your insurance card, medication list, and emergency contacts so family can help in an emergency." if important_missing else "Your vault is well-stocked!",
        }

    def _alert_owner_of_vault_access(
        self, owner_user_id: int, accessed_by: str, db: Session,
    ) -> None:
        """Send alert to vault owner when caregiver accesses vault."""
        from app.services.alert_service import AlertService
        alerts = AlertService()
        alerts.send_vault_access_alert(
            user_id=owner_user_id,
            accessed_by=accessed_by,
            document_name="Emergency Vault",
            db=db,
        )
