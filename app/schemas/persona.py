from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.company_summary import CompanySummary
from app.schemas.seller_profile import SellerProfile

BuyerPersona = Literal[
    "Founder",
    "CEO",
    "CTO",
    "VP Engineering",
    "Head of AI",
    "VP Sales",
    "RevOps",
    "Product",
]


class PersonaAgentInput(BaseModel):
    company_summary: CompanySummary
    icp_score: float | None = Field(default=None, ge=0, le=100)
    seller_profile: SellerProfile = Field(default_factory=SellerProfile)


class PersonaSelection(BaseModel):
    persona: BuyerPersona
    why: list[str]
    confidence: float = Field(ge=0, le=1)
