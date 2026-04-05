from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.deps import get_admin_user, get_db
from app.models.document import AuditLog, Document, Notification
from app.models.user import User
from app.schemas.audit import AuditLogResponse
from app.schemas.observability import MetricsResponse
from app.schemas.user_admin import AdminUserResponse, AdminUserUpdateRequest
from app.services.audit_service import AuditService

router = APIRouter()
audit = AuditService()


def _active_admin_count(db: Session) -> int:
    return db.query(func.count(User.id)).filter(User.role == 'admin', User.is_active == True).scalar() or 0


@router.get('/metrics', response_model=MetricsResponse)
def metrics(db: Session = Depends(get_db), current_user: User = Depends(get_admin_user)):
    return MetricsResponse(
        users=db.query(func.count(User.id)).scalar() or 0,
        documents=db.query(func.count(Document.id)).scalar() or 0,
        notifications=db.query(func.count(Notification.id)).scalar() or 0,
        audit_logs=db.query(func.count(AuditLog.id)).scalar() or 0,
    )


@router.get('/audit', response_model=list[AuditLogResponse])
def audit_feed(limit: int = Query(default=100, le=500), db: Session = Depends(get_db), current_user: User = Depends(get_admin_user)):
    return db.query(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit).all()


@router.get('/users', response_model=list[AdminUserResponse])
def list_users(db: Session = Depends(get_db), current_user: User = Depends(get_admin_user)):
    return db.query(User).order_by(User.created_at.desc()).all()


@router.patch('/users/{user_id}', response_model=AdminUserResponse)
def update_user(user_id: int, payload: AdminUserUpdateRequest, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_admin_user)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail='User not found')

    next_role = payload.role if payload.role is not None else user.role
    next_is_active = payload.is_active if payload.is_active is not None else user.is_active

    if user.id == current_user.id and payload.is_active is False:
        raise HTTPException(status_code=400, detail='You cannot deactivate your own admin account')

    if user.role == 'admin' and (next_role != 'admin' or next_is_active is False) and _active_admin_count(db) <= 1:
        raise HTTPException(status_code=400, detail='At least one active admin must remain')

    user.role = next_role
    user.is_active = next_is_active
    db.add(user)
    db.commit()
    db.refresh(user)
    audit.log(db, action='admin.user_updated', user_id=current_user.id, entity_type='user', entity_id=str(user_id), detail=f'role={user.role};active={user.is_active}', ip_address=request.client.host if request.client else None)
    return user
