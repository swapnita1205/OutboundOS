from pydantic import BaseModel, HttpUrl


class CompanySummary(BaseModel):
    company: str
    industry: str
    description: str
    employees: str
    recent_news: list[str]
    products: list[str]
    customers: list[str]
    funding: str
    tech_stack: list[str]
    ai_signals: list[str]
    evidence_urls: list[str] = []
    evidence_snippets: list[str] = []


class ResearchAgentInput(BaseModel):
    company_name: str
    website: HttpUrl
