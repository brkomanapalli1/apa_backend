from __future__ import annotations

from typing import Optional
from datetime import datetime
from typing import List, Dict

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base
from app.db.enums import (
    DocumentStatus,
    DocumentType,
    MalwareScanStatus,
    NotificationChannel,
    ReminderStatus,
    UserRole,
    WorkflowState,
)
from app.db.sqlalchemy_types import values_enum


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    assigned_to_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(255))
    mime_type: Mapped[str] = mapped_column(String(120))
    file_size_bytes: Mapped[Optional[int]] = mapped_column(nullable=True)
    storage_key: Mapped[str] = mapped_column(String(500), unique=True)
    storage_bucket: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    checksum_sha256: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)

    status: Mapped[DocumentStatus] = mapped_column(
        values_enum(DocumentStatus, name="document_status_enum"),
        default=DocumentStatus.UPLOADING,
    )

    processing_job_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    extracted_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    deadlines: Mapped[List[dict]] = mapped_column(JSONB, default=list)

    document_type: Mapped[DocumentType] = mapped_column(
        values_enum(DocumentType, name="document_type_enum"),
        default=DocumentType.UNKNOWN,
        index=True,
    )

    document_type_confidence: Mapped[Optional[float]] = mapped_column(Numeric(5, 4), nullable=True)
    extracted_fields: Mapped[Dict[str, object]] = mapped_column(JSONB, default=dict)
    recommended_actions: Mapped[List[dict]] = mapped_column(JSONB, default=list)
    generated_letter: Mapped[Dict[str, object]] = mapped_column(JSONB, default=dict)
    has_ocr: Mapped[bool] = mapped_column(Boolean, default=False)

    malware_scan_status: Mapped[MalwareScanStatus] = mapped_column(
        values_enum(MalwareScanStatus, name="malware_scan_status_enum"),
        default=MalwareScanStatus.PENDING,
    )

    malware_scan_result: Mapped[Dict[str, object]] = mapped_column(JSONB, default=dict)

    workflow_state: Mapped[WorkflowState] = mapped_column(
        values_enum(WorkflowState, name="workflow_state_enum"),
        default=WorkflowState.NEW,
        index=True,
    )

    version_number: Mapped[int] = mapped_column(Integer, default=1)
    source_metadata: Mapped[Dict[str, object]] = mapped_column(JSONB, default=dict)
    processing_metadata: Mapped[Dict[str, object]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    owner = relationship("User", back_populates="documents", foreign_keys=[owner_id])
    shares = relationship("Share", back_populates="document", cascade="all, delete-orphan")
    reminders = relationship("Reminder", back_populates="document", cascade="all, delete-orphan")
    comments = relationship("Comment", back_populates="document", cascade="all, delete-orphan")
    versions = relationship("DocumentVersion", back_populates="document", cascade="all, delete-orphan")
    assignee = relationship("User", foreign_keys=[assigned_to_user_id], back_populates="assigned_documents")
    activities = relationship("DocumentActivity", back_populates="document", cascade="all, delete-orphan")


class DocumentVersion(Base):
    __tablename__ = "document_versions"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    version_number: Mapped[int] = mapped_column(Integer, index=True)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    deadlines: Mapped[List[dict]] = mapped_column(JSONB, default=list)

    document_type: Mapped[DocumentType] = mapped_column(
        values_enum(DocumentType, name="document_type_enum"),
        default=DocumentType.UNKNOWN,
        index=True,
    )

    document_type_confidence: Mapped[Optional[float]] = mapped_column(Numeric(5, 4), nullable=True)
    extracted_fields: Mapped[Dict[str, object]] = mapped_column(JSONB, default=dict)
    recommended_actions: Mapped[List[dict]] = mapped_column(JSONB, default=list)
    generated_letter: Mapped[Dict[str, object]] = mapped_column(JSONB, default=dict)
    storage_key: Mapped[str] = mapped_column(String(500))
    created_by_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    change_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    document = relationship("Document", back_populates="versions")


class Invitation(Base):
    __tablename__ = "invitations"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    inviter_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    invitee_email: Mapped[str] = mapped_column(String(255), index=True)
    token: Mapped[str] = mapped_column(String(255), unique=True, index=True)

    role: Mapped[UserRole] = mapped_column(
        values_enum(UserRole, name="user_role_enum"),
        default=UserRole.VIEWER,
    )

    accepted: Mapped[bool] = mapped_column(Boolean, default=False)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    accepted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    invitation_metadata: Mapped[Dict[str, object]] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    inviter = relationship("User", back_populates="sent_invitations")


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text)

    channel: Mapped[NotificationChannel] = mapped_column(
        values_enum(NotificationChannel, name="notification_channel_enum"),
        default=NotificationChannel.IN_APP,
    )

    is_read: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    read_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    payload: Mapped[Dict[str, object]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

    user = relationship("User", back_populates="notifications")


class Reminder(Base):
    __tablename__ = "reminders"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    due_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)

    status: Mapped[ReminderStatus] = mapped_column(
        values_enum(ReminderStatus, name="reminder_status_enum"),
        default=ReminderStatus.SCHEDULED,
        index=True,
    )

    payload: Mapped[Dict[str, object]] = mapped_column(JSONB, default=dict)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="reminders")
    document = relationship("Document", back_populates="reminders")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    action: Mapped[str] = mapped_column(String(120), index=True)
    entity_type: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    entity_id: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    detail: Mapped[Dict[str, object]] = mapped_column(JSONB, default=dict)
    ip_address: Mapped[Optional[str]] = mapped_column(INET, nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    request_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

    user = relationship("User", back_populates="audit_logs")


class Comment(Base):
    __tablename__ = "comments"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    body: Mapped[str] = mapped_column(Text)
    mentions: Mapped[List[dict]] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    document = relationship("Document", back_populates="comments")
    user = relationship("User", back_populates="comments")


class DocumentActivity(Base):
    __tablename__ = "document_activity"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    actor_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    activity_type: Mapped[str] = mapped_column(String(80), index=True)
    payload: Mapped[Dict[str, object]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

    document = relationship("Document", back_populates="activities")