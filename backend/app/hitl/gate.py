from app.agents.registry import humanize_agent_type
from app.core.settings_store import get_hitl_threshold

SENSITIVE_AGENT_TYPES = {"workflow"}  # performs real actions, not just reporting


def requires_approval(agent_type: str, confidence: float, sensitive: bool) -> tuple[bool, str | None]:
    """FR-7: route sensitive or low-confidence operations to Human-in-the-Loop
    approval before completion, instead of auto-completing."""
    threshold = get_hitl_threshold()
    if agent_type in SENSITIVE_AGENT_TYPES:
        return True, (
            f"the '{humanize_agent_type(agent_type)}' feature always requires human review "
            "because it can take real actions"
        )
    if sensitive:
        return True, "this operation touched sensitive/restricted enterprise data"
    if confidence < threshold:
        return (
            True,
            f"confidence {confidence:.0%} is below the {threshold:.0%} approval threshold",
        )
    return False, None
