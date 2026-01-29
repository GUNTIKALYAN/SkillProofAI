from typing import Optional
from groq import Groq

from app.config import GROQ_API_KEY, LLAMA_MODEL, validate_llm_config


class LLMClient:
    """
    Thin wrapper around Groq LLM.
    Safe for CI, tests, and Docker.
    """

    def __init__(self, model: Optional[str] = None):
        self.model = model or LLAMA_MODEL
        self._client: Optional[Groq] = None

    def _get_client(self) -> Groq:
        """
        Lazy initialization so app can boot without API key.
        """
        validate_llm_config()

        if self._client is None:
            self._client = Groq(api_key=GROQ_API_KEY)

        return self._client

    def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 800,
    ) -> str:
        """
        Generate a single completion.
        """
        client = self._get_client()

        response = client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )

        return response.choices[0].message.content.strip()
