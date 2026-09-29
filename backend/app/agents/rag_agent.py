from app.agents.base import AgentResult, BaseAgent
from app.rag.pipeline import answer_with_rag


class RAGAgent(BaseAgent):
    agent_type = "rag"

    def run(self, description: str, prior_results: list[AgentResult], role: str) -> AgentResult:
        # Let a pipeline failure (retrieval/LLM) propagate to the orchestrator's
        # uniform except-block handling -- it already logs the real error and
        # keeps a generic, safe message on the requester-facing result (NFR-1),
        # rather than duplicating that logic (and the leak it used to have) here.
        result = answer_with_rag(description, role)

        text = result.answer
        if result.sources:
            text += f"\n\nSources: {', '.join(result.sources)}"

        return AgentResult(
            text=text,
            confidence=result.confidence,
            explanation=result.explanation,
            sensitive=result.sensitive,
            sources=result.sources,
            # FR-8: the vector store was queried whenever this ran, regardless
            # of whether the answer was granted, access-denied, or later
            # flagged for approval.
            data_access_events=[
                {
                    "action": "rag.retrieve",
                    "context": {"sources": result.sources, "sensitive": result.sensitive},
                }
            ],
            llm_duration_ms=result.llm_duration_ms,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
        )
