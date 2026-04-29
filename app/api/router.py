from fastapi import APIRouter
from app.api.v1 import (
    admin, audit, auth, billing, documents,
    invitations, notifications, reminders,
    caregiver, vault, analytics, voice,
    renewals, preferences,
)

api_router = APIRouter()

# ── Core (Phase 1) ─────────────────────────────────────────────────────────
api_router.include_router(auth.router,          prefix="/auth",          tags=["auth"])
api_router.include_router(documents.router,     prefix="/documents",     tags=["documents"])
api_router.include_router(reminders.router,     prefix="/reminders",     tags=["reminders"])
api_router.include_router(notifications.router, prefix="/notifications", tags=["notifications"])
api_router.include_router(invitations.router,   prefix="/invitations",   tags=["invitations"])
api_router.include_router(audit.router,         prefix="/audit",         tags=["audit"])
api_router.include_router(billing.router,       prefix="/billing",       tags=["billing"])
api_router.include_router(admin.router,         prefix="/admin",         tags=["admin"])

# ── Phase 2: Smart Assistant ───────────────────────────────────────────────
api_router.include_router(analytics.router,     prefix="/analytics",     tags=["analytics"])
api_router.include_router(voice.router,         prefix="/voice",         tags=["voice"])

# ── Phase 3: Caregiver + Vault + Renewals ─────────────────────────────────
api_router.include_router(caregiver.router,     prefix="/caregiver",     tags=["caregiver"])
api_router.include_router(vault.router,         prefix="/vault",         tags=["emergency-vault"])
api_router.include_router(renewals.router,      prefix="/renewals",      tags=["renewals"])

# ── Phase 5: User Preferences + Translation ───────────────────────────────
api_router.include_router(preferences.router,   prefix="/preferences",   tags=["preferences"])
