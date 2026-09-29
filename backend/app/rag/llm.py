from dataclasses import dataclass

import requests

from app.core.config import settings


class LLMUnavailableError(RuntimeError):
    pass


@dataclass
class LLMResult:
    text: str
    duration_ms: int
    input_tokens: int | None
    output_tokens: int | None


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
    # eval_duration is nanoseconds; prompt_eval_count/eval_count are token counts
    return LLMResult(
        text=data["response"].strip(),
        duration_ms=round(data.get("eval_duration", 0) / 1_000_000),
        input_tokens=data.get("prompt_eval_count"),
        output_tokens=data.get("eval_count"),
    )
