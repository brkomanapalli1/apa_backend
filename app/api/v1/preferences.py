"""
preferences.py — User Preferences API

Handles:
  - Language preference (for translation)
  - Accessibility settings (large text, high contrast)
  - Notification preferences (which channels, quiet hours)
  - Voice preferences

GET  /preferences          — Get current user preferences
PUT  /preferences          — Update preferences
GET  /preferences/languages — List supported languages
"""
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.core.deps import get_current_user, get_db
from app.models.user import User

router = APIRouter()


class AccessibilitySettings(BaseModel):
    large_text: bool = False
    high_contrast: bool = False
    voice_only: bool = False
    text_size_scale: float = 1.0  # 1.0 = normal, 1.4 = large, 1.8 = extra large


class NotificationPreferences(BaseModel):
    push_enabled: bool = True
    email_enabled: bool = True
    sms_enabled: bool = False
    medication_reminders: bool = True
    bill_reminders: bool = True
    deadline_alerts: bool = True
    scam_alerts: bool = True
    quiet_hours_start: str = "21:00"   # 9 PM
    quiet_hours_end: str = "08:00"     # 8 AM


class UserPreferences(BaseModel):
    language: str = "en"
    accessibility: AccessibilitySettings = AccessibilitySettings()
    notifications: NotificationPreferences = NotificationPreferences()
    voice_speed: float = 0.9  # Slightly slower for seniors
    voice_gender: str = "female"  # nova = female, echo = male


class UpdatePreferencesRequest(BaseModel):
    language: str | None = None
    accessibility: AccessibilitySettings | None = None
    notifications: NotificationPreferences | None = None
    voice_speed: float | None = None
    voice_gender: str | None = None


@router.get("")
def get_preferences(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get current user preferences."""
    prefs = current_user.preferences or {}

    return {
        "language": prefs.get("language", "en"),
        "accessibility": prefs.get("accessibility", AccessibilitySettings().model_dump()),
        "notifications": prefs.get("notifications", NotificationPreferences().model_dump()),
        "voice_speed": prefs.get("voice_speed", 0.9),
        "voice_gender": prefs.get("voice_gender", "female"),
    }


@router.put("")
def update_preferences(
    payload: UpdatePreferencesRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update user preferences."""
    from app.services.translation_service import SUPPORTED_LANGUAGES

    if payload.language and payload.language not in SUPPORTED_LANGUAGES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported language: {payload.language}. Supported: {list(SUPPORTED_LANGUAGES.keys())}"
        )

    prefs = dict(current_user.preferences or {})

    if payload.language is not None:
        prefs["language"] = payload.language
    if payload.accessibility is not None:
        prefs["accessibility"] = payload.accessibility.model_dump()
    if payload.notifications is not None:
        prefs["notifications"] = payload.notifications.model_dump()
    if payload.voice_speed is not None:
        prefs["voice_speed"] = max(0.5, min(2.0, payload.voice_speed))
    if payload.voice_gender is not None:
        prefs["voice_gender"] = payload.voice_gender

    current_user.preferences = prefs
    db.add(current_user)
    db.commit()

    return {"ok": True, "preferences": prefs}


@router.get("/languages")
def list_languages(current_user: User = Depends(get_current_user)):
    """List all supported languages for translation."""
    from app.services.translation_service import SUPPORTED_LANGUAGES
    return {
        "languages": [
            {"code": code, "name": name}
            for code, name in SUPPORTED_LANGUAGES.items()
        ]
    }
