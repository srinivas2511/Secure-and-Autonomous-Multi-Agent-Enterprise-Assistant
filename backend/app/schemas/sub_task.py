from datetime import datetime

from pydantic import BaseModel, ConfigDict


class SubTaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    agent_type: str
    description: str
    status: str
    result: str | None
    confidence: float | None
    explanation: str | None
    duration_ms: int | None
    approved_by_email: str | None
    approved_at: datetime | None
    created_at: datetime
    workflow_steps: list[dict] = []
