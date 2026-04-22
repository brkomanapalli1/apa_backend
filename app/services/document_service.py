"""
DocumentService — full document lifecycle.
Pipeline: upload → malware scan → OCR/parse → AI analysis → notify → remind

All original features preserved + HIPAA audit + all 27 bill types via bill_intelligence.
"""
from __future__ import annotations
import hashlib, logging
from typing import Any
from fastapi import HTTPException
from sqlalchemy.orm import Session
from app.core.config import settings
from app.db.enums import DocumentStatus, DocumentType, MalwareScanStatus, WorkflowState
from app.models.document import Document, DocumentActivity
from app.models.user import User
from app.services.audit_service import AuditService
from app.services.bill_intelligence import analyze_document, build_letter
from app.services.file_parser import parse_file
from app.services.malware_service import MalwareScanner
from app.services.notification_service import NotificationService
from app.services.reminder_service import ReminderService
from app.services.storage_service import StorageService

logger = logging.getLogger(__name__)


class DocumentService:
    def __init__(self) -> None:
        self.storage = StorageService()
        self.notifications = NotificationService()
        self.malware = MalwareScanner()
        self.reminders = ReminderService()
        self.audit = AuditService()

    def create_pending_document(self, db, owner_id, filename, mime_type, storage_key):
        doc = Document(owner_id=owner_id, name=filename, mime_type=mime_type,
                       storage_key=storage_key, status=DocumentStatus.UPLOADED,
                       workflow_state=WorkflowState.NEW)
        db.add(doc); db.commit(); db.refresh(doc)
        logger.info("Created document id=%d name=%s owner=%d", doc.id, filename, owner_id)
        return doc

    def mark_processing(self, db, document, job_id):
        document.status = DocumentStatus.PROCESSING
        document.processing_job_id = job_id
        db.add(document); db.commit(); db.refresh(document)
        return document

    def process_document(self, db: Session, document: Document) -> Document:
        # 1 — Download
        try:
            raw = self.storage.download_bytes(document.storage_key)
        except Exception as exc:
            logger.error("Storage download failed doc=%d: %s", document.id, exc)
            return self._fail(db, document, "storage_download_failed", str(exc))

        # 2 — Malware scan
        scan = self.malware.scan_bytes(raw)
        try:
            document.malware_scan_status = MalwareScanStatus(scan["status"])
        except ValueError:
            document.malware_scan_status = MalwareScanStatus.FAILED
        document.malware_scan_result = scan.get("result") or {}
        if document.malware_scan_status == MalwareScanStatus.INFECTED:
            return self._quarantine(db, document)

        # 3 — Parse / OCR
        parsed = parse_file(raw, document.mime_type, document.name)
        text = (parsed.get("text") or "").strip()
        logger.debug("Parsed doc=%d parser=%s ocr=%s len=%d", document.id,
                     parsed.get("parser"), parsed.get("used_ocr"), len(text))
        if not text or text == "No extractable text found.":
            return self._fail(db, document, "no_extractable_text", parsed_meta=parsed)

        # 4 — AI analysis (bill_intelligence + optional LLM overlay)
        try:
            # Try LLM first, merge over heuristic result
            from app.services.llm_service import analyze_document_with_llm
            heuristic = analyze_document(text, document.name)
            llm_result = analyze_document_with_llm(text, document.name)
            if llm_result:
                # LLM wins for everything — summary, letter, deadlines, medications
                phase1 = {**heuristic, **llm_result}

                # Merge extracted_fields: LLM fields win, but add heuristic ui_summary
                # only if LLM didn't provide a better one
                merged_fields = {**heuristic.get("extracted_fields", {}),
                                 **llm_result.get("extracted_fields", {})}

                # Build a clean ui_summary from LLM data, not heuristic
                # This prevents DOB being used as key date
                llm_deadlines = llm_result.get("deadlines") or []
                llm_fields = llm_result.get("extracted_fields") or {}
                doc_type = llm_result.get("document_type", "unknown")

                # Get best key date from LLM deadlines (skip DOB)
                dob = llm_fields.get("date_of_birth", "")
                key_date = None
                for dl in llm_deadlines:
                    dl_date = dl.get("date", "")
                    if dl_date and dl_date != dob and "birth" not in dl.get("title","").lower():
                        key_date = dl_date
                        break

                # Get heuristic ui_summary as base then fix key date
                h_ui = heuristic.get("extracted_fields", {}).get("ui_summary", {})
                if h_ui:
                    h_ui["main_due_date"] = key_date  # replace DOB with real date
                    if dob and h_ui.get("main_due_date") == dob:
                        h_ui["main_due_date"] = None
                    # Fix what_this_is using LLM summary
                    if llm_result.get("summary"):
                        h_ui["what_this_is"] = llm_result["summary"]

                merged_fields["ui_summary"] = h_ui

                # Keep medications from LLM
                if llm_result.get("extracted_fields", {}).get("medications"):
                    merged_fields["medications"] = llm_result["extracted_fields"]["medications"]

                phase1["extracted_fields"] = merged_fields
                phase1["analyzer"] = llm_result.get("analyzer", "llm+rules_v3")
            else:
                phase1 = heuristic
        except Exception as exc:
            logger.error("Analysis error doc=%d: %s", document.id, exc, exc_info=True)
            phase1 = {"document_type": "unknown", "document_type_confidence": 0.0,
                      "summary": "Document uploaded but analysis encountered an error.",
                      "extracted_fields": {}, "deadlines": [], "recommendations": [],
                      "letter": {}, "analyzer": "error_fallback"}

        # 5 — Persist
        return self._persist(db, document, phase1, parsed)

    def _persist(self, db, document, phase1, parsed):
        deadlines = phase1.get("deadlines") or []
        recs = phase1.get("recommendations") or []
        fields = phase1.get("extracted_fields") or {}
        doc_type = phase1.get("document_type") or "unknown"
        letter = phase1.get("letter") or build_letter(doc_type, fields)

        try:
            document.document_type = DocumentType(doc_type)
        except ValueError:
            document.document_type = DocumentType.UNKNOWN

        raw_text = (parsed.get("text") or "")[:50_000]
        document.extracted_text = raw_text
        document.summary = phase1.get("summary")
        document.deadlines = deadlines
        document.document_type_confidence = phase1.get("document_type_confidence")
        # Save medications from Claude into extracted_fields so frontend can display them
        medications = phase1.get("medications") or []
        if medications:
            fields["medications"] = medications

        document.extracted_fields = fields
        document.recommended_actions = recs
        document.generated_letter = letter
        document.has_ocr = parsed.get("used_ocr", False)
        document.status = DocumentStatus.PROCESSED
        document.workflow_state = WorkflowState.NEEDS_REVIEW if deadlines else WorkflowState.NEW
        document.processing_metadata = {
            "parser": parsed.get("parser"), "used_ocr": parsed.get("used_ocr"),
            "analyzer": phase1.get("analyzer", "rules_v3"),
            "text_length": len(raw_text),
            "billing_errors_found": len(phase1.get("billing_errors") or []),
        }
        db.add(document); db.commit(); db.refresh(document)

        self._activity(db, document.id, document.owner_id, "document_processed",
                       {"document_type": str(document.document_type), "analyzer": phase1.get("analyzer")})
        self.audit.log(db, action="document.processed", user_id=document.owner_id,
                       entity_type="document", entity_id=str(document.id),
                       detail={"document_type": str(document.document_type),
                               "malware_scan_status": str(document.malware_scan_status)})

        # Post-process: reminders, notifications, push, medication reminders
        medications = phase1.get("medications") or []
        self._post(db, document, deadlines, medications)
        return document

    def _quarantine(self, db, document):
        document.status = DocumentStatus.QUARANTINED
        db.add(document); db.commit()
        self.notifications.create(db, document.owner_id, "Document blocked",
                                  f"{document.name} was blocked by security scanning.")
        self.audit.log(db, action="document.quarantined", user_id=document.owner_id,
                       entity_type="document", entity_id=str(document.id),
                       detail={"malware_scan_result": document.malware_scan_result})
        self._activity(db, document.id, document.owner_id, "document_quarantined", {})
        logger.warning("Document %d quarantined", document.id)
        return document

    def _fail(self, db, document, reason, error=None, parsed_meta=None):
        document.status = DocumentStatus.FAILED
        document.summary = ("We could not extract readable text from this document. "
                            "Please try uploading a clearer PDF or image.")
        document.deadlines = []; document.document_type = DocumentType.UNKNOWN
        document.document_type_confidence = None; document.extracted_fields = {}
        document.recommended_actions = [{"title": "Upload a clearer file",
            "why": "The document text could not be read.",
            "action": "Try a higher-quality scan or PDF. Ensure pages are not rotated.",
            "priority": "high"}]
        document.generated_letter = {}
        document.has_ocr = (parsed_meta or {}).get("used_ocr", False)
        document.processing_metadata = {"parser": (parsed_meta or {}).get("parser"),
            "used_ocr": (parsed_meta or {}).get("used_ocr"),
            "error": reason, "error_detail": error}
        db.add(document); db.commit(); db.refresh(document)
        self.notifications.create(db, document.owner_id, "Document needs attention",
                                  f"We could not read {document.name}. Please upload a clearer file.",
                                  payload={"document_id": document.id})
        self.audit.log(db, action="document.processing_failed", user_id=document.owner_id,
                       entity_type="document", entity_id=str(document.id),
                       detail={"reason": reason, "error": error})
        self._activity(db, document.id, document.owner_id, "document_processing_failed", {"reason": reason})
        logger.warning("Document %d failed: %s", document.id, reason)
        return document

    def _post(self, db, document, deadlines, medications=None):
        for fn, label in [
            (lambda: self.reminders.sync_from_deadlines(db, user_id=document.owner_id,
                document_id=document.id, deadlines=deadlines), "reminders"),
            (lambda: self.notifications.create(db, document.owner_id, "Document ready",
                f"{document.name} has been analyzed.",
                payload={"document_id": document.id}), "notification"),
        ]:
            try:
                fn()
            except Exception as exc:
                logger.warning("%s failed for doc=%d: %s", label, document.id, exc)

        # Create medication reminders if prescriptions were found
        if medications:
            try:
                self._create_medication_reminders(db, document, medications)
            except Exception as exc:
                logger.warning("Medication reminders failed for doc=%d: %s", document.id, exc)

        try:
            owner = db.get(User, document.owner_id)
            if owner:
                med_count = len(medications) if medications else 0
                msg = f"{document.name} is ready."
                if med_count:
                    msg += f" {med_count} medication(s) found."
                self.notifications.send_push_if_available(owner, "Document ready", msg)
        except Exception as exc:
            logger.warning("Push failed for doc=%d: %s", document.id, exc)

    def _create_medication_reminders(self, db, document, medications):
        """Create daily reminders for each medication found in the document."""
        from app.models.document import Reminder
        from datetime import datetime, timezone

        for med in medications or []:
            name = med.get("name", "Medication")
            dosage = med.get("dosage", "")
            instructions = med.get("instructions", "")
            reminder_times = med.get("reminder_times") or []
            refill_date = med.get("refill_date")

            # Create a reminder for each dose time
            if reminder_times:
                for t in reminder_times:
                    title = f"Take {name} {dosage}".strip()
                    existing = db.query(Reminder).filter(
                        Reminder.user_id == document.owner_id,
                        Reminder.document_id == document.id,
                        Reminder.title == title,
                    ).first()
                    if not existing:
                        db.add(Reminder(
                            user_id=document.owner_id,
                            document_id=document.id,
                            title=title,
                            due_at=None,  # medication reminders fire daily, not on a fixed date
                            payload={
                                "type": "medication",
                                "medication": name,
                                "dosage": dosage,
                                "instructions": instructions,
                                "reminder_time": t,
                            }
                        ))
            else:
                # No specific times — create one general reminder
                title = f"Take {name} {dosage}".strip()
                existing = db.query(Reminder).filter(
                    Reminder.user_id == document.owner_id,
                    Reminder.document_id == document.id,
                    Reminder.title == title,
                ).first()
                if not existing:
                    db.add(Reminder(
                        user_id=document.owner_id,
                        document_id=document.id,
                        title=title,
                        due_at=None,
                        payload={
                            "type": "medication",
                            "medication": name,
                            "dosage": dosage,
                            "instructions": instructions,
                        }
                    ))

            # Create a refill reminder if refill date exists
            if refill_date:
                refill_title = f"Refill {name}"
                parsed_refill = None
                try:
                    from app.services.reminder_service import ReminderService
                    parsed_refill = ReminderService._parse_date(refill_date)
                except Exception:
                    pass
                existing = db.query(Reminder).filter(
                    Reminder.user_id == document.owner_id,
                    Reminder.document_id == document.id,
                    Reminder.title == refill_title,
                ).first()
                if not existing:
                    db.add(Reminder(
                        user_id=document.owner_id,
                        document_id=document.id,
                        title=refill_title,
                        due_at=parsed_refill,
                        payload={"type": "medication_refill", "medication": name}
                    ))

        db.commit()
        logger.info("Created medication reminders for doc=%d (%d meds)", document.id, len(medications))

    @staticmethod
    def _sha256(content: bytes) -> str:
        return hashlib.sha256(content).hexdigest()

    def validate_not_duplicate(self, db, document):
        try:
            raw = self.storage.download_bytes(document.storage_key)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Failed to read uploaded file: {exc}") from exc
        checksum = self._sha256(raw)
        dup = (db.query(Document)
               .filter(Document.owner_id == document.owner_id,
                       Document.checksum_sha256 == checksum,
                       Document.id != document.id,
                       Document.status != DocumentStatus.QUARANTINED)
               .first())
        if dup:
            raise HTTPException(status_code=409, detail={
                "message": "This document has already been uploaded.",
                "existing_document_id": dup.id})
        document.checksum_sha256 = checksum
        db.add(document); db.commit(); db.refresh(document)
        return document

    def create_version_snapshot(self, db, document, created_by_user_id=None):
        from app.models.document import DocumentVersion
        v = DocumentVersion(
            document_id=document.id, version_number=document.version_number,
            summary=document.summary, deadlines=document.deadlines or [],
            document_type=document.document_type or DocumentType.UNKNOWN,
            document_type_confidence=(float(document.document_type_confidence)
                                      if document.document_type_confidence is not None else None),
            extracted_fields=document.extracted_fields or {},
            recommended_actions=document.recommended_actions or [],
            generated_letter=document.generated_letter or {},
            storage_key=document.storage_key, created_by_user_id=created_by_user_id)
        db.add(v); db.commit(); db.refresh(v)
        return v

    def complete_upload_with_fallback(self, db, document, process_callable):
        self.validate_not_duplicate(db, document)
        self.create_version_snapshot(db, document, document.owner_id)
        document.version_number += 1
        db.add(document); db.commit(); db.refresh(document)
        try:
            task = process_callable(document.id)
            task_id = getattr(task, "id", None)
            self.mark_processing(db, document, task_id or "queued")
            logger.info("Document %d queued (task=%s)", document.id, task_id)
            return "processing", task_id
        except Exception as exc:
            logger.warning("Celery unavailable doc=%d (%s) — processing sync", document.id, exc)
            self.mark_processing(db, document, "sync-processing")
            try:
                self.process_document(db, document)
                return "completed", "sync-processing"
            except Exception as sync_exc:
                document.status = DocumentStatus.FAILED
                document.processing_metadata = {**(document.processing_metadata or {}),
                    "error": str(sync_exc), "mode": "sync-processing"}
                db.add(document); db.commit(); db.refresh(document)
                raise

    def delete_document_record(self, db, document):
        db.delete(document); db.commit()

    def _activity(self, db, document_id, actor_user_id, activity_type, payload=None):
        try:
            db.add(DocumentActivity(document_id=document_id, actor_user_id=actor_user_id,
                                    activity_type=activity_type, payload=payload or {}))
            db.commit()
        except Exception as exc:
            logger.warning("Activity log failed %s doc=%d: %s", activity_type, document_id, exc)
            db.rollback()