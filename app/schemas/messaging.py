from pydantic import BaseModel, Field

from app.schemas.company_summary import CompanySummary
from app.schemas.pain_points import PainPoint
from app.schemas.persona import PersonaSelection


class MessagingAgentInput(BaseModel):
    company_summary: CompanySummary
    pain_points: list[PainPoint] = Field(default_factory=list)
    persona_selection: PersonaSelection


class OutboundMessageBundle(BaseModel):
    subject: str
    cold_email: str
    follow_up_1: str
    follow_up_2: str
    linkedin_message: str
    call_to_action: str
