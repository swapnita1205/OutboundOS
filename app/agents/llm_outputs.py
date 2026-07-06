from pydantic import BaseModel, Field

from app.schemas.icp_score import ICPScore
from app.schemas.pain_points import PainPoint
from app.schemas.persona import BuyerPersona, PersonaSelection


class ResearchLLMOutput(BaseModel):
    industry: str
    description: str
    employees: str = "unknown"
    products: list[str] = Field(default_factory=list)
    customers: list[str] = Field(default_factory=list)
    funding: str = "unknown"
    tech_stack: list[str] = Field(default_factory=list)
    ai_signals: list[str] = Field(default_factory=list)
    recent_news: list[str] = Field(default_factory=list)


class PainPointLLMOutput(BaseModel):
    top_pain_points: list[PainPoint] = Field(min_length=3, max_length=5)


class ReviewerLLMOutput(BaseModel):
    scores_hallucinations: float = Field(ge=0, le=1)
    scores_generic_language: float = Field(ge=0, le=1)
    scores_grammar: float = Field(ge=0, le=1)
    scores_unsupported_claims: float = Field(ge=0, le=1)
    scores_email_length: float = Field(ge=0, le=1)
    scores_personalization: float = Field(ge=0, le=1)
    scores_tone: float = Field(ge=0, le=1)
    decision: str
    reasons: list[str]
    action_items: list[str]


class PersonaLLMOutput(BaseModel):
    persona: BuyerPersona
    why: list[str]
    confidence: float = Field(ge=0, le=1)


AgentICPScore = ICPScore
AgentPersonaSelection = PersonaSelection
