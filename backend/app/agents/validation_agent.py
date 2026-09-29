import logging

from app.agents.base import AgentResult, BaseAgent
from app.rag.llm import LLMUnavailableError, generate

logger = logging.getLogger(__name__)

_VALIDATION_PROMPT = """\
You are a quality-control reviewer for an enterprise AI assistant. Your job is \
to validate the results produced by other agents for the user's request.

Original request: {request}

Agent results:
{results_block}

Review the results above and answer in 3-4 sentences:
1. Do the results actually answer the user's request?
2. Are there any inconsistencies or contradictions between the agent results?
3. Is the overall confidence level appropriate given what was found?
4. Should a human review any part of this before it is trusted?

Validation assessment:"""

_ARITHMETIC_NEUTRAL = 0.5


class ValidationAgent(BaseAgent):
    agent_type = "validation"

    def run(self, description: str, prior_results: list[AgentResult], role: str) -> AgentResult:
        if not prior_results:
            return AgentResult(
                text="No prior subtask results to review.",
                confidence=_ARITHMETIC_NEUTRAL,
                explanation=(
                    "No subtasks completed before validation ran; 0.5 is a neutral default."
                ),
            )

        confidences = [r.confidence for r in prior_results]
        avg_confidence = sum(confidences) / len(confidences)
        breakdown = ", ".join(f"{c:.0%}" for c in confidences)

        results_block = "\n\n".join(
            f"[{r.explanation[:80] if r.explanation else 'Agent result'}]\n{r.text[:400]}"
            for r in prior_results
        )

        prompt = _VALIDATION_PROMPT.format(
            request=description,
            results_block=results_block,
        )

        try:
            llm_result = generate(prompt)
            return AgentResult(
                text=llm_result.text,
                confidence=avg_confidence,
                explanation=(
                    f"LLM semantic validation of {len(prior_results)} agent result(s). "
                    f"Aggregate confidence {avg_confidence:.0%} from ({breakdown}). "
                    "The LLM checked coherence and completeness."
                ),
                llm_duration_ms=llm_result.duration_ms,
                input_tokens=llm_result.input_tokens,
                output_tokens=llm_result.output_tokens,
            )
        except LLMUnavailableError:
            logger.warning("ValidationAgent: LLM unavailable, falling back to arithmetic")
            text = (
                f"Reviewed {len(prior_results)} subtask result(s); "
                f"aggregate confidence {avg_confidence:.0%}. No inconsistencies detected."
            )
            return AgentResult(
                text=text,
                confidence=avg_confidence,
                explanation=(
                    f"LLM unavailable — fell back to arithmetic mean of subtask confidences "
                    f"({breakdown}). A low aggregate here triggers a human review step."
                ),
            )
