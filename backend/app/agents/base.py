from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class AgentResult:
    """FR-6 (XAI): every agent decision carries a confidence score and an
    explanation of how that confidence was derived, alongside its text."""

    text: str
    confidence: float
    explanation: str
    # FR-7 (HITL): whether this decision touched sensitive/restricted data,
    # regardless of confidence. Only RAGAgent sets this; others default False.
    sensitive: bool = False
    # FR-8 (audit): documents this decision was grounded on, if any -- lets the
    # orchestrator log a data_access event without re-deriving it. Empty for
    # every agent except RAGAgent.
    sources: list[str] = field(default_factory=list)
    # FR-9: simulated-function steps this decision executed, if any -- lets the
    # orchestrator persist a WorkflowExecution row per step without re-deriving
    # it. Empty for every agent except WorkflowAgent. Each entry is
    # {"function_name": str, "output": dict}.
    workflow_steps: list[dict] = field(default_factory=list)
    # NFR-9 (Maintainability): data_access audit events this decision should
    # generate, if any -- keeps the orchestrator agent-agnostic (it doesn't
    # need an `if agent_type == "..."` branch per agent to know who touched
    # real data). Each entry is {"action": str, "context": dict}.
    data_access_events: list[dict] = field(default_factory=list)
    # Observability: LLM call telemetry captured by agents that call generate().
    # Populated only by RAGAgent and AnalyticsAgent; None for all others.
    llm_duration_ms: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None


class BaseAgent(ABC):
    """Common interface every specialized agent implements.

    Real agent logic lands with later FRs (FR-3 RAG, FR-9 Workflow done;
    security/analytics remain deterministic stubs so the orchestrator's
    decomposition/routing/aggregation can be exercised for agent types that
    don't have a dedicated FR yet -- their confidence reflects that honestly
    (fixed, low). `role` is the requesting user's role -- most agents ignore
    it (the orchestrator already gates *whether* an agent runs at all per
    FR-4); RAGAgent uses it to gate *which documents* it may ground on.
    """

    agent_type: str

    @abstractmethod
    def run(self, description: str, prior_results: list[AgentResult], role: str) -> AgentResult:
        """Execute the subtask and return its result, confidence, and explanation."""
        raise NotImplementedError
