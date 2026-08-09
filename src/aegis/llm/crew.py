"""CrewAI LLM factory - routes every agent to the local Ollama engine."""

from crewai import LLM

from aegis import config


def build_llm(*, temperature: float = 0.2, max_tokens: int = 512) -> LLM:
    return LLM(
        model=f"ollama/{config.OLLAMA_MODEL}",
        base_url=config.OLLAMA_BASE_URL,
        api_key="ollama",
        temperature=temperature,
        max_tokens=max_tokens,
    )
