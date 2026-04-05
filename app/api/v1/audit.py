from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_admin_user, get_db
from app.models.document import AuditLog
from app.models.user import User

router = APIRouter()


@router.get('')
def list_audit_logs(db: Session = Depends(get_db), current_user: User = Depends(get_admin_user)):
    logs = db.query(AuditLog).order_by(AuditLog.created_at.desc()).limit(500).all()
    return [{'id': a.id, 'user_id': a.user_id, 'action': a.action, 'entity_type': a.entity_type, 'entity_id': a.entity_id, 'detail': a.detail or {}, 'ip_address': str(a.ip_address) if a.ip_address else None, 'created_at': a.created_at} for a in logs]


@router.get('/export')
def export_audit_logs(db: Session = Depends(get_db), current_user: User = Depends(get_admin_user)):
    rows = db.query(AuditLog).order_by(AuditLog.created_at.desc()).limit(1000).all()
    return {'items': [{'id': a.id, 'user_id': a.user_id, 'action': a.action, 'entity_type': a.entity_type, 'entity_id': a.entity_id, 'detail': a.detail or {}, 'ip_address': str(a.ip_address) if a.ip_address else None, 'created_at': a.created_at.isoformat() if a.created_at else None} for a in rows]}
