from datetime import datetime

from pydantic import BaseModel


class ReminderResponse(BaseModel):
    id: int
    user_id: int
    document_id: int
    title: str
    due_at: datetime | None = None
    status: str
    created_at: datetime

    class Config:
        from_attributes = True
