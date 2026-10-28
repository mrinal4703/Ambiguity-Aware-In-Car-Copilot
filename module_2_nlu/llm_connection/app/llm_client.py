
import json
import re
from openai import OpenAI
from app.config import settings


class LLMClient:

    def __init__(self):
        self.client = OpenAI(
            api_key=settings.GROQ_API_KEY,
            base_url="https://api.groq.com/openai/v1"
        )

    def generate(self, prompt: str) -> dict:
        response = self.client.chat.completions.create(
            model="openai/gpt-oss-20b",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are an NLU engine. "
                        "Return only a valid JSON object."
                    )
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0,
            # Ask the provider for a JSON object (fix B10).
            response_format={"type": "json_object"},
        )

        content = response.choices[0].message.content

        if not content:
            raise ValueError("LLM returned an empty response")

        # Strip markdown fences if the model added them anyway (fix B10).
        fenced = re.search(r"```(?:json)?\s*(.*?)```", content, re.S)
        if fenced:
            content = fenced.group(1)

        try:
            return json.loads(content)
        except json.JSONDecodeError as e:
            raise ValueError(
                f"Invalid JSON from LLM: {e}\nResponse: {content}"
            )
