from app.tools.llm_client import StructuredLLMClient
from app.utils.settings import Settings, get_settings


def get_agent_llm(settings: Settings | None = None) -> StructuredLLMClient:
    return StructuredLLMClient(settings or get_settings())


def live_agents_enabled(settings: Settings | None = None) -> bool:
    resolved = settings or get_settings()
    if resolved.benchmark_mode:
        return False
    return bool(resolved.openai_api_key)
