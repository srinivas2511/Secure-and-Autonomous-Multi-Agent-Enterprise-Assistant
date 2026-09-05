from app.agents.base import AgentResult, BaseAgent
from app.rag.llm import generate
from app.workflow.functions import (
    MOCK_EXPENSE_TOTALS_USD,
    MOCK_HEADCOUNT,
    _match_department,
)

_PROMPT = """\
You are an enterprise analytics assistant. Answer the request below using ONLY \
the data provided. Be concise and specific -- cite figures where relevant.

ENTERPRISE DATA (simulated, current period):
Headcount by department: {headcount}
Monthly expenses (USD) by department: {expenses}
Total headcount: {total_hc}  |  Total monthly expenses: ${total_exp:,}

REQUEST:
{question}

ANALYSIS:"""

# Higher confidence when we matched a specific department; lower when we had
# to show everything and the LLM had to interpret which figures apply.
_DEPT_CONFIDENCE = 0.82
_BROAD_CONFIDENCE = 0.58


class AnalyticsAgent(BaseAgent):
    agent_type = "analytics"

    def run(self, description: str, prior_results: list[AgentResult], role: str) -> AgentResult:
        dept = _match_department(description)

        if dept:
            headcount_str = f"{dept}: {MOCK_HEADCOUNT[dept]}"
            expenses_str = f"{dept}: ${MOCK_EXPENSE_TOTALS_USD[dept]:,}"
            confidence = _DEPT_CONFIDENCE
            explanation = (
                f"Analytics grounded in mock enterprise dataset for {dept}. "
                "Figures are simulated (real ERP integration is out of scope) -- "
                "confidence reflects dataset specificity, not live-data certainty."
            )
        else:
            headcount_str = ", ".join(f"{d}: {n}" for d, n in MOCK_HEADCOUNT.items())
            expenses_str = ", ".join(
                f"{d}: ${n:,}" for d, n in MOCK_EXPENSE_TOTALS_USD.items()
            )
            confidence = _BROAD_CONFIDENCE
            explanation = (
                "No specific department matched, so all departments were included. "
                "Confidence is moderate because the LLM had to interpret which "
                "figures apply rather than being given a single focused dataset."
            )

        prompt = _PROMPT.format(
            headcount=headcount_str,
            expenses=expenses_str,
            total_hc=sum(MOCK_HEADCOUNT.values()),
            total_exp=sum(MOCK_EXPENSE_TOTALS_USD.values()),
            question=description,
        )

        # Let LLM errors propagate to the orchestrator's uniform handler (same
        # as RAGAgent) -- it logs the real error and shows a safe message to
        # the requester (NFR-1).
        text = generate(prompt)

        return AgentResult(
            text=text,
            confidence=confidence,
            explanation=explanation,
            data_access_events=[
                {
                    "action": "analytics.retrieve_data",
                    "context": {
                        "department": dept or "all",
                        "metrics": ["headcount", "expenses"],
                    },
                }
            ],
        )
