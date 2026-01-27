import os
import json
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

class BaseAgent:
    def __init__(self):
        self.client = None

    def _get_client(self):
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise RuntimeError("GROQ_API_KEY not set")
        if self.client is None:
            self.client = Groq(api_key=api_key)
        return self.client

    def run(self, system_prompt: str, payload: dict) -> dict:
        client = self._get_client()

        response = client.chat.completions.create(
            model=os.getenv("LLAMA_MODEL", "llama-3.1-8b-instant"),
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(payload)}
            ],
            response_format={"type": "json_object"},
            temperature=0
        )

        return json.loads(response.choices[0].message.content)
