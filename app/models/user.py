from __future__ import annotations

from sqlalchemy import Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base
from app.db.enums import SSOProvider, SubscriptionStatus, UserRole
from app.db.sqlalchemy_types import values_enum


class User(Base):
    __tablename__ = 'users'

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(255))
    hashed_password: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    role: Mapped[UserRole] = mapped_column(
        values_enum(UserRole, name='user_role_enum'),
        default=UserRole.MEMBER,
        index=True,
    )

    stripe_customer_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, unique=True, index=True
    )

    subscription_status: Mapped[SubscriptionStatus] = mapped_column(
        values_enum(SubscriptionStatus, name='subscription_status_enum'),
        default=SubscriptionStatus.FREE,
    )

    push_token: Mapped[str | None] = mapped_column(String(255), nullable=True)
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    totp_secret: Mapped[str | None] = mapped_column(String(255), nullable=True)

    sso_provider: Mapped[SSOProvider | None] = mapped_column(
        values_enum(SSOProvider, name='sso_provider_enum'),
        nullable=True,
    )

    profile: Mapped[dict] = mapped_column(JSONB, default=dict)
    preferences: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    documents = relationship(
        'Document',
        back_populates='owner',
        cascade='all, delete-orphan',
        foreign_keys='Document.owner_id',
    )
    sent_invitations = relationship('Invitation', back_populates='inviter', cascade='all, delete-orphan')
    notifications = relationship('Notification', back_populates='user', cascade='all, delete-orphan')
    audit_logs = relationship('AuditLog', back_populates='user', cascade='all, delete-orphan')
    reminders = relationship('Reminder', back_populates='user', cascade='all, delete-orphan')
    comments = relationship('Comment', back_populates='user', cascade='all, delete-orphan')
    assigned_documents = relationship(
        'Document',
        foreign_keys='Document.assigned_to_user_id',
        back_populates='assignee',
    )
    refresh_tokens = relationship('RefreshToken', back_populates='user', cascade='all, delete-orphan')


class RefreshToken(Base):
    __tablename__ = 'refresh_tokens'

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    token_jti: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    is_revoked: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    expires_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), index=True)
    token_metadata: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user = relationship('User', back_populates='refresh_tokens')