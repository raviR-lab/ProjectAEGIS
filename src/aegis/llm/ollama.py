import requests

from aegis import config


class OllamaClient:
    """Local LLM engine client (Ollama)."""

    def __init__(self, base_url: str | None = None, model: str | None = None) -> None:
        self.base_url = (base_url or config.OLLAMA_BASE_URL).rstrip("/")
        self.model = model or config.OLLAMA_MODEL

    def list_models(self) -> list[str]:
        resp = requests.get(f"{self.base_url}/api/tags", timeout=10)
        resp.raise_for_status()
        return [m["name"] for m in resp.json().get("models", [])]

    def is_model_available(self) -> bool:
        return self.model in self.list_models()

    def generate(self, prompt: str, *, temperature: float = 0.2, max_tokens: int = 512) -> str:
        resp = requests.post(
            f"{self.base_url}/api/generate",
            json={"model": self.model, "prompt": prompt, "stream": False,
                  "options": {"temperature": temperature, "num_predict": max_tokens}},
            timeout=120,
        )
        resp.raise_for_status()
        return resp.json().get("response", "")
