from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.company_summary import CompanySummary
from app.schemas.messaging import OutboundMessageBundle
from app.schemas.pain_points import PainPoint
from app.schemas.persona import PersonaSelection

ReviewerDecision = Literal["APPROVE", "REWRITE", "RESEARCH"]


class ReviewerAgentInput(BaseModel):
    message_bundle: OutboundMessageBundle
    company_summary: CompanySummary
    pain_points: list[PainPoint] = Field(default_factory=list)
    persona_selection: PersonaSelection
    threshold: float = Field(default=0.7, ge=0, le=1)


class ReviewerScores(BaseModel):
    hallucinations: float = Field(ge=0, le=1)
    generic_language: float = Field(ge=0, le=1)
    grammar: float = Field(ge=0, le=1)
    unsupported_claims: float = Field(ge=0, le=1)
    email_length: float = Field(ge=0, le=1)
    personalization: float = Field(ge=0, le=1)
    tone: float = Field(ge=0, le=1)


class ReviewerCritique(BaseModel):
    scores: ReviewerScores
    average_score: float = Field(ge=0, le=1)
    decision: ReviewerDecision
    reasons: list[str]
    action_items: list[str]
