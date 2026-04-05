from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.db.enums import (
    DocumentStatus,
    WorkflowState,
    DocumentType,
    MalwareScanStatus,
)
from app.models.document import Document, DocumentActivity
from app.models.user import User
from app.services.audit_service import AuditService
from app.services.file_parser import parse_file
from app.services.malware_service import MalwareScanner
from app.services.notification_service import NotificationService
from app.services.paperwork_intelligence import analyze_phase1_document, generate_letter_for_document
from app.services.reminder_service import ReminderService
from app.services.storage_service import StorageService

import hashlib
from fastapi import HTTPException


class DocumentService:
    def __init__(self) -> None:
        self.storage = StorageService()
        self.notifications = NotificationService()
        self.malware = MalwareScanner()
        self.reminders = ReminderService()
        self.audit = AuditService()

    def create_pending_document(
        self,
        db: Session,
        owner_id: int,
        filename: str,
        mime_type: str,
        storage_key: str,
    ) -> Document:
        document = Document(
            owner_id=owner_id,
            name=filename,
            mime_type=mime_type,
            storage_key=storage_key,
            status=DocumentStatus.UPLOADED,
            workflow_state=WorkflowState.NEW,  # ✅ FIXED
        )
        db.add(document)
        db.commit()
        db.refresh(document)
        return document

    def mark_processing(self, db: Session, document: Document, job_id: str) -> Document:
        document.status = DocumentStatus.PROCESSING
        document.processing_job_id = job_id
        db.add(document)
        db.commit()
        db.refresh(document)
        return document

    def _activity(
        self,
        db: Session,
        document_id: int,
        actor_user_id: int | None,
        activity_type: str,
        payload: dict | None = None,
    ) -> None:
        db.add(
            DocumentActivity(
                document_id=document_id,
                actor_user_id=actor_user_id,
                activity_type=activity_type,
                payload=payload or {},
            )
        )
        db.commit()

    def process_document(self, db: Session, document: Document) -> Document:
        raw = self.storage.download_bytes(document.storage_key)

        # 🔥 MALWARE FIX
        malware_scan = self.malware.scan_bytes(raw)

        try:
            document.malware_scan_status = MalwareScanStatus(malware_scan["status"])
        except ValueError:
            document.malware_scan_status = MalwareScanStatus.FAILED

        document.malware_scan_result = malware_scan.get("result") or {}

        if document.malware_scan_status == MalwareScanStatus.INFECTED:
            document.status = DocumentStatus.QUARANTINED
            db.add(document)
            db.commit()

            self.notifications.create(
                db,
                document.owner_id,
                "Document blocked",
                f"{document.name} was quarantined by malware scanning.",
            )

            self.audit.log(
                db,
                action="document.quarantined",
                user_id=document.owner_id,
                entity_type="document",
                entity_id=str(document.id),
                detail={"malware_scan_result": document.malware_scan_result},
            )

            self._activity(
                db,
                document.id,
                document.owner_id,
                "document_quarantined",
                {"malware_scan_result": document.malware_scan_result},
            )

            return document

        parsed = parse_file(raw, document.mime_type, document.name)

        phase1 = analyze_phase1_document(parsed["text"], document.name)

        deadlines = phase1.get("deadlines", [])
        recommendations = phase1.get("recommendations", [])

        letter = phase1.get("letter") or generate_letter_for_document(
            phase1.get("document_type") or "unknown",
            phase1.get("extracted_fields") or {},
            recommendations,
            parsed["text"],
        )

        document.extracted_text = parsed["text"]
        document.summary = phase1.get("summary")
        document.deadlines = deadlines

        # 🔥 FIXED ENUM
        document.document_type = DocumentType(
            phase1.get("document_type") or "unknown"
        )

        document.document_type_confidence = phase1.get("document_type_confidence")
        document.extracted_fields = phase1.get("extracted_fields", {})
        document.recommended_actions = recommendations
        document.generated_letter = letter
        document.has_ocr = parsed["used_ocr"]
        document.status = DocumentStatus.COMPLETED

        document.processing_metadata = {
            "parser": parsed.get("parser"),
            "used_ocr": parsed.get("used_ocr"),
            "analyzer": phase1.get("analyzer", "rules_v1"),
        }

        db.add(document)
        db.commit()
        db.refresh(document)

        self.reminders.sync_from_deadlines(
            db,
            user_id=document.owner_id,
            document_id=document.id,
            deadlines=deadlines,
        )

        self.notifications.create(
            db,
            document.owner_id,
            "Document processed",
            f"{document.name} is ready to review.",
            payload={"document_id": document.id},
        )

        owner = db.query(User).filter(User.id == document.owner_id).first()
        if owner:
            self.notifications.send_push_if_available(
                owner,
                "Document processed",
                f"{document.name} is ready to review.",
            )

        self.audit.log(
            db,
            action="document.processed",
            user_id=document.owner_id,
            entity_type="document",
            entity_id=str(document.id),
            detail={
                "document_type": str(document.document_type),
                "malware_scan_status": str(document.malware_scan_status),
            },
        )

        self._activity(
            db,
            document.id,
            document.owner_id,
            "document_processed",
            {"document_type": str(document.document_type)},
        )

        return document

    def _sha256_bytes(self, content: bytes) -> str:
        return hashlib.sha256(content).hexdigest()

    def find_duplicate_document(
        self,
        db: Session,
        owner_id: int,
        checksum_sha256: str,
        exclude_document_id: int | None = None,
    ) -> Document | None:
        query = db.query(Document).filter(
            Document.owner_id == owner_id,
            Document.checksum_sha256 == checksum_sha256,
        )

        if exclude_document_id is not None:
            query = query.filter(Document.id != exclude_document_id)

        return query.first()

    def validate_not_duplicate(self, db: Session, document: Document) -> Document:
        try:
            raw = self.storage.download_bytes(document.storage_key)
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to read uploaded file: {str(e)}",
            )

        checksum = self._sha256_bytes(raw)

        duplicate = (
            db.query(Document)
            .filter(
                Document.owner_id == document.owner_id,
                Document.checksum_sha256 == checksum,
                Document.id != document.id,
            )
            .first()
        )

        if duplicate:
            raise HTTPException(
                status_code=409,
                detail={"message": "Document already uploaded"},
            )

        document.checksum_sha256 = checksum
        db.add(document)
        db.commit()
        db.refresh(document)

        return document

    def create_version_snapshot(
        self,
        db: Session,
        document: Document,
        created_by_user_id: int | None = None,
    ):
        from app.models.document import DocumentVersion

        version = DocumentVersion(
            document_id=document.id,
            version_number=document.version_number,
            summary=document.summary,
            deadlines=document.deadlines or [],
            document_type=document.document_type or DocumentType.UNKNOWN,  # ✅ FIXED
            document_type_confidence=float(document.document_type_confidence)
            if document.document_type_confidence is not None
            else None,
            extracted_fields=document.extracted_fields or {},
            recommended_actions=document.recommended_actions or [],
            generated_letter=document.generated_letter or {},
            storage_key=document.storage_key,
            created_by_user_id=created_by_user_id,
        )

        db.add(version)
        db.commit()
        db.refresh(version)

        return version

    def delete_document_record(self, db: Session, document: Document) -> None:
        db.delete(document)
        db.commit()

    def complete_upload_with_fallback(
        self,
        db: Session,
        document: Document,
        process_callable,
    ) -> tuple[str, str | None]:
        self.validate_not_duplicate(db, document)
        self.create_version_snapshot(db, document, document.owner_id)

        document.version_number += 1
        db.add(document)
        db.commit()
        db.refresh(document)

        try:
            task = process_callable(document.id)
            task_id = getattr(task, "id", None)
            self.mark_processing(db, document, task_id or "local-processing")
            return "processing", task_id

        except Exception:
            self.mark_processing(db, document, "local-processing")
            try:
                self.process_document(db, document)
                return "completed", "local-processing"
            except Exception as exc:
                document.status = DocumentStatus.FAILED
                document.processing_metadata = {
                    **(document.processing_metadata or {}),
                    "error": str(exc),
                    "mode": "local-processing",
                }
                db.add(document)
                db.commit()
                db.refresh(document)
                raise