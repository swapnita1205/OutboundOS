import logging
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

from app.tools.base import RetryConfig, with_retries
from app.utils.settings import Settings

logger = logging.getLogger("outboundos.tools.firecrawl")

FIRECRAWL_SCRAPE_URL = "https://api.firecrawl.dev/v1/scrape"
DEFAULT_TIMEOUT = 45.0


class FirecrawlScrapeResult:
    __slots__ = ("url", "markdown", "success", "error")

    def __init__(self, url: str, markdown: str, success: bool, error: str | None = None) -> None:
        self.url = url
        self.markdown = markdown
        self.success = success
        self.error = error


@with_retries("firecrawl_scrape", retry_config=RetryConfig(attempts=2, initial_delay_seconds=1.0))
async def scrape_url(url: str, settings: Settings) -> FirecrawlScrapeResult:
    api_key = settings.firecrawl_api_key.get_secret_value() if settings.firecrawl_api_key else None
    if not api_key:
        return FirecrawlScrapeResult(url=url, markdown="", success=False, error="missing_api_key")

    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        response = await client.post(
            FIRECRAWL_SCRAPE_URL,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"url": url, "formats": ["markdown"]},
        )
        if response.status_code >= 400:
            return FirecrawlScrapeResult(
                url=url,
                markdown="",
                success=False,
                error=f"http_{response.status_code}",
            )
        payload: dict[str, Any] = response.json()

    data = payload.get("data", {})
    markdown = data.get("markdown", "") or ""
    return FirecrawlScrapeResult(url=url, markdown=markdown[:8000], success=bool(markdown))


def normalize_website(website: str) -> str:
    parsed = urlparse(website if "://" in website else f"https://{website}")
    if not parsed.scheme:
        return f"https://{website}"
    return website if "://" in website else f"https://{website}"


def candidate_paths() -> list[tuple[str, str]]:
    return [
        ("", "website"),
        ("/about", "website"),
        ("/about-us", "website"),
        ("/company", "website"),
        ("/pricing", "website"),
        ("/customers", "website"),
        ("/case-studies", "website"),
        ("/use-cases", "website"),
        ("/blog", "blog"),
        ("/docs", "docs"),
        ("/careers", "careers"),
        ("/jobs", "careers"),
    ]


async def scrape_company_pages(
    website: str,
    settings: Settings,
) -> list[FirecrawlScrapeResult]:
    base = normalize_website(website)
    results: list[FirecrawlScrapeResult] = []
    for path, _ in candidate_paths():
        target = urljoin(base if base.endswith("/") else base + "/", path.lstrip("/"))
        if path == "":
            target = base
        result = await scrape_url(target, settings)
        results.append(result)
    return results
