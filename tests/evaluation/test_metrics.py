from app.evaluation.metrics import (
    _email_quality_score,
    _expected_reviewer_decision,
    _persona_accuracy,
    _reviewer_agreement,
)
from app.schemas.reviewer import ReviewerCritique, ReviewerScores


def test_persona_accuracy_role_family_match() -> None:
    score = _persona_accuracy(
        "VP Sales",
        "Go-to-market teams including marketers and sales professionals",
    )
    assert score == 1.0


def test_persona_accuracy_engineering_match() -> None:
    score = _persona_accuracy(
        "CTO",
        "Developers and DevOps engineers building cloud infrastructure",
    )
    assert score == 1.0


def test_persona_accuracy_partial_without_family_overlap() -> None:
    score = _persona_accuracy("Product", "Restaurant owners and operators")
    assert score <= 0.5


def test_email_quality_detects_company_pain_and_cta() -> None:
    score = _email_quality_score(
        cold_email=(
            "Hi Stripe team, managing global payment complexity is tough for finance teams. "
            "Open to a quick call next week?"
        ),
        company_name="Stripe",
        truth_pain_points=[
            "Challenges integrating global payment processing efficiently across borders",
        ],
        reference_outreach="Stripe powers global payment infrastructure for finance teams.",
    )
    assert score >= 0.6


def test_expected_reviewer_decision_approve_on_strong_email() -> None:
    decision = _expected_reviewer_decision(
        research_accuracy=1.0,
        email_quality=0.75,
        threshold=0.75,
    )
    assert decision == "APPROVE"


def test_reviewer_agreement_partial_credit_for_borderline_approve() -> None:
    critique = ReviewerCritique(
        scores=ReviewerScores(
            hallucinations=0.8,
            generic_language=0.8,
            grammar=0.9,
            unsupported_claims=0.8,
            email_length=0.9,
            personalization=0.8,
            tone=0.85,
        ),
        average_score=0.84,
        decision="APPROVE",
        reasons=["Looks good"],
        action_items=[],
    )
    agreement = _reviewer_agreement(
        critique=critique,
        research_accuracy=1.0,
        email_quality=0.4,
        threshold=0.75,
    )
    assert agreement == 0.5
