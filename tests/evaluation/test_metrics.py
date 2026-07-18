from app.evaluation.metrics import (
    SEMANTIC_FLOOR_T,
    SEMANTIC_MATCH_T,
    _email_quality_score,
    _expected_reviewer_decision,
    _pain_point_accuracy,
    _persona_accuracy,
    _reviewer_agreement,
    _semantic_band,
)
from app.evaluation.semantic import SemanticMatcher
from app.schemas.reviewer import ReviewerCritique, ReviewerScores


class _FakeSemanticMatcher(SemanticMatcher):
    """Returns a fixed similarity for every pair, without touching the API."""

    def __init__(self, similarity: float) -> None:
        self._similarity = similarity

    @property
    def enabled(self) -> bool:
        return True

    async def similarity_matrix(
        self,
        rows: list[str],
        cols: list[str],
    ) -> list[list[float]] | None:
        return [[self._similarity for _ in cols] for _ in rows]


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


async def test_email_quality_detects_company_pain_and_cta() -> None:
    score = await _email_quality_score(
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


def test_semantic_band_maps_similarity_to_credit() -> None:
    assert _semantic_band(SEMANTIC_MATCH_T) == 1.0
    assert _semantic_band(SEMANTIC_FLOOR_T) == 0.0
    midpoint = (SEMANTIC_MATCH_T + SEMANTIC_FLOOR_T) / 2
    assert abs(_semantic_band(midpoint) - 0.5) < 1e-9


async def test_pain_point_accuracy_token_only_misses_paraphrase() -> None:
    score = await _pain_point_accuracy(
        predicted=["Teams struggle with fragmented information silos"],
        truth=["Knowledge and workflows scattered across many disconnected tools"],
        semantic=None,
    )
    assert score == 0.0


async def test_pain_point_accuracy_semantic_credits_paraphrase() -> None:
    score = await _pain_point_accuracy(
        predicted=["Teams struggle with fragmented information silos"],
        truth=["Knowledge and workflows scattered across many disconnected tools"],
        semantic=_FakeSemanticMatcher(similarity=0.75),
    )
    assert score == 1.0


async def test_pain_point_accuracy_low_similarity_gets_no_credit() -> None:
    score = await _pain_point_accuracy(
        predicted=["Something entirely unrelated"],
        truth=["Knowledge and workflows scattered across many disconnected tools"],
        semantic=_FakeSemanticMatcher(similarity=0.1),
    )
    assert score == 0.0


async def test_pain_point_accuracy_token_match_needs_no_semantic() -> None:
    score = await _pain_point_accuracy(
        predicted=["Manual outbound research slows sales teams"],
        truth=["Manual research slows outbound sales"],
        semantic=None,
    )
    assert score == 1.0


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
