import logging
import re
from dataclasses import dataclass
from urllib.parse import urlparse

from app.dataset.schemas import EvidenceItem
from app.tools.firecrawl_client import normalize_website, scrape_company_pages
from app.tools.web_search import search_web
from app.utils.settings import Settings

logger = logging.getLogger("outboundos.tools.company_evidence")

_IMAGE_MARKDOWN_PATTERN = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_LINK_MARKDOWN_PATTERN = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_JUNK_LINE_SUBSTRINGS = (
    "vimeo",
    "youtube.com",
    "video thumbnail",
    "thumbnail",
    ".mp4",
    "cloudfront.net",
)


@dataclass(slots=True)
class CompanyEvidence:
    company_name: str
    website: str
    homepage_scraped: bool
    evidence: list[EvidenceItem]
    scrape_errors: list[str]


def _classify_source(url: str, source_hint: str) -> str:
    lowered = url.lower()
    if "career" in lowered or "jobs" in lowered or source_hint == "careers":
        return "careers"
    if "/blog" in lowered or source_hint == "blog":
        return "blog"
    if "/docs" in lowered or source_hint == "docs":
        return "docs"
    if any(token in lowered for token in ("techcrunch", "news", "reuters", "bloomberg")):
        return "news"
    return "website"


def _snippet_from_markdown(markdown: str, limit: int = 500) -> str:
    """Build a snippet from the first substantive lines, skipping embeds/nav/boilerplate.

    A flat "first N characters" cut can accidentally grab a video-embed caption or a bare
    nav-link list if that happens to be what a page's markdown leads with, starving the LLM
    of the real body copy that sits just below it. Instead, walk lines and keep only ones
    that read like actual prose.
    """
    without_images = _IMAGE_MARKDOWN_PATTERN.sub(" ", markdown)
    substantive: list[str] = []
    total_len = 0
    for raw_line in without_images.split("\n"):
        line = raw_line.strip()
        if not line:
            continue
        if any(junk in line.lower() for junk in _JUNK_LINE_SUBSTRINGS):
            continue
        text_only = _LINK_MARKDOWN_PATTERN.sub(r"\1", line).strip()
        if len(text_only.split()) < 5:
            continue
        substantive.append(text_only)
        total_len += len(text_only)
        if total_len >= limit:
            break

    if not substantive:
        cleaned = " ".join(without_images.split())
        return cleaned[:limit]

    return " ".join(substantive)[:limit]


def format_evidence_block(evidence: list[EvidenceItem]) -> str:
    lines: list[str] = []
    for item in evidence:
        lines.append(f"- URL: {item.url}\n  Type: {item.source_type}\n  Snippet: {item.snippet}")
    return "\n".join(lines)


async def collect_company_evidence(
    company_name: str,
    website: str,
    settings: Settings,
) -> CompanyEvidence:
    normalized = normalize_website(website)
    evidence: list[EvidenceItem] = []
    scrape_errors: list[str] = []
    homepage_scraped = False

    scrape_results = await scrape_company_pages(normalized, settings)
    for idx, result in enumerate(scrape_results):
        if result.success and result.markdown:
            if idx == 0:
                homepage_scraped = True
            evidence.append(
                EvidenceItem(
                    url=result.url,
                    snippet=_snippet_from_markdown(result.markdown),
                    source_type=_classify_source(result.url, "website"),
                )
            )
        elif result.error:
            scrape_errors.append(f"{result.url}: {result.error}")

    domain = urlparse(normalized).netloc
    search_queries = [
        f"{company_name} recent news",
        f"{company_name} careers hiring site:{domain}",
    ]
    for query in search_queries:
        try:
            results = await search_web(query, settings, max_results=3)
            for hit in results:
                source_type = "careers" if "career" in query.lower() else "news"
                evidence.append(
                    EvidenceItem(
                        url=hit.url,
                        snippet=hit.snippet or hit.title,
                        source_type=source_type,
                    )
                )
        except Exception as exc:  # noqa: BLE001
            scrape_errors.append(f"search_failed:{query}:{exc}")
            logger.warning("search_failed", extra={"company": company_name, "query": query})

    deduped: dict[str, EvidenceItem] = {}
    for item in evidence:
        if item.url and item.url not in deduped:
            deduped[item.url] = item

    return CompanyEvidence(
        company_name=company_name,
        website=normalized,
        homepage_scraped=homepage_scraped,
        evidence=list(deduped.values()),
        scrape_errors=scrape_errors,
    )
