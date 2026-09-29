from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class TraceSpan(Base):
    """Observability: one row per unit of work in the agent execution graph.

    Span types and their parent relationships:
      "agent"          — one per subtask; parent_span_id is None (root level)
      "llm_call"       — nested under an "agent" span (RAG, Analytics)
      "rag_retrieve"   — nested under an "agent" span (RAG vector-store query)
      "workflow_step"  — nested under an "agent" span (WorkflowAgent step)
      "hitl_gate"      — nested under an "agent" span (HITL approval trigger)
    """

    __tablename__ = "trace_spans"

    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[int] = mapped_column(
        ForeignKey("enterprise_requests.id"), nullable=False, index=True
    )
    subtask_id: Mapped[int | None] = mapped_column(
        ForeignKey("sub_tasks.id"), nullable=True, index=True
    )
    parent_span_id: Mapped[int | None] = mapped_column(
        ForeignKey("trace_spans.id"), nullable=True
    )
    span_type: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)
