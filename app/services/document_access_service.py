from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.share import Share
from app.models.user import User


class DocumentAccessService:
    def get_share(self, db: Session, document_id: int, email: str) -> Share | None:
        return db.query(Share).filter(Share.document_id == document_id, Share.shared_with_email == email).first()

    def get_access_level(self, db: Session, document: Document, user: User) -> str | None:
        if document.owner_id == user.id:
            return 'owner'
        share = self.get_share(db, document.id, user.email)
        return share.permission if share else None

    def assert_can_view(self, db: Session, document: Document | None, user: User) -> Document:
        if not document:
            raise HTTPException(status_code=404, detail='Document not found')
        access = self.get_access_level(db, document, user)
        if not access and user.role != 'admin':
            raise HTTPException(status_code=404, detail='Document not found')
        return document

    def assert_can_edit(self, db: Session, document: Document | None, user: User) -> Document:
        document = self.assert_can_view(db, document, user)
        access = self.get_access_level(db, document, user)
        if user.role == 'admin':
            return document
        if access not in {'owner', 'editor'}:
            raise HTTPException(status_code=403, detail='You do not have edit access to this document')
        return document

    def serialize_document(self, db: Session, document: Document, user: User) -> dict:
        access_level = self.get_access_level(db, document, user) or ('admin' if user.role == 'admin' else 'none')
        return {
            'id': document.id,
            'name': document.name,
            'mime_type': document.mime_type,
            'status': str(document.status),
            'processing_job_id': document.processing_job_id,
            'summary': document.summary,
            'deadlines': document.deadlines or [],
            'document_type': str(document.document_type or 'unknown'),
            'document_type_confidence': float(document.document_type_confidence) if document.document_type_confidence is not None else None,
            'extracted_fields': document.extracted_fields or {},
            'recommended_actions': document.recommended_actions or [],
            'generated_letter': document.generated_letter or {},
            'has_ocr': document.has_ocr,
            'created_at': document.created_at,
            'access_level': access_level,
            'workflow_state': str(document.workflow_state),
            'version_number': document.version_number,
            'assigned_to_user_id': document.assigned_to_user_id,
            'assigned_to_user_name': document.assignee.full_name if getattr(document, 'assignee', None) else None,
        }
