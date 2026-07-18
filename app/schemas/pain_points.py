from pydantic import BaseModel, Field

from app.schemas.company_summary import CompanySummary
from app.schemas.seller_profile import SellerProfile


class PainPointAgentInput(BaseModel):
    company_summary: CompanySummary
    hiring_trends: list[str] = Field(default_factory=list)
    seller_profile: SellerProfile = Field(default_factory=SellerProfile)


class PainPoint(BaseModel):
    description: str
    evidence: list[str]
    confidence: float = Field(ge=0, le=1)
    recommended_messaging_angle: str


class PainPointOutput(BaseModel):
    top_pain_points: list[PainPoint] = Field(min_length=5, max_length=5)
