import logging
import re
from dataclasses import dataclass

import requests
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from app.core.config import settings

logger = logging.getLogger(__name__)

# Characters/sequences that are common prompt-injection vectors.
_INJECTION_PATTERNS = re.compile(
    r"(ignore\s+(previous|prior|above|all)\s+instructions?|"
    r"system\s*prompt|forget\s+everything|you\s+are\s+now|"
    r"act\s+as\s+(?:an?\s+)?(?:unrestricted|jailbreak|DAN)|"
    r"</?(system|user|assistant)>)",
    re.IGNORECASE,
)


class LLMUnavailableError(RuntimeError):
    pass


@dataclass
class LLMResult:
    text: str
    duration_ms: int
    input_tokens: int | None
    output_tokens: int | None


def sanitize_input(text: str) -> str:
    """Strip prompt-injection patterns from user-supplied text before it
    enters an LLM prompt. Replaces matched sequences with [FILTERED]."""
    return _INJECTION_PATTERNS.sub("[FILTERED]", text)


@retry(
    retry=retry_if_exception_type(LLMUnavailableError),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    reraise=True,
)
def generate(prompt: str) -> LLMResult:
    try:
        response = requests.post(
            f"{settings.ollama_base_url}/api/generate",
            json={"model": settings.ollama_model, "prompt": prompt, "stream": False},
            timeout=180,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise LLMUnavailableError(
            f"Could not reach local LLM (Ollama) at {settings.ollama_base_url} "
            f"with model '{settings.ollama_model}'. Is `ollama serve` running? ({exc})"
        ) from exc

    data = response.json()
    return LLMResult(
        text=data["response"].strip(),
        duration_ms=round(data.get("eval_duration", 0) / 1_000_000),
        input_tokens=data.get("prompt_eval_count"),
        output_tokens=data.get("eval_count"),
    )


def ollama_available() -> bool:
    """Quick liveness check — used by health endpoint and LLM decomposer fallback."""
    try:
        r = requests.get(f"{settings.ollama_base_url}/api/tags", timeout=3)
        return r.status_code == 200
    except Exception:
        return False
