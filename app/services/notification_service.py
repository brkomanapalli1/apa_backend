from __future__ import annotations
import logging
import httpx
from sqlalchemy.orm import Session
from app.models.document import Notification
from app.core.config import settings

logger = logging.getLogger(__name__)


class NotificationService:
    def create(
        self, db: Session, user_id: int, title: str, body: str,
        channel: str = "in_app", payload: dict | None = None,
    ) -> Notification:
        """Store an in-app notification in the database."""
        item = Notification(
            user_id=user_id, title=title, body=body,
            channel=channel, payload=payload or {},
        )
        db.add(item); db.commit(); db.refresh(item)
        return item

    def send_push_if_available(self, user, title: str, body: str) -> bool:
        """Send Expo push notification if user has a push token."""
        token = getattr(user, "push_token", None)
        if not token:
            return False
        try:
            self.send_expo_push(token=token, title=title, body=body)
            return True
        except Exception as exc:
            logger.warning("Push notification failed for user %s: %s", getattr(user, "id", "?"), exc)
            return False

    def send_expo_push(self, token: str, title: str, body: str, data: dict | None = None) -> dict:
        """
        Send a push notification via Expo Push Notification service.
        Works for both iOS and Android via React Native Expo app.
        [HIPAA] Only minimum necessary info — no PHI in push body.
        """
        if not token or not token.startswith("ExponentPushToken"):
            logger.warning("Invalid Expo push token: %s", token[:20] if token else "None")
            return {"ok": False, "reason": "Invalid token"}

        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if settings.EXPO_ACCESS_TOKEN:
            headers["Authorization"] = f"Bearer {settings.EXPO_ACCESS_TOKEN}"

        payload = {
            "to": token,
            "title": title[:100],
            "body": body[:200],  # [HIPAA] Keep external messages brief
            "sound": "default",
            "priority": "high",
        }
        if data:
            payload["data"] = data

        try:
            with httpx.Client(timeout=10) as client:
                resp = client.post(
                    "https://exp.host/--/api/v2/push/send",
                    json=payload, headers=headers,
                )
                result = resp.json()
                if result.get("data", {}).get("status") == "error":
                    logger.warning("Expo push error: %s", result)
                return result
        except Exception as exc:
            logger.error("Expo push request failed: %s", exc)
            return {"ok": False, "error": str(exc)}
