from datetime import datetime

from pydantic import BaseModel


class NotificationResponse(BaseModel):
    id: int
    title: str
    body: str
    channel: str
    is_read: bool
    created_at: datetime

    class Config:
        from_attributes = True
