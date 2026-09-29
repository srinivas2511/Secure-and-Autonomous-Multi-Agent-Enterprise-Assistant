import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.agents.base import AgentResult
from app.agents.registry import get_agent, humanize_agent_type
from app.audit.logger import log_event
from app.hitl.gate import requires_approval
from app.models.enterprise_request import EnterpriseRequest
from app.models.sub_task import SubTask
from app.models.trace_span import TraceSpan
from app.models.workflow_execution import WorkflowExecution
from app.orchestrator.decomposer import VALIDATION_AGENT_TYPE, decompose
from app.rbac.roles import can_use_agent
from app.rbac.zero_trust import verify_continuous_access

logger = logging.getLogger(__name__)

DENIAL_CONFIDENCE = 1.0
DENIAL_EXPLANATION = "This is a certain result based on access rules, not an estimate."
GENERIC_AGENT_ERROR = (
    "This subtask failed with an unexpected error. An administrator can check the audit "
    "log for details."
)

# Agents that may run in parallel (order-independent). Validation always runs last.
_PARALLEL_ELIGIBLE = {"rag", "security", "analytics", "workflow"}


def compute_request_status(subtasks: list[SubTask]) -> str:
    statuses = {s.status for s in subtasks}
    if "failed" in statuses:
        return "failed"
    if "pending_approval" in statuses:
        return "pending_approval"
    if "denied" in statuses or "rejected" in statuses:
        return "partially_denied"
    return "completed"


def _run_single_subtask(
    subtask: SubTask,
    prior_results: list[AgentResult],
    request: EnterpriseRequest,
    db: Session,
) -> AgentResult | None:
    """Execute one subtask with Zero-Trust + RBAC + HITL. Mutates subtask in place."""
    agent_result: AgentResult | None = None
    error_detail: str | None = None

    verification = verify_continuous_access(request.user_id, db)
    if not verification.verified:
        subtask.status = "denied"
        subtask.result = f"Your access could not be verified: {verification.reason}."
        subtask.confidence = DENIAL_CONFIDENCE
        subtask.explanation = DENIAL_EXPLANATION
        audit_action = "zero_trust.deny"
    else:
        role = verification.role
        if not can_use_agent(role, subtask.agent_type, db):
            subtask.status = "denied"
            subtask.result = (
                f"Access denied: the '{role}' role does not have permission to use the "
                f"'{humanize_agent_type(subtask.agent_type)}' feature. Contact an "
                "administrator if you believe this is incorrect."
            )
            subtask.confidence = DENIAL_CONFIDENCE
            subtask.explanation = DENIAL_EXPLANATION
            audit_action = "rbac.deny"
        else:
            span_started_at = datetime.now(timezone.utc)
            agent_span = TraceSpan(
                request_id=request.id,
                subtask_id=subtask.id,
                parent_span_id=None,
                span_type="agent",
                name=subtask.agent_type,
                status="running",
                started_at=span_started_at,
            )
            db.add(agent_span)
            db.flush()

            try:
                agent = get_agent(subtask.agent_type)
                start = time.perf_counter()
                agent_result = agent.run(subtask.description, prior_results, role)
                subtask.duration_ms = round((time.perf_counter() - start) * 1000)
                subtask.result = agent_result.text
                subtask.confidence = agent_result.confidence

                for i, step in enumerate(agent_result.workflow_steps, start=1):
                    db.add(
                        WorkflowExecution(
                            subtask_id=subtask.id,
                            step_number=i,
                            function_name=step["function_name"],
                            output=step["output"],
                        )
                    )
                    db.add(
                        TraceSpan(
                            request_id=request.id,
                            subtask_id=subtask.id,
                            parent_span_id=agent_span.id,
                            span_type="workflow_step",
                            name=step["function_name"],
                            status="completed",
                            started_at=span_started_at,
                            ended_at=datetime.now(timezone.utc),
                            metadata_={"step_number": i, "output": step["output"]},
                        )
                    )

                flagged, reason = requires_approval(
                    subtask.agent_type, agent_result.confidence, agent_result.sensitive
                )
                if flagged:
                    subtask.status = "pending_approval"
                    subtask.explanation = (
                        f"{agent_result.explanation} Flagged for human review: {reason}."
                    )
                    db.add(
                        TraceSpan(
                            request_id=request.id,
                            subtask_id=subtask.id,
                            parent_span_id=agent_span.id,
                            span_type="hitl_gate",
                            name="hitl_gate",
                            status="pending_approval",
                            started_at=datetime.now(timezone.utc),
                            ended_at=datetime.now(timezone.utc),
                            metadata_={"reason": reason},
                        )
                    )
                else:
                    subtask.status = "completed"
                    subtask.explanation = agent_result.explanation

                audit_action = f"{subtask.agent_type}.run"
                span_ended_at = datetime.now(timezone.utc)
                agent_span.status = subtask.status
                agent_span.ended_at = span_ended_at
                agent_span.duration_ms = subtask.duration_ms
                agent_span.metadata_ = {
                    "confidence": agent_result.confidence,
                    "explanation": agent_result.explanation,
                    "sensitive": agent_result.sensitive,
                    "sources": agent_result.sources,
                }

                if agent_result.llm_duration_ms is not None:
                    db.add(
                        TraceSpan(
                            request_id=request.id,
                            subtask_id=subtask.id,
                            parent_span_id=agent_span.id,
                            span_type="llm_call",
                            name="llm_generate",
                            status="completed",
                            started_at=span_started_at,
                            ended_at=span_ended_at,
                            duration_ms=agent_result.llm_duration_ms,
                            input_tokens=agent_result.input_tokens,
                            output_tokens=agent_result.output_tokens,
                            metadata_={"model": None},
                        )
                    )

            except Exception as exc:
                logger.exception(
                    "Agent %s failed for subtask %d", subtask.agent_type, subtask.id
                )
                error_detail = str(exc)
                subtask.status = "failed"
                subtask.result = GENERIC_AGENT_ERROR
                subtask.confidence = None
                subtask.explanation = (
                    "This subtask failed with an unexpected error; no confidence applies."
                )
                audit_action = f"{subtask.agent_type}.error"
                agent_span.status = "failed"
                agent_span.ended_at = datetime.now(timezone.utc)
                agent_span.metadata_ = {"error": error_detail}

    # Audit log (always, regardless of outcome)
    ctx = {
        "agent_type": subtask.agent_type,
        "status": subtask.status,
        "confidence": subtask.confidence,
    }
    if error_detail:
        ctx["error_detail"] = error_detail
    log_event(
        db,
        event_type="agent_action",
        action=audit_action,
        user_id=request.user_id,
        role=verification.role,
        request_id=request.id,
        subtask_id=subtask.id,
        context=ctx,
    )

    if agent_result is not None:
        for event in agent_result.data_access_events:
            log_event(
                db,
                event_type="data_access",
                action=event["action"],
                user_id=request.user_id,
                role=verification.role,
                request_id=request.id,
                subtask_id=subtask.id,
                context=event["context"],
            )

    db.commit()
    return agent_result if subtask.status == "completed" else None


