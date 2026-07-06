from openai import AsyncOpenAI

from app.utils.settings import Settings


class OpenAIClient:
    def __init__(self, settings: Settings) -> None:
        api_key = settings.openai_api_key.get_secret_value() if settings.openai_api_key else None
        self._client = AsyncOpenAI(api_key=api_key)
        self._model = settings.openai_model

    @property
    def client(self) -> AsyncOpenAI:
        return self._client

    @property
    def model(self) -> str:
        return self._model
