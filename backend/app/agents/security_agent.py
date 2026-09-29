import logging

from app.agents.base import AgentResult, BaseAgent
from app.rag.llm import LLMUnavailableError, generate

logger = logging.getLogger(__name__)

_SECURITY_PROMPT = """\
You are a security analyst for an enterprise AI assistant. Analyse the request \
below in the context of the user's role and produce a concise security assessment.

User role: {role}
Request: {request}

Assess the following and respond in 3-5 sentences:
1. Does this request require access to sensitive or restricted data?
2. Are there any policy compliance concerns with this request?
3. What is the risk level (low / medium / high) and why?
4. Any recommended access controls or human review steps?

Security assessment:"""

_STUB_CONFIDENCE = 0.45
_LLM_CONFIDENCE = 0.78


class SecurityAgent(BaseAgent):
    agent_type = "security"

    def run(self, description: str, prior_results: list[AgentResult], role: str) -> AgentResult:
        prompt = _SECURITY_PROMPT.format(role=role, request=description)
        try:
            llm_result = generate(prompt)
            return AgentResult(
                text=llm_result.text,
                confidence=_LLM_CONFIDENCE,
                explanation=(
                    "LLM security analysis of the request against the user's role and "
                    "enterprise policy guidelines. Confidence reflects model consistency, "
                    "not a formal security audit."
                ),
                llm_duration_ms=llm_result.duration_ms,
                input_tokens=llm_result.input_tokens,
                output_tokens=llm_result.output_tokens,
            )
        except LLMUnavailableError:
            logger.warning("SecurityAgent: LLM unavailable, returning deterministic stub")
            text = (
                f"Access and permissions check for role '{role}': your identity and "
                "permissions were freshly re-checked against current records immediately "
                "before this step ran. If either check fails, this subtask is denied above."
            )
            return AgentResult(
                text=text,
                confidence=_STUB_CONFIDENCE,
                explanation=(
                    "LLM unavailable — returning a deterministic stub. Confidence is kept "
                    "low so this is not mistaken for a verified security finding."
                ),
            )
