from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_current_user, get_db
from app.models.document import AuditLog, Comment, Document, Notification
from app.models.user import User
from app.schemas.document import (
    ActivityItemResponse,
    AssignmentRequest,
    CommentRequest,
    CommentResponse,
    CompleteUploadRequest,
    DocumentResponse,
    DocumentVersionResponse,
    GeneratedLetterResponse,
    JobStatusResponse,
    LetterGenerationRequest,
    PresignedUploadRequest,
    PresignedUploadResponse,
    ShareRequest,
    WorkflowUpdateRequest,
)
from app.services.audit_service import AuditService
from app.services.document_access_service import DocumentAccessService
from app.services.document_service import DocumentService
from app.services.paperwork_intelligence import generate_letter_for_document
from app.services.file_parser import is_supported_upload, SUPPORTED_EXTENSIONS
from app.services.storage_service import StorageService
from app.worker.tasks import process_document_task

router = APIRouter()
service = DocumentService()
storage = StorageService()
audit = AuditService()
access = DocumentAccessService()


def _get_doc(db: Session, document_id: int) -> Document:
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail='Document not found')
    return doc


@router.get('', response_model=list[DocumentResponse])
def list_documents(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    docs = db.query(Document).order_by(Document.created_at.desc()).all()
    return [access.serialize_document(db, doc, current_user) for doc in docs if access.get_access_level(db, doc, current_user) or current_user.role == 'admin']


@router.post('/presigned-upload', response_model=PresignedUploadResponse)
def create_presigned_upload(payload: PresignedUploadRequest, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if not is_supported_upload(payload.filename, payload.mime_type):
        raise HTTPException(
            status_code=400,
            detail={
                'message': 'Unsupported file format',
                'supported_extensions': sorted(SUPPORTED_EXTENSIONS),
            },
        )
    upload_url, storage_key = storage.get_presigned_upload(payload.filename, payload.mime_type or 'application/octet-stream')
    document = service.create_pending_document(db, current_user.id, payload.filename, payload.mime_type, storage_key)
    audit.log(db, action='document.presigned_upload_created', user_id=current_user.id, entity_type='document', entity_id=str(document.id), detail={'filename': payload.filename}, ip_address=request.client.host if request.client else None, user_agent=request.headers.get('user-agent'), request_id=request.headers.get('x-request-id'))
    return PresignedUploadResponse(upload_url=upload_url, document_id=document.id, storage_key=storage_key, expires_in=settings.PRESIGNED_UPLOAD_EXPIRE_SECONDS, headers={'Content-Type': payload.mime_type})


@router.post('/complete-upload', response_model=JobStatusResponse)
def complete_upload(payload: CompleteUploadRequest, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    doc = access.assert_can_edit(db, _get_doc(db, payload.document_id), current_user)

    try:
        status, task_id = service.complete_upload_with_fallback(db, doc, lambda document_id: process_document_task.delay(document_id))
    except HTTPException:
        service.delete_document_record(db, doc)
        raise

    audit.log(
        db,
        action='document.processing_started',
        user_id=current_user.id,
        entity_type='document',
        entity_id=str(doc.id),
        detail={'task_id': task_id, 'status': status},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get('user-agent'),
        request_id=request.headers.get('x-request-id'),
    )

    return JobStatusResponse(document_id=doc.id, status=status, processing_job_id=task_id)

@router.delete('/{document_id}')
def delete_document(document_id: int, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    doc = access.assert_can_edit(db, _get_doc(db, document_id), current_user)

    # optional: delete object from storage
    try:
        storage.client.delete_object(Bucket=settings.MINIO_BUCKET, Key=doc.storage_key)
    except Exception:
        pass

    audit.log(
        db,
        action='document.deleted',
        user_id=current_user.id,
        entity_type='document',
        entity_id=str(document_id),
        detail={'name': doc.name},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get('user-agent'),
        request_id=request.headers.get('x-request-id'),
    )

    db.delete(doc)
    db.commit()
    return {'ok': True}

@router.get('/{document_id}', response_model=DocumentResponse)
def get_document(document_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    doc = access.assert_can_view(db, _get_doc(db, document_id), current_user)
    return access.serialize_document(db, doc, current_user)


@router.get('/{document_id}/status', response_model=JobStatusResponse)
def get_document_status(document_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    doc = access.assert_can_view(db, _get_doc(db, document_id), current_user)
    return JobStatusResponse(document_id=doc.id, status=str(doc.status), processing_job_id=doc.processing_job_id)


@router.get('/{document_id}/download-url')
def get_download_url(document_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    doc = access.assert_can_view(db, _get_doc(db, document_id), current_user)
    return {'url': storage.get_presigned_download(doc.storage_key)}


@router.post('/{document_id}/share')
def share_document(document_id: int, payload: ShareRequest, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    doc = access.assert_can_edit(db, _get_doc(db, document_id), current_user)
    if access.get_access_level(db, doc, current_user) != 'owner' and current_user.role != 'admin':
        raise HTTPException(status_code=403, detail='Only document owners can manage sharing')
    from app.models.share import Share

    share = db.query(Share).filter(Share.document_id == document_id, Share.shared_with_email == payload.email).first()
    if share:
        share.permission = payload.permission
    else:
        share = Share(document_id=document_id, shared_with_email=payload.email, permission=payload.permission, shared_by_user_id=current_user.id)
        db.add(share)
    db.commit()
    audit.log(db, action='document.share_updated', user_id=current_user.id, entity_type='document', entity_id=str(document_id), detail={'shared_with': payload.email, 'permission': payload.permission}, ip_address=request.client.host if request.client else None, user_agent=request.headers.get('user-agent'), request_id=request.headers.get('x-request-id'))
    return {'ok': True}


@router.get('/{document_id}/comments', response_model=list[CommentResponse])
def list_comments(document_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    doc = access.assert_can_view(db, _get_doc(db, document_id), current_user)
    comments = db.query(Comment).filter(Comment.document_id == doc.id).order_by(Comment.created_at.desc()).all()
    return [CommentResponse(id=item.id, document_id=item.document_id, user_id=item.user_id, user_name=item.user.full_name if item.user else None, body=item.body, mentions=item.mentions or [], created_at=item.created_at) for item in comments]


@router.post('/{document_id}/comments', response_model=CommentResponse)
def create_comment(document_id: int, payload: CommentRequest, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    doc = access.assert_can_view(db, _get_doc(db, document_id), current_user)
    mentioned = sorted({m.lower() for m in re.findall(r'@([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})', payload.body)})
    item = Comment(document_id=doc.id, user_id=current_user.id, body=payload.body, mentions=mentioned)
    db.add(item)
    db.commit()
    db.refresh(item)

    if mentioned:
        users = db.query(User).filter(User.email.in_(list(mentioned))).all()
        for user in users:
            db.add(Notification(user_id=user.id, title='You were mentioned in a document comment', body=f'{current_user.full_name} mentioned you in {doc.name}', channel='in_app', payload={'document_id': doc.id, 'type': 'mention'}))
        db.commit()

    audit.log(db, action='document.comment_created', user_id=current_user.id, entity_type='document', entity_id=str(document_id), detail={'body_preview': payload.body[:200], 'mentions': mentioned}, ip_address=request.client.host if request.client else None, user_agent=request.headers.get('user-agent'), request_id=request.headers.get('x-request-id'))
    return CommentResponse(id=item.id, document_id=item.document_id, user_id=item.user_id, user_name=current_user.full_name, body=item.body, mentions=item.mentions or [], created_at=item.created_at)


@router.get('/{document_id}/activity', response_model=list[ActivityItemResponse])
def activity(document_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    doc = access.assert_can_view(db, _get_doc(db, document_id), current_user)
    items = db.query(AuditLog).filter(AuditLog.entity_type == 'document', AuditLog.entity_id == str(doc.id)).order_by(AuditLog.created_at.desc()).limit(100).all()
    return [ActivityItemResponse(id=item.id, action=item.action, detail=item.detail, created_at=item.created_at, actor_name=item.user.full_name if item.user else None) for item in items]


@router.get('/{document_id}/versions', response_model=list[DocumentVersionResponse])
def versions(document_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    from app.models.document import DocumentVersion

    doc = access.assert_can_view(db, _get_doc(db, document_id), current_user)
    return db.query(DocumentVersion).filter(DocumentVersion.document_id == doc.id).order_by(DocumentVersion.version_number.desc()).all()


@router.post('/{document_id}/workflow', response_model=DocumentResponse)
def update_workflow(document_id: int, payload: WorkflowUpdateRequest, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    doc = access.assert_can_edit(db, _get_doc(db, document_id), current_user)
    doc.workflow_state = payload.workflow_state
    db.add(doc)
    db.commit()
    db.refresh(doc)
    audit.log(db, action='document.workflow_updated', user_id=current_user.id, entity_type='document', entity_id=str(document_id), detail={'workflow_state': payload.workflow_state}, ip_address=request.client.host if request.client else None, user_agent=request.headers.get('user-agent'), request_id=request.headers.get('x-request-id'))
    return access.serialize_document(db, doc, current_user)


@router.post('/{document_id}/assign', response_model=DocumentResponse)
def assign_document(document_id: int, payload: AssignmentRequest, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    doc = access.assert_can_edit(db, _get_doc(db, document_id), current_user)
    if payload.assigned_to_user_id is not None:
        assignee = db.query(User).filter(User.id == payload.assigned_to_user_id, User.is_active == True).first()
        if not assignee:
            raise HTTPException(status_code=404, detail='Assignee not found')
        doc.assigned_to_user_id = assignee.id
        detail = {'assigned_to': assignee.email}
    else:
        doc.assigned_to_user_id = None
        detail = {'assigned_to': None}
    db.add(doc)
    db.commit()
    db.refresh(doc)
    audit.log(db, action='document.assignment_updated', user_id=current_user.id, entity_type='document', entity_id=str(document_id), detail=detail, ip_address=request.client.host if request.client else None, user_agent=request.headers.get('user-agent'), request_id=request.headers.get('x-request-id'))
    return access.serialize_document(db, doc, current_user)


@router.post('/{document_id}/generate-letter', response_model=GeneratedLetterResponse)
def generate_document_letter(document_id: int, payload: LetterGenerationRequest, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    doc = access.assert_can_view(db, _get_doc(db, document_id), current_user)
    extracted_fields = doc.extracted_fields or {}
    recommendations = doc.recommended_actions or []
    letter = generate_letter_for_document(str(doc.document_type or 'unknown'), extracted_fields, recommendations, doc.extracted_text or '')
    if payload.reason:
        letter['body'] = f"{letter['body'].rstrip()}\n\nAdditional context from the user: {payload.reason}\n"
    doc.generated_letter = letter
    db.add(doc)
    db.commit()
    db.refresh(doc)
    audit.log(db, action='document.letter_generated', user_id=current_user.id, entity_type='document', entity_id=str(document_id), detail={'reason': payload.reason or 'default'}, ip_address=request.client.host if request.client else None, user_agent=request.headers.get('user-agent'), request_id=request.headers.get('x-request-id'))
    return GeneratedLetterResponse(**letter, source_document_id=doc.id, document_type=str(doc.document_type), extracted_fields=extracted_fields)
