import json
from groq import Groq
from app.config import GROQ_API_KEY, LLAMA_MODEL


class BaseAgent:
    def __init__(self):
        self.client = Groq(api_key=GROQ_API_KEY)

    def run(self, system_prompt: str, payload: dict) -> dict:
        response = self.client.chat.completions.create(
            model=LLAMA_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(payload)}
            ],
            response_format={"type": "json_object"},
            temperature=0
        )

        return json.loads(response.choices[0].message.content)
