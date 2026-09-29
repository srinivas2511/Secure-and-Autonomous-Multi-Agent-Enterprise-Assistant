import json
import logging
from dataclasses import dataclass

from app.core.config import settings

logger = logging.getLogger(__name__)

# ── Keyword fallback (used when LLM is unavailable) ──────────────────────────
AGENT_KEYWORDS: dict[str, list[str]] = {
    "security": ["access", "permission", "role", "authoriz", "security", "who can"],
    "analytics": ["report", "analy", "data", "metric", "trend", "statistic", "dashboard", "summar"],
    "rag": ["policy", "document", "knowledge", "find", "lookup", "what is", "explain", "search"],
    "workflow": ["create", "update", "schedule", "approve", "submit", "process", "automate", "task"],
}

FALLBACK_AGENT_TYPE = "workflow"
VALIDATION_AGENT_TYPE = "validation"

_PLANNER_PROMPT = """\
You are a task planner for an enterprise AI assistant. Given a user request, \
identify which specialized agents should handle it and briefly describe each \
subtask. Output ONLY a JSON array with no markdown or explanation.

Available agents:
- "rag"       : retrieve information from enterprise documents / knowledge base
- "analytics" : analyse enterprise data, metrics, headcount, expenses
- "security"  : check access permissions and security policy compliance
- "workflow"  : execute multi-step tasks: create, update, schedule, automate

Rules:
- Include only the agents genuinely needed for this specific request.
- Always end with exactly one "validation" agent to review all results.
- Each object has exactly two keys: "agent_type" (string) and "description" (string).
- The description is a concise restatement of the relevant part of the request for that agent.

Example output:
[
  {{"agent_type": "rag", "description": "Find the company leave policy"}},
  {{"agent_type": "validation", "description": "Verify the response is accurate and complete"}}
]

User request: {request}

JSON array:"""


@dataclass
class SubTaskPlan:
    agent_type: str
    description: str


def _keyword_decompose(text: str) -> list[SubTaskPlan]:
    """Rule-based fallback when the LLM is unavailable."""
    lowered = text.lower()
    matched = [
        agent_type
        for agent_type, keywords in AGENT_KEYWORDS.items()
        if any(keyword in lowered for keyword in keywords)
    ]
    if not matched:
        matched = [FALLBACK_AGENT_TYPE]
    plans = [SubTaskPlan(agent_type=t, description=text) for t in matched]
    plans.append(SubTaskPlan(agent_type=VALIDATION_AGENT_TYPE, description=text))
    return plans


def _llm_decompose(text: str) -> list[SubTaskPlan]:
    """LLM-driven planning. Raises on failure so the caller can fall back."""
    from app.rag.llm import generate

    result = generate(_PLANNER_PROMPT.format(request=text))
    raw = result.text.strip()

    # Strip accidental markdown fences
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]

    items = json.loads(raw)
    if not isinstance(items, list):
        raise ValueError("LLM planner did not return a list")

    plans: list[SubTaskPlan] = []
    for item in items:
        agent_type = str(item.get("agent_type", "")).strip()
        description = str(item.get("description", text)).strip()
        if not agent_type:
            continue
        plans.append(SubTaskPlan(agent_type=agent_type, description=description or text))

    # Guarantee a validation subtask exists (LLM might omit it)
    if not any(p.agent_type == VALIDATION_AGENT_TYPE for p in plans):
        plans.append(SubTaskPlan(agent_type=VALIDATION_AGENT_TYPE, description=text))

    return plans


def decompose(text: str) -> list[SubTaskPlan]:
    """Route a request to one or more agents.

    Tries LLM-based planning first; falls back to keyword routing if the LLM
    is unavailable or returns unparseable output.
    """
    if settings.use_llm_decomposer:
        try:
            plans = _llm_decompose(text)
            logger.debug("LLM decomposer produced %d subtasks", len(plans))
            return plans
        except Exception as exc:
            logger.warning("LLM decomposer failed (%s), falling back to keyword routing", exc)

    return _keyword_decompose(text)
