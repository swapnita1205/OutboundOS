import logging
from dataclasses import dataclass
from urllib.parse import urlparse

from app.dataset.schemas import EvidenceItem
from app.tools.firecrawl_client import normalize_website, scrape_company_pages
from app.tools.web_search import search_web
from app.utils.settings import Settings

logger = logging.getLogger("outboundos.tools.company_evidence")


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


def _snippet_from_markdown(markdown: str, limit: int = 400) -> str:
    cleaned = " ".join(markdown.split())
    return cleaned[:limit]


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
