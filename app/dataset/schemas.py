from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field


class SeedCompany(BaseModel):
    company_name: str
    website: str
    category: str | None = None
    notes: str | None = None


class EvidenceItem(BaseModel):
    url: str
    snippet: str
    source_type: Literal["website", "blog", "docs", "news", "careers", "search"]


class PainPointExtraction(BaseModel):
    description: str
    evidence_urls: list[str] = Field(default_factory=list)
    evidence_snippets: list[str] = Field(default_factory=list)


class LLMExtractionOutput(BaseModel):
    industry: str
    short_description: str
    target_persona: str
    pain_points: list[PainPointExtraction] = Field(min_length=1, max_length=5)
    confidence_score: float = Field(ge=0, le=1)
    persona_confidence: float = Field(ge=0, le=1)


class ReferenceOutreachOutput(BaseModel):
    email_body: str


class OutreachValidation(BaseModel):
    email_body: str
    word_count: int
    includes_company_fact: bool
    includes_pain_point: bool
    unsupported_claims: list[str] = Field(default_factory=list)


class EnrichmentBundle(BaseModel):
    company_name: str
    website: str
    homepage_scraped: bool
    evidence: list[EvidenceItem] = Field(default_factory=list)
    scrape_errors: list[str] = Field(default_factory=list)


class OutboundBenchRecord(BaseModel):
    company_name: str
    website: str
    industry: str
    short_description: str
    target_persona: str
    pain_points: list[str]
    evidence_urls: list[str]
    evidence_snippets: list[str]
    reference_outreach: str
    confidence_score: float = Field(ge=0, le=1)
    needs_human_review: bool
    source_quality_score: float = Field(ge=0, le=1)
    generated_at: datetime
    validation_reasons: list[str] = Field(default_factory=list)

    @staticmethod
    def now() -> datetime:
        return datetime.now(tz=UTC)
