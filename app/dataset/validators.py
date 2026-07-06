import re

from app.dataset.schemas import (
    EnrichmentBundle,
    LLMExtractionOutput,
    OutboundBenchRecord,
    OutreachValidation,
    PainPointExtraction,
)

_BOILERPLATE_PATTERNS = (
    re.compile(r"^(hi|hello|hey|dear|greetings)\b", re.IGNORECASE),
    re.compile(r"\b(best|thanks|thank you|regards|sincerely|cheers)\b", re.IGNORECASE),
    re.compile(
        r"\b(let me know|looking forward|open to|happy to|would you be open)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b(schedule|quick call|short call|chat next week|connect)\b", re.IGNORECASE),
)


def _tokenize(text: str) -> set[str]:
    return {word for word in re.findall(r"[a-z0-9]+", text.lower()) if len(word) > 3}


def compute_source_quality_score(bundle: EnrichmentBundle) -> float:
    score = 0.0
    source_types = {item.source_type for item in bundle.evidence}
    if bundle.homepage_scraped:
        score += 0.25
    if "website" in source_types:
        score += 0.2
    if "blog" in source_types or "docs" in source_types:
        score += 0.15
    if "news" in source_types:
        score += 0.15
    if "careers" in source_types:
        score += 0.15
    independent = len(
        {item.url.split("/")[2] if "://" in item.url else item.url for item in bundle.evidence}
    )
    score += min(0.1, independent * 0.02)
    return min(1.0, score)


def _is_boilerplate_sentence(sentence: str) -> bool:
    cleaned = sentence.strip()
    if len(cleaned) < 12:
        return True
    return any(pattern.search(cleaned) for pattern in _BOILERPLATE_PATTERNS)


def _sentence_supported(sentence: str, evidence_corpus: str, company_name: str) -> bool:
    if _is_boilerplate_sentence(sentence):
        return True
    if company_name.lower() in sentence.lower():
        return True

    sentence_tokens = _tokenize(sentence)
    if not sentence_tokens:
        return True

    evidence_tokens = _tokenize(evidence_corpus)
    overlap = sentence_tokens & evidence_tokens
    return len(overlap) >= min(2, len(sentence_tokens))


def _sentence_relates_to_pain(sentence: str, pain_points: list[str]) -> bool:
    sentence_tokens = _tokenize(sentence)
    if not sentence_tokens:
        return False
    for point in pain_points:
        if sentence_tokens & _tokenize(point):
            return True
    return False


def _detect_unsupported_claims(
    email_body: str,
    evidence_snippets: list[str],
    *,
    company_name: str,
    pain_points: list[str],
) -> list[str]:
    corpus = " ".join(snippet for snippet in evidence_snippets if snippet)
    unsupported: list[str] = []
    for sentence in re.split(r"[.!?]+", email_body):
        cleaned = sentence.strip()
        if not cleaned:
            continue
        if _pain_point_in_email(cleaned, pain_points) or _sentence_relates_to_pain(
            cleaned, pain_points
        ):
            continue
        if not _sentence_supported(cleaned, corpus, company_name):
            unsupported.append(cleaned)
    return unsupported[:3]


def _pain_point_in_email(email_body: str, pain_points: list[str]) -> bool:
    email_tokens = _tokenize(email_body)
    for point in pain_points:
        point_tokens = _tokenize(point)
        if not point_tokens:
            continue
        overlap = point_tokens & email_tokens
        required = max(2, int(len(point_tokens) * 0.25))
        if len(overlap) >= required:
            return True
    return False


def validate_outreach(
    email_body: str,
    *,
    company_name: str,
    pain_points: list[str],
    evidence_snippets: list[str],
) -> OutreachValidation:
    lowered = email_body.lower()
    includes_company_fact = company_name.lower() in lowered
    includes_pain_point = _pain_point_in_email(email_body, pain_points)
    unsupported_claims = _detect_unsupported_claims(
        email_body,
        evidence_snippets,
        company_name=company_name,
        pain_points=pain_points,
    )
    return OutreachValidation(
        email_body=email_body,
        word_count=len(email_body.split()),
        includes_company_fact=includes_company_fact,
        includes_pain_point=includes_pain_point,
        unsupported_claims=unsupported_claims,
    )


def validate_record(
    *,
    bundle: EnrichmentBundle,
    extraction: LLMExtractionOutput,
    outreach: OutreachValidation,
    source_quality_score: float,  # noqa: ARG001
) -> tuple[bool, list[str]]:
    return validate_exported_record(
        industry=extraction.industry,
        pain_points=[item.description for item in extraction.pain_points],
        evidence_urls=[item.url for item in bundle.evidence if item.url],
        confidence_score=extraction.confidence_score,
        persona_confidence=extraction.persona_confidence,
        homepage_scraped=bundle.homepage_scraped,
        pain_points_with_evidence=extraction.pain_points,
        outreach=outreach,
    )


def validate_exported_record(
    *,
    industry: str,
    pain_points: list[str],
    evidence_urls: list[str],
    confidence_score: float,
    outreach: OutreachValidation,
    persona_confidence: float | None = None,
    homepage_scraped: bool | None = None,
    pain_points_with_evidence: list[PainPointExtraction] | None = None,
) -> tuple[bool, list[str]]:
    reasons: list[str] = []

    if len(evidence_urls) < 2:
        reasons.append("fewer_than_2_evidence_urls")
    if confidence_score < 0.75:
        reasons.append("low_confidence_score")
    if persona_confidence is not None and persona_confidence < 0.6:
        reasons.append("low_persona_confidence")
    if homepage_scraped is False:
        reasons.append("homepage_scrape_failed")
    if industry.lower() == "unknown":
        reasons.append("industry_unknown")
    if outreach.unsupported_claims:
        reasons.append("unsupported_outreach_claims")
    if outreach.word_count > 120:
        reasons.append("outreach_too_long")
    if not outreach.includes_company_fact:
        reasons.append("missing_company_fact")
    if not outreach.includes_pain_point:
        reasons.append("missing_pain_point")

    if pain_points_with_evidence is not None:
        for pain in pain_points_with_evidence:
            if not pain.evidence_urls or not pain.evidence_snippets:
                reasons.append("pain_point_missing_evidence")
                break

    needs_review = len(reasons) > 0
    return needs_review, reasons


def build_record(
    *,
    bundle: EnrichmentBundle,
    extraction: LLMExtractionOutput,
    outreach: OutreachValidation,
) -> OutboundBenchRecord:
    source_quality_score = compute_source_quality_score(bundle)
    needs_review, reasons = validate_record(
        bundle=bundle,
        extraction=extraction,
        outreach=outreach,
        source_quality_score=source_quality_score,
    )

    pain_points = [item.description for item in extraction.pain_points]
    evidence_urls = list({url for item in bundle.evidence for url in [item.url] if url})
    evidence_snippets = [item.snippet for item in bundle.evidence if item.snippet]

    return OutboundBenchRecord(
        company_name=bundle.company_name,
        website=bundle.website,
        industry=extraction.industry,
        short_description=extraction.short_description,
        target_persona=extraction.target_persona,
        pain_points=pain_points,
        evidence_urls=evidence_urls,
        evidence_snippets=evidence_snippets,
        reference_outreach=outreach.email_body,
        confidence_score=extraction.confidence_score,
        needs_human_review=needs_review,
        source_quality_score=source_quality_score,
        generated_at=OutboundBenchRecord.now(),
        validation_reasons=reasons,
    )
