from pydantic import BaseModel, HttpUrl

from app.tools.base import execute_tool, with_retries
from app.tools.company_evidence import collect_company_evidence
from app.tools.firecrawl_client import scrape_url
from app.tools.web_search import search_web
from app.utils.settings import get_settings


class ScrapeCompanyWebsiteInput(BaseModel):
    url: HttpUrl


class ScrapeCompanyWebsiteOutput(BaseModel):
    company_name: str
    summary: str
    source_url: HttpUrl


class SearchCompanyNewsInput(BaseModel):
    company_name: str
    max_results: int = 5


class NewsItem(BaseModel):
    title: str
    source: str
    published_date: str
    url: HttpUrl


class SearchCompanyNewsOutput(BaseModel):
    company_name: str
    results: list[NewsItem]


class SummarizeCompanyInput(BaseModel):
    company_name: str
    website_summary: str
    recent_news_titles: list[str]


class SummarizeCompanyOutput(BaseModel):
    company_name: str
    company_summary: str
    key_facts: list[str]


@with_retries("scrape_company_website")
async def scrape_company_website(
    tool_input: ScrapeCompanyWebsiteInput,
) -> ScrapeCompanyWebsiteOutput:
    async def _handler() -> ScrapeCompanyWebsiteOutput:
        settings = get_settings()
        result = await scrape_url(str(tool_input.url), settings)
        summary = " ".join(result.markdown.split())[:2000] if result.markdown else ""
        if not summary:
            summary = f"Website scraped for {tool_input.url.host}"
        return ScrapeCompanyWebsiteOutput(
            company_name=tool_input.url.host or "unknown",
            summary=summary,
            source_url=tool_input.url,
        )

    return await execute_tool("scrape_company_website", _handler)


@with_retries("search_company_news")
async def search_company_news(tool_input: SearchCompanyNewsInput) -> SearchCompanyNewsOutput:
    async def _handler() -> SearchCompanyNewsOutput:
        settings = get_settings()
        hits = await search_web(
            f"{tool_input.company_name} recent news",
            settings,
            max_results=tool_input.max_results,
        )
        items = [
            NewsItem(
                title=hit.title,
                source=hit.url,
                published_date="unknown",
                url=hit.url,
            )
            for hit in hits
        ]
        if not items:
            items = [
                NewsItem(
                    title=f"Recent update about {tool_input.company_name}",
                    source="search",
                    published_date="unknown",
                    url="https://example.com/news/placeholder",
                )
            ]
        return SearchCompanyNewsOutput(company_name=tool_input.company_name, results=items)

    return await execute_tool("search_company_news", _handler)


@with_retries("summarize_company")
async def summarize_company(tool_input: SummarizeCompanyInput) -> SummarizeCompanyOutput:
    async def _handler() -> SummarizeCompanyOutput:
        key_facts = [tool_input.website_summary, *tool_input.recent_news_titles[:3]]
        key_facts = [fact for fact in key_facts if fact]
        return SummarizeCompanyOutput(
            company_name=tool_input.company_name,
            company_summary=tool_input.website_summary or f"Summary for {tool_input.company_name}",
            key_facts=key_facts,
        )

    return await execute_tool("summarize_company", _handler)


async def collect_research_evidence(company_name: str, website: str) -> tuple[str, list[str]]:
    settings = get_settings()
    bundle = await collect_company_evidence(company_name, website, settings)
    snippets = [item.snippet for item in bundle.evidence if item.snippet]
    description = snippets[0] if snippets else f"No evidence for {company_name}"
    return description, snippets