def run_orchestration(request: EnterpriseRequest, db: Session) -> EnterpriseRequest:
    """Decompose → dispatch agents (parallel where independent) → aggregate.

    Parallel agents: rag, security, analytics, workflow (order-independent).
    Validation always runs last, receiving all completed prior results.
    """
    plans = decompose(request.text)

    parallel_plans = [p for p in plans if p.agent_type in _PARALLEL_ELIGIBLE]
    sequential_plans = [p for p in plans if p.agent_type not in _PARALLEL_ELIGIBLE]

    # Persist all subtasks up front so the frontend can see them immediately.
    all_plans = parallel_plans + sequential_plans
    subtasks = [
        SubTask(
            request_id=request.id,
            agent_type=plan.agent_type,
            description=plan.description,
        )
        for plan in all_plans
    ]
    db.add_all(subtasks)
    db.commit()
    for st in subtasks:
        db.refresh(st)

    # Split into parallel and sequential SubTask objects.
    p_subtasks = subtasks[: len(parallel_plans)]
    s_subtasks = subtasks[len(parallel_plans):]

    prior_results: list[AgentResult] = []

    # ── Run parallel agents concurrently ────────────────────────────────────
    if p_subtasks:
        # Each thread needs its own DB session to avoid cross-thread conflicts.
        from app.core.database import SessionLocal

        def _run_in_thread(st: SubTask) -> AgentResult | None:
            thread_db = SessionLocal()
            # Re-fetch the subtask within this thread's session.
            thread_st = thread_db.query(SubTask).filter(SubTask.id == st.id).first()
            thread_req = (
                thread_db.query(EnterpriseRequest)
                .filter(EnterpriseRequest.id == request.id)
                .first()
            )
            try:
                return _run_single_subtask(thread_st, list(prior_results), thread_req, thread_db)
            finally:
                thread_db.close()

        with ThreadPoolExecutor(max_workers=min(len(p_subtasks), 4)) as executor:
            futures = {executor.submit(_run_in_thread, st): st for st in p_subtasks}
            for future in as_completed(futures):
                result = future.result()
                if result is not None:
                    prior_results.append(result)

        # Refresh subtask state from DB after parallel execution.
        for st in p_subtasks:
            db.refresh(st)

    # ── Run sequential agents (validation etc.) one at a time ───────────────
    for st in s_subtasks:
        result = _run_single_subtask(st, prior_results, request, db)
        if result is not None:
            prior_results.append(result)

    all_subtasks_fresh = db.query(SubTask).filter(SubTask.request_id == request.id).all()
    request.status = compute_request_status(all_subtasks_fresh)
    request.completed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(request)
    return request
