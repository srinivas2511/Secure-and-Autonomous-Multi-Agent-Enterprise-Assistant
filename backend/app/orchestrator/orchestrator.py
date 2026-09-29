import logging
import time
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
from app.orchestrator.decomposer import decompose
from app.rbac.roles import can_use_agent
from app.rbac.zero_trust import verify_continuous_access

logger = logging.getLogger(__name__)

DENIAL_CONFIDENCE = 1.0
DENIAL_EXPLANATION = "This is a certain result based on access rules, not an estimate."
GENERIC_AGENT_ERROR = (
    "This subtask failed with an unexpected error. An administrator can check the audit "
    "log for details."
)


def compute_request_status(subtasks: list[SubTask]) -> str:
    """Priority: failed > pending_approval > partially_denied (covers both
    automated 'denied' and human 'rejected' subtasks) > completed."""
    statuses = {s.status for s in subtasks}
    if "failed" in statuses:
        return "failed"
    if "pending_approval" in statuses:
        return "pending_approval"
    if "denied" in statuses or "rejected" in statuses:
        return "partially_denied"
    return "completed"


def run_orchestration(request: EnterpriseRequest, db: Session) -> EnterpriseRequest:
    """Decompose the request into subtasks, assign each to its agent, run them,
    and persist the results. Runs synchronously -- agents are stubs for now.
    """
    plans = decompose(request.text)

    subtasks = [
        SubTask(request_id=request.id, agent_type=plan.agent_type, description=plan.description)
        for plan in plans
    ]
    db.add_all(subtasks)
    db.commit()
    for subtask in subtasks:
        db.refresh(subtask)

    prior_results: list[AgentResult] = []
    for subtask in subtasks:
        agent_result: AgentResult | None = None
        error_detail: str | None = None

        # Zero-Trust (FR-5): re-verify identity/authorization fresh immediately
        # before this subtask, rather than reusing a role captured once for
        # the whole request -- covers both this inter-agent dispatch and (for
        # the rag agent) the data-access it's about to perform.
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
                # Observability: open an agent-level trace span before calling the agent.
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
                db.flush()  # get agent_span.id without committing

                try:
                    agent = get_agent(subtask.agent_type)
                    # NFR-5 (Performance): time only the agent's own work, not
                    # the surrounding DB/Zero-Trust/RBAC overhead -- that's
                    # the part whose speed is agent-specific and actionable.
                    start = time.perf_counter()
                    agent_result = agent.run(subtask.description, prior_results, role)
                    subtask.duration_ms = round((time.perf_counter() - start) * 1000)
                    subtask.result = agent_result.text
                    subtask.confidence = agent_result.confidence

                    # FR-9: persist each simulated workflow step as a real
                    # record, regardless of whether this subtask is later
                    # gated for approval -- the simulated action already
                    # happened; HITL controls trust/finalization, not
                    # whether the (simulated) side effect occurred, same
                    # precedent as RAG's retrieval always happening (FR-8).
                    for i, step in enumerate(agent_result.workflow_steps, start=1):
                        db.add(
                            WorkflowExecution(
                                subtask_id=subtask.id,
                                step_number=i,
                                function_name=step["function_name"],
                                output=step["output"],
                            )
                        )
                        # Observability: one child span per workflow step.
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

                    # HITL (FR-7): sensitive or below-threshold decisions don't
                    # auto-complete -- they wait for a human approver
                    # (app/api/routes/approvals.py) instead of being trusted
                    # as a finished result.
                    flagged, reason = requires_approval(
                        subtask.agent_type, agent_result.confidence, agent_result.sensitive
                    )
                    if flagged:
                        subtask.status = "pending_approval"
                        subtask.explanation = (
                            f"{agent_result.explanation} Flagged for human review: {reason}."
                        )
                        # Observability: HITL gate child span.
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
                        prior_results.append(agent_result)
                    audit_action = f"{subtask.agent_type}.run"

                    # Observability: close the agent span and emit LLM child span if present.
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
                                metadata_={
                                    "model": None,  # available from settings if needed
                                },
                            )
                        )

                except Exception as exc:  # noqa: BLE001 -- isolate one agent's failure
                    # NFR-1: never show the raw exception to the requester -- it can
                    # contain internal details (infra hostnames, file paths, etc).
                    # Full detail goes to the server log and the (admin-only) audit
                    # log's context instead.
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
                    # Observability: close the span as failed.
                    agent_span.status = "failed"
                    agent_span.ended_at = datetime.now(timezone.utc)
                    agent_span.metadata_ = {"error": error_detail}

        # FR-8: log every agent action, whatever the outcome -- including
        # denials, where no agent ever ran. error_detail (admin-only, via
        # /api/admin/audit-logs) is where the real exception text lives now
        # that it's no longer shown to the requester (NFR-1).
        agent_action_context = {
            "agent_type": subtask.agent_type,
            "status": subtask.status,
            "confidence": subtask.confidence,
        }
        if error_detail is not None:
            agent_action_context["error_detail"] = error_detail
        log_event(
            db,
            event_type="agent_action",
            action=audit_action,
            user_id=request.user_id,
            role=verification.role,
            request_id=request.id,
            subtask_id=subtask.id,
            context=agent_action_context,
        )

        # FR-8/NFR-9: data access -- each agent declares its own
        # data_access_events (e.g. rag's vector-store retrieval, workflow's
        # retrieve_data call) on its AgentResult, whatever the outcome, so
        # this loop stays agent-agnostic instead of hardcoding per-agent-type
        # branches here.
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

    request.status = compute_request_status(subtasks)
    request.completed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(request)
    return request
