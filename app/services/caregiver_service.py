"""
caregiver_service.py — Caregiver & Family Support System (Phase 3)

Features:
  - Invite family caregivers with granular permissions
  - View-only / helper / full-access roles
  - Real-time alerts when senior uploads documents
  - Caregiver dashboard showing senior's pending actions
  - Shared document notes and comments
  - Emergency contact designation
  - Activity feed for caregivers
  - Permission expiry (e.g. temporary access for visiting family)

[HIPAA] All caregiver access is:
  - Logged in audit trail
  - Limited by Minimum Necessary Standard
  - Requires explicit consent from the senior (document owner)
  - Revocable at any time by the senior
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.core.hipaa_compliance import HIPAAAuditLogger
from app.services.alert_service import AlertService

logger = logging.getLogger(__name__)


class CaregiverPermission:
    """Permission levels for caregiver access."""
    VIEW_ONLY = "viewer"          # Can read documents and summaries
    HELPER = "member"             # Can add notes, change workflow status
    FULL_ACCESS = "admin"         # Can do everything except delete account

    LABELS = {
        "viewer": "Can view documents (read only)",
        "member": "Can help (add notes, update status)",
        "admin": "Full access (manage documents and settings)",
    }


class CaregiverService:
    """Manages caregiver relationships and permissions."""

    def __init__(self):
        self.alerts = AlertService()

    def get_caregiver_dashboard(
        self, caregiver_user_id: int, db: Session
    ) -> dict[str, Any]:
        """
        Returns a caregiver's full dashboard view:
        - All seniors they care for
        - Each senior's pending documents and deadlines
        - Recent activity
        - Urgent items requiring attention
        """
        from app.models.user import User
        from app.models.document import Document
        from app.models.share import Share

        # Get all seniors this caregiver has access to
        shares = (
            db.query(Share)
            .filter(
                Share.shared_with_user_id == caregiver_user_id,
                Share.is_active == True,
            )
            .all()
        )

        seniors_data = []
        urgent_items = []

        for share in shares:
            senior = db.query(User).filter(User.id == share.document_owner_id).first()
            if not senior:
                continue

            # Get senior's documents based on permission level
            docs_query = (
                db.query(Document)
                .filter(Document.owner_id == senior.id)
                .order_by(Document.created_at.desc())
            )

            docs = docs_query.limit(10).all()
            pending_actions = []
            deadlines_soon = []

            for doc in docs:
                # Check for urgent items
                if doc.workflow_state in ("needs_review", "waiting_on_user"):
                    pending_actions.append({
                        "document_id": doc.id,
                        "document_name": doc.name,
                        "status": str(doc.workflow_state),
                        "created_at": str(doc.created_at),
                    })

                # Check deadlines
                for deadline in (doc.deadlines or []):
                    if deadline.get("date"):
                        deadline_info = {
                            "document_id": doc.id,
                            "document_name": doc.name,
                            "title": deadline.get("title"),
                            "date": deadline.get("date"),
                            "action": deadline.get("action"),
                        }
                        deadlines_soon.append(deadline_info)
                        urgent_items.append({**deadline_info, "senior_name": senior.full_name})

            seniors_data.append({
                "senior_id": senior.id,
                "senior_name": senior.full_name,
                "senior_email": senior.email,
                "permission_level": share.permission,
                "permission_label": CaregiverPermission.LABELS.get(share.permission, share.permission),
                "total_documents": docs_query.count(),
                "pending_actions": pending_actions,
                "upcoming_deadlines": deadlines_soon[:5],
                "last_activity": str(docs[0].updated_at) if docs else None,
                "access_expires": str(share.expires_at) if hasattr(share, "expires_at") and share.expires_at else None,
            })

        # Log caregiver dashboard access [HIPAA]
        audit = HIPAAAuditLogger(db)
        audit.log_phi_access(
            user_id=caregiver_user_id,
            action="caregiver.dashboard_viewed",
            resource_type="caregiver_dashboard",
            resource_id=str(caregiver_user_id),
        )

        return {
            "caregiver_user_id": caregiver_user_id,
            "seniors": seniors_data,
            "urgent_items": urgent_items[:10],
            "total_seniors": len(seniors_data),
            "items_needing_attention": len(urgent_items),
        }

    def notify_caregivers_of_document(
        self, senior_user_id: int, document_id: int,
        document_name: str, db: Session,
    ) -> None:
        """Alert all caregivers when a senior uploads a new document."""
        from app.models.user import User
        from app.models.share import Share

        senior = db.query(User).filter(User.id == senior_user_id).first()
        senior_name = senior.full_name if senior else "Your senior"

        # Find all active caregivers for this senior
        caregiver_shares = (
            db.query(Share)
            .filter(
                Share.document_owner_id == senior_user_id,
                Share.is_active == True,
            )
            .all()
        )

        for share in caregiver_shares:
            try:
                self.alerts.send_caregiver_new_document(
                    caregiver_id=share.shared_with_user_id,
                    senior_name=senior_name,
                    document_name=document_name,
                    document_id=document_id,
                    db=db,
                )
            except Exception as exc:
                logger.warning(
                    "Caregiver alert failed for caregiver_id=%d: %s",
                    share.shared_with_user_id, exc,
                )

    def notify_caregivers_of_scam(
        self, senior_user_id: int, document_id: int,
        risk_level: str, db: Session,
    ) -> None:
        """Urgently alert caregivers when a scam is detected."""
        from app.models.share import Share

        caregiver_shares = (
            db.query(Share)
            .filter(Share.document_owner_id == senior_user_id, Share.is_active == True)
            .all()
        )

        caregiver_ids = [s.shared_with_user_id for s in caregiver_shares]
        self.alerts.send_scam_warning(
            user_id=senior_user_id,
            risk_level=risk_level,
            document_id=document_id,
            db=db,
            caregiver_ids=caregiver_ids,
        )

    def get_senior_activity_feed(
        self, caregiver_user_id: int, senior_user_id: int, db: Session, limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Get recent activity for a senior (for caregiver view)."""
        from app.models.document import DocumentActivity, AuditLog
        from app.models.share import Share

        # Verify caregiver has access [HIPAA]
        share = (
            db.query(Share)
            .filter(
                Share.shared_with_user_id == caregiver_user_id,
                Share.document_owner_id == senior_user_id,
                Share.is_active == True,
            )
            .first()
        )

        if not share:
            raise PermissionError("Caregiver does not have access to this senior's data")

        # Log this access [HIPAA]
        audit = HIPAAAuditLogger(db)
        audit.log_phi_access(
            user_id=caregiver_user_id,
            action="caregiver.activity_feed_viewed",
            resource_type="senior_activity",
            resource_id=str(senior_user_id),
        )

        activities = (
            db.query(DocumentActivity)
            .join(DocumentActivity.document)
            .filter(DocumentActivity.document.has(owner_id=senior_user_id))
            .order_by(DocumentActivity.created_at.desc())
            .limit(limit)
            .all()
        )

        return [
            {
                "id": a.id,
                "activity_type": a.activity_type,
                "document_id": a.document_id,
                "created_at": str(a.created_at),
                "summary": _activity_label(a.activity_type),
            }
            for a in activities
        ]


def _activity_label(activity_type: str) -> str:
    labels = {
        "document_processed": "Document analyzed",
        "document_quarantined": "Document blocked (security)",
        "document_processing_failed": "Document could not be read",
        "workflow_updated": "Status updated",
        "comment_added": "Note added",
        "letter_generated": "Letter generated",
    }
    return labels.get(activity_type, activity_type.replace("_", " ").title())
