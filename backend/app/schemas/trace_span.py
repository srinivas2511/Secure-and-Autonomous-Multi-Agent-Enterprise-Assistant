from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TraceSpanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: int
    request_id: int
    subtask_id: int | None
    parent_span_id: int | None
    span_type: str
    name: str
    status: str
    started_at: datetime
    ended_at: datetime | None
    duration_ms: int | None
    input_tokens: int | None
    output_tokens: int | None
    # The ORM column is `metadata_` to avoid SQLAlchemy's reserved `.metadata`
    # attribute; expose it as `metadata` in the API response.
    metadata: dict | None = Field(None, validation_alias="metadata_")
