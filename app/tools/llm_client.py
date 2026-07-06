from openai import AsyncOpenAI
from pydantic import BaseModel

from app.utils.settings import Settings


class StructuredLLMClient:
    def __init__(self, settings: Settings) -> None:
        api_key = settings.openai_api_key.get_secret_value() if settings.openai_api_key else None
        self._client = AsyncOpenAI(api_key=api_key)
        self._model = settings.openai_model

    async def parse(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema: type[BaseModel],
    ) -> BaseModel:
        response = await self._client.beta.chat.completions.parse(
            model=self._model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format=schema,
        )
        message = response.choices[0].message
        if message.parsed is None:
            raise RuntimeError("LLM structured parse returned empty payload")
        return message.parsed
