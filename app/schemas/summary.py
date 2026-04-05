from pydantic import BaseModel


class SummaryResponse(BaseModel):
    summary: str
    deadlines: str | None = None
