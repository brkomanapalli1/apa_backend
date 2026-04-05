from fastapi import APIRouter

from app.api.v1 import admin, audit, auth, billing, documents, invitations, notifications, reminders

api_router = APIRouter()
api_router.include_router(auth.router, prefix='/auth', tags=['auth'])
api_router.include_router(documents.router, prefix='/documents', tags=['documents'])
api_router.include_router(reminders.router, prefix='/reminders', tags=['reminders'])
api_router.include_router(audit.router, prefix='/audit', tags=['audit'])
api_router.include_router(invitations.router, prefix='/invitations', tags=['invitations'])
api_router.include_router(notifications.router, prefix='/notifications', tags=['notifications'])
api_router.include_router(billing.router, prefix='/billing', tags=['billing'])
api_router.include_router(admin.router, prefix='/admin', tags=['admin'])
