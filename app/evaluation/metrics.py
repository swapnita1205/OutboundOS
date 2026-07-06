import re

from app.evaluation.models import EvaluationRecord, EvaluationSample
from app.graph.state import OutboundWorkflowState
from app.schemas.reviewer import ReviewerCritique, ReviewerDecision

PERSONA_FAMILY_KEYWORDS: dict[str, set[str]] = {
    "executive": {"ceo", "founder", "executive", "leadership", "owner", "president"},
    "sales": {"sales", "revenue", "revops", "account", "sdr", "seller", "gtm"},
    "marketing": {"marketing", "marketer", "demand", "brand", "engagement", "campaign"},
    "engineering": {
        "engineering",
        "engineer",
        "developer",
        "devops",
        "cto",
        "technical",
        "platform",
    },
    "product": {"product", "pm"},
    "finance": {"finance", "cfo", "accounting", "treasury", "corporate"},
    "security": {"security", "ciso", "cybersecurity", "iam"},
    "operations": {"operations", "ops", "hr", "workforce", "service", "support"},
    "customer": {"customer", "success", "support", "crm", "service"},
    "data": {"data", "analytics", "scientist", "analyst", "intelligence"},
    "ai": {"ai", "ml", "machine", "learning"},
}

BUYER_PERSONA_FAMILY: dict[str, set[str]] = {
    "Founder": {"executive"},
    "CEO": {"executive"},
    "CTO": {"engineering"},
    "VP Engineering": {"engineering"},
    "Head of AI": {"ai", "engineering"},
    "VP Sales": {"sales"},
    "RevOps": {"sales"},
    "Product": {"product"},
}


def score_record(sample: EvaluationSample, result: OutboundWorkflowState) -> EvaluationRecord:
    company_summary = result["company_summary"]
    icp = result["icp_score"]
    persona = result["persona_selection"]
    pain_points = result["pain_points"].top_pain_points
    critique = result["reviewer_critique"]
    cold_email = result["message_bundle"].cold_email
    threshold = result.get("quality_threshold", 0.7)

    research_accuracy = _label_similarity(
        company_summary.industry,
        sample.ground_truth.industry,
    )
    icp_accuracy = _distance_score(icp.score, sample.ground_truth.icp_target)
    persona_accuracy = _persona_accuracy(persona.persona, sample.ground_truth.persona)
    pain_point_accuracy = _pain_overlap(
        predicted=[item.description for item in pain_points],
        truth=sample.ground_truth.pain_points,
    )
    email_similarity = _email_quality_score(
        cold_email=cold_email,
        company_name=sample.company_name,
        truth_pain_points=sample.ground_truth.pain_points,
        reference_outreach=sample.ground_truth.reference_outreach,
    )
    reviewer_agreement = _reviewer_agreement(
        critique=critique,
        research_accuracy=research_accuracy,
        email_quality=email_similarity,
        threshold=threshold,
    )

    return EvaluationRecord(
        company_name=sample.company_name,
        research_accuracy=research_accuracy,
        icp_accuracy=icp_accuracy,
        persona_accuracy=persona_accuracy,
        pain_point_accuracy=pain_point_accuracy,
        reviewer_agreement=reviewer_agreement,
        email_similarity=email_similarity,
        latency_ms=result["total_latency_ms"],
        cost_usd=result["total_cost_usd"],
        tokens=result["total_token_usage"],
    )


def _tokenize(text: str) -> set[str]:
    return {word for word in re.findall(r"[a-z0-9]+", text.lower()) if len(word) > 2}


def _label_similarity(predicted: str, truth: str) -> float:
    if predicted.lower().strip() == truth.lower().strip():
        return 1.0
    predicted_tokens = _tokenize(predicted)
    truth_tokens = _tokenize(truth)
    if not predicted_tokens or not truth_tokens:
        return 0.0
    overlap = predicted_tokens & truth_tokens
    required = max(1, int(min(len(predicted_tokens), len(truth_tokens)) * 0.3))
    return 1.0 if len(overlap) >= required else len(overlap) / required


