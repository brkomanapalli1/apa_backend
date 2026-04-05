from __future__ import annotations
from sqlalchemy import DateTime, Enum, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base
from app.db.enums import SharePermission


class Share(Base):
    __tablename__ = 'shares'
    __table_args__ = (UniqueConstraint('document_id', 'shared_with_email', name='uq_document_share_email'),)

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    document_id: Mapped[int] = mapped_column(ForeignKey('documents.id', ondelete='CASCADE'), index=True)
    shared_with_email: Mapped[str] = mapped_column(String(255), index=True)
    permission: Mapped[SharePermission] = mapped_column(Enum(SharePermission, name='share_permission_enum'), default=SharePermission.VIEWER)
    shared_by_user_id: Mapped[int | None] = mapped_column(ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    share_metadata: Mapped[dict] = mapped_column("metadata",JSONB, default=dict)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    document = relationship('Document', back_populates='shares')
