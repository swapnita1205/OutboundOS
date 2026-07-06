from pydantic import BaseModel, Field

from app.schemas.company_summary import CompanySummary


class ICPAgentInput(BaseModel):
    company_summary: CompanySummary


class ICPScore(BaseModel):
    score: float = Field(ge=0, le=100)
    reasons: list[str]
    ideal_persona: str
    risk_flags: list[str]
    confidence: float = Field(ge=0, le=1)