def _persona_families(text: str) -> set[str]:
    tokens = _tokenize(text)
    families: set[str] = set()
    for family, keywords in PERSONA_FAMILY_KEYWORDS.items():
        if tokens & keywords:
            families.add(family)
    return families


def _persona_accuracy(predicted: str, truth: str) -> float:
    predicted_families = BUYER_PERSONA_FAMILY.get(predicted, set()) | _persona_families(predicted)
    truth_families = _persona_families(truth)
    if not predicted_families or not truth_families:
        return _label_similarity(predicted, truth)

    overlap = predicted_families & truth_families
    if overlap:
        return 1.0

    token_score = _label_similarity(predicted, truth)
    return min(token_score, 0.5)


def _email_quality_score(
    *,
    cold_email: str,
    company_name: str,
    truth_pain_points: list[str],
    reference_outreach: str,
) -> float:
    lowered = cold_email.lower()
    scores: list[float] = []

    if company_name.lower() in lowered:
        scores.append(1.0)
    else:
        scores.append(0.0)

    pain_hits = 0
    for truth_point in truth_pain_points:
        truth_tokens = _tokenize(truth_point)
        if not truth_tokens:
            continue
        overlap = truth_tokens & _tokenize(lowered)
        required = max(2, int(len(truth_tokens) * 0.15))
        if len(overlap) >= required:
            pain_hits += 1
    pain_score = pain_hits / len(truth_pain_points) if truth_pain_points else 0.0
    scores.append(pain_score)

    reference_tokens = _tokenize(reference_outreach)
    email_tokens = _tokenize(lowered)
    if reference_tokens:
        fact_overlap = len(reference_tokens & email_tokens)
        required = max(2, int(len(reference_tokens) * 0.1))
        fact_score = min(1.0, fact_overlap / required)
    else:
        fact_score = 0.0
    scores.append(fact_score)

    has_cta = any(
        phrase in lowered
        for phrase in ("call", "chat", "meet", "connect", "schedule", "open to", "worth")
    )
    scores.append(1.0 if has_cta else 0.0)

    weights = [0.2, 0.4, 0.25, 0.15]
    return sum(score * weight for score, weight in zip(scores, weights, strict=True))


def _distance_score(predicted: float, target: float) -> float:
    return max(0.0, 1.0 - (abs(predicted - target) / 100.0))


def _pain_overlap(predicted: list[str], truth: list[str]) -> float:
    if not truth:
        return 0.0

    matches = 0
    for truth_point in truth:
        truth_tokens = _tokenize(truth_point)
        if not truth_tokens:
            continue
        for item in predicted:
            overlap = truth_tokens & _tokenize(item)
            required = max(2, int(len(truth_tokens) * 0.2))
            if len(overlap) >= required:
                matches += 1
                break
    return min(1.0, matches / len(truth))


def _expected_reviewer_decision(
    research_accuracy: float,
    email_quality: float,
    threshold: float,
) -> ReviewerDecision:
    if research_accuracy < 0.5:
        return "RESEARCH"
    if email_quality < max(0.4, threshold - 0.25):
        return "REWRITE"
    if email_quality >= threshold - 0.1:
        return "APPROVE"
    return "REWRITE"


def _reviewer_agreement(
    *,
    critique: ReviewerCritique,
    research_accuracy: float,
    email_quality: float,
    threshold: float,
) -> float:
    expected = _expected_reviewer_decision(research_accuracy, email_quality, threshold)
    if critique.decision == expected:
        return 1.0

    if critique.decision == "APPROVE" and expected == "REWRITE" and email_quality >= 0.35:
        return 0.5
    if (
        critique.decision == "REWRITE"
        and expected == "APPROVE"
        and email_quality >= threshold - 0.15
    ):
        return 0.5
    return 0.0
