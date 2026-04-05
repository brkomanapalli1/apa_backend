from datetime import datetime
from typing import Any

from pydantic import BaseModel, EmailStr, Field


class DocumentResponse(BaseModel):
    id: int
    name: str
    mime_type: str
    status: str
    processing_job_id: str | None = None
    summary: str | None = None
    deadlines: list[dict[str, Any]] = []
    document_type: str = 'unknown'
    document_type_confidence: float | None = None
    extracted_fields: dict[str, Any] = {}
    recommended_actions: list[dict[str, Any]] = []
    generated_letter: dict[str, Any] = {}
    has_ocr: bool
    created_at: datetime
    access_level: str = 'owner'
    workflow_state: str = 'new'
    version_number: int = 1
    assigned_to_user_id: int | None = None
    assigned_to_user_name: str | None = None

    class Config:
        from_attributes = True


class ShareRequest(BaseModel):
    email: EmailStr
    permission: str = Field(default='viewer', pattern='^(viewer|reviewer|editor)$')


class InvitationRequest(BaseModel):
    invitee_email: EmailStr
    role: str = Field(default='viewer', pattern='^(viewer|member|admin)$')


class PresignedUploadRequest(BaseModel):
    filename: str
    mime_type: str


class PresignedUploadResponse(BaseModel):
    upload_url: str
    document_id: int
    storage_key: str
    expires_in: int
    headers: dict[str, str] = {}


class CompleteUploadRequest(BaseModel):
    document_id: int


class JobStatusResponse(BaseModel):
    document_id: int
    status: str
    processing_job_id: str | None = None


class CommentRequest(BaseModel):
    body: str = Field(min_length=1, max_length=5000)


class CommentResponse(BaseModel):
    id: int
    document_id: int
    user_id: int
    user_name: str | None = None
    body: str
    mentions: list[str] = []
    created_at: datetime


class ActivityItemResponse(BaseModel):
    id: int
    action: str
    detail: dict[str, Any] | str | None = None
    created_at: datetime
    actor_name: str | None = None


class WorkflowUpdateRequest(BaseModel):
    workflow_state: str = Field(pattern='^(new|needs_review|in_progress|waiting_on_user|done)$')


class AssignmentRequest(BaseModel):
    assigned_to_user_id: int | None = None


class DocumentVersionResponse(BaseModel):
    id: int
    document_id: int
    version_number: int
    summary: str | None = None
    deadlines: list[dict[str, Any]] = []
    document_type: str = 'unknown'
    document_type_confidence: float | None = None
    extracted_fields: dict[str, Any] = {}
    recommended_actions: list[dict[str, Any]] = []
    generated_letter: dict[str, Any] = {}
    storage_key: str
    created_by_user_id: int | None = None
    created_at: datetime

    class Config:
        from_attributes = True


class LetterGenerationRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


class GeneratedLetterResponse(BaseModel):
    title: str
    subject: str
    body: str
    audience: str
    use_case: str
    source_document_id: int
    document_type: str | None = None
    extracted_fields: dict[str, Any] = {}
