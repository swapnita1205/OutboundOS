import logging
from typing import Any

import httpx
from pydantic import BaseModel

from app.tools.base import RetryConfig, with_retries
from app.utils.settings import Settings

logger = logging.getLogger("outboundos.tools.web_search")

TAVILY_URL = "https://api.tavily.com/search"
EXA_URL = "https://api.exa.ai/search"
DEFAULT_TIMEOUT = 30.0


class WebSearchResult(BaseModel):
    url: str
    title: str
    snippet: str


@with_retries("tavily_search", retry_config=RetryConfig(attempts=3, initial_delay_seconds=0.5))
async def tavily_search(
    query: str,
    settings: Settings,
    *,
    max_results: int = 5,
) -> list[WebSearchResult]:
    api_key = settings.tavily_api_key.get_secret_value() if settings.tavily_api_key else None
    if not api_key:
        raise ValueError("TAVILY_API_KEY is not configured")

    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        response = await client.post(
            TAVILY_URL,
            json={
                "api_key": api_key,
                "query": query,
                "max_results": max_results,
                "include_answer": False,
            },
        )
        response.raise_for_status()
        payload: dict[str, Any] = response.json()

    results: list[WebSearchResult] = []
    for item in payload.get("results", []):
        results.append(
            WebSearchResult(
                url=item.get("url", ""),
                title=item.get("title", ""),
                snippet=item.get("content", "")[:500],
            )
        )
    return results


@with_retries("exa_search", retry_config=RetryConfig(attempts=3, initial_delay_seconds=0.5))
async def exa_search(
    query: str,
    settings: Settings,
    *,
    max_results: int = 5,
) -> list[WebSearchResult]:
    api_key = settings.exa_api_key.get_secret_value() if settings.exa_api_key else None
    if not api_key:
        raise ValueError("EXA_API_KEY is not configured")

    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        response = await client.post(
            EXA_URL,
            headers={"x-api-key": api_key, "Content-Type": "application/json"},
            json={"query": query, "numResults": max_results, "useAutoprompt": True},
        )
        response.raise_for_status()
        payload: dict[str, Any] = response.json()

    results: list[WebSearchResult] = []
    for item in payload.get("results", []):
        results.append(
            WebSearchResult(
                url=item.get("url", ""),
                title=item.get("title", ""),
                snippet=(item.get("text") or item.get("snippet") or "")[:500],
            )
        )
    return results


async def search_web(
    query: str,
    settings: Settings,
    *,
    max_results: int = 5,
) -> list[WebSearchResult]:
    if settings.tavily_api_key:
        return await tavily_search(query, settings, max_results=max_results)
    if settings.exa_api_key:
        return await exa_search(query, settings, max_results=max_results)
    raise ValueError("Configure TAVILY_API_KEY or EXA_API_KEY for web search")
