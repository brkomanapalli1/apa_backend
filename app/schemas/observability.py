from pydantic import BaseModel


class MetricsResponse(BaseModel):
    users: int
    documents: int
    notifications: int
    audit_logs: int
