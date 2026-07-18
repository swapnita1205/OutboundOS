import logging
import re
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

from app.tools.base import RetryConfig, with_retries
from app.utils.settings import Settings

logger = logging.getLogger("outboundos.tools.firecrawl")

FIRECRAWL_SCRAPE_URL = "https://api.firecrawl.dev/v1/scrape"
DEFAULT_TIMEOUT = 45.0
MAX_DISCOVERED_PAGES = 9

_NOT_FOUND_PATTERNS = (
    "page not found",
    "404",
    "does not exist",
    "may have been moved",
    "page you are looking for",
    "we can't find that page",
    "we can not find that page",
    "content not found",
)

_LINK_PATTERN = re.compile(r"\[([^\]]*)\]\((https?://[^\s)]+)\)")

_SKIP_LINK_SUBSTRINGS = (
    "mailto:",
    "tel:",
    "twitter.com",
    "x.com",
    "linkedin.com",
    "facebook.com",
    "instagram.com",
    "youtube.com",
    "youtu.be",
    "vimeo.com",
    ".png",
    ".jpg",
    ".jpeg",
    ".svg",
    ".pdf",
    ".gif",
    ".css",
    ".js",
)

_PAGE_KEYWORDS = (
    "product",
    "solution",
    "platform",
    "about",
    "company",
    "team",
    "customer",
    "case-stud",
    "casestud",
    "use-case",
    "usecase",
    "pricing",
    "blog",
    "docs",
    "documentation",
    "career",
    "job",
    "contact",
    "security",
    "compliance",
    "partner",
)


def _looks_like_not_found(markdown: str) -> bool:
    if not markdown:
        return False
    lowered = markdown.lower()[:300]
    return any(pattern in lowered for pattern in _NOT_FOUND_PATTERNS)


def discover_internal_links(markdown: str, base_url: str, limit: int = MAX_DISCOVERED_PAGES) -> list[str]:
    """Find real same-domain links from a homepage's own markdown, ranked by relevance.

    This replaces blindly guessing a fixed slug list (/about, /pricing, ...) which 404s on
    any site that doesn't happen to use those exact paths.
    """
    base_domain = urlparse(base_url).netloc.replace("www.", "")
    base_normalized = base_url.rstrip("/")
    seen: set[str] = set()
    scored: list[tuple[int, str]] = []

    for _text, href in _LINK_PATTERN.findall(markdown):
        lowered_href = href.lower()
        if any(bad in lowered_href for bad in _SKIP_LINK_SUBSTRINGS):
            continue
        parsed = urlparse(href)
        if parsed.netloc.replace("www.", "") != base_domain:
            continue
        normalized = href.split("#")[0].rstrip("/")
        if not normalized or normalized == base_normalized or normalized in seen:
            continue
        seen.add(normalized)
        score = sum(1 for keyword in _PAGE_KEYWORDS if keyword in normalized.lower())
        scored.append((score, normalized))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [url for _, url in scored[:limit]]


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
    if _looks_like_not_found(markdown):
        return FirecrawlScrapeResult(url=url, markdown="", success=False, error="not_found_page")
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
    homepage_result = await scrape_url(base, settings)
    results: list[FirecrawlScrapeResult] = [homepage_result]

    discovered = (
        discover_internal_links(homepage_result.markdown, base)
        if homepage_result.success
        else []
    )

    # If the homepage's own markdown didn't yield enough real links (e.g. a JS nav that
    # didn't render), fall back to the generic slug guesses to fill the remaining slots.
    if len(discovered) < 4:
        existing = {url.rstrip("/") for url in discovered}
        for path, _ in candidate_paths():
            if not path:
                continue
            target = urljoin(base if base.endswith("/") else base + "/", path.lstrip("/"))
            if target.rstrip("/") not in existing:
                discovered.append(target)
                existing.add(target.rstrip("/"))
            if len(discovered) >= MAX_DISCOVERED_PAGES:
                break

    for target in discovered[:MAX_DISCOVERED_PAGES]:
        result = await scrape_url(target, settings)
        results.append(result)
    return results
