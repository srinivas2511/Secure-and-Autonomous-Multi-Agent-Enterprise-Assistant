from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class SubTask(Base):
    __tablename__ = "sub_tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[int] = mapped_column(
        ForeignKey("enterprise_requests.id"), nullable=False, index=True
    )
    agent_type: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    # NFR-5 (Performance): indexed -- list_pending_approvals filters on this
    # on every admin approvals-queue load.
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="pending", index=True
    )
    result: Mapped[str | None] = mapped_column(Text, nullable=True)
    # FR-6 (XAI): confidence (0.0-1.0) and the rationale behind it. Nullable
    # because pre-FR-6 rows and failed subtasks have neither.
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    # NFR-5 (Performance): wall-clock time of the agent's actual work
    # (agent.run()), excluding DB/Zero-Trust/RBAC overhead -- the part
    # that's actually agent-specific and optimizable. Null for denied
    # subtasks, which never call an agent.
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # FR-7 (HITL): set once an admin approves/rejects a pending_approval subtask.
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    request: Mapped["EnterpriseRequest"] = relationship(back_populates="subtasks")
    approver: Mapped["User | None"] = relationship(foreign_keys=[approved_by])
    workflow_executions: Mapped[list["WorkflowExecution"]] = relationship(
        "WorkflowExecution", foreign_keys="WorkflowExecution.subtask_id"
    )

    @property
    def approved_by_email(self) -> str | None:
        return self.approver.email if self.approver else None

    @property
    def workflow_steps(self) -> list[dict]:
        return [
            {"step": we.step_number, "function": we.function_name, "output": we.output}
            for we in sorted(self.workflow_executions, key=lambda x: x.step_number)
        ]
