from typing import Literal, NotRequired, TypedDict

from app.schemas.company_summary import CompanySummary
from app.schemas.icp_score import ICPScore
from app.schemas.messaging import OutboundMessageBundle
from app.schemas.pain_points import PainPointOutput
from app.schemas.persona import PersonaSelection
from app.schemas.reviewer import ReviewerCritique
from app.schemas.seller_profile import SellerProfile
from app.utils.seller_profile import get_seller_profile

WorkflowDecision = Literal["APPROVE", "REWRITE", "RESEARCH"]


class OutboundWorkflowState(TypedDict):
    company_name: str
    website: str
    hiring_trends: list[str]
    seller_profile: SellerProfile
    quality_threshold: float
    max_iterations: int
    iteration_count: int
    review_fail_count: int

    company_summary: NotRequired[CompanySummary]
    icp_score: NotRequired[ICPScore]
    pain_points: NotRequired[PainPointOutput]
    persona_selection: NotRequired[PersonaSelection]
    message_bundle: NotRequired[OutboundMessageBundle]
    reviewer_critique: NotRequired[ReviewerCritique]

    quality_score: float
    reviewer_decision: WorkflowDecision

    total_latency_ms: float
    total_token_usage: int
    total_cost_usd: float
    reasoning_trace: list[str]


def create_initial_state(
    company_name: str,
    website: str,
    *,
    hiring_trends: list[str] | None = None,
    seller_profile: SellerProfile | None = None,
    quality_threshold: float = 0.7,
    max_iterations: int = 4,
) -> OutboundWorkflowState:
    return OutboundWorkflowState(
        company_name=company_name,
        website=website,
        hiring_trends=hiring_trends or [],
        seller_profile=seller_profile or get_seller_profile(),
        quality_threshold=quality_threshold,
        max_iterations=max_iterations,
        iteration_count=0,
        review_fail_count=0,
        quality_score=0.0,
        reviewer_decision="REWRITE",
        total_latency_ms=0.0,
        total_token_usage=0,
        total_cost_usd=0.0,
        reasoning_trace=[],
    )
