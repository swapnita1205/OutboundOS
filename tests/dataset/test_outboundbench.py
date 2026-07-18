import csv
import json
from datetime import UTC, datetime
from pathlib import Path

from app.dataset.exporters import export_csv, export_jsonl, export_review_queue
from app.dataset.schemas import (
    EnrichmentBundle,
    EvidenceItem,
    LLMExtractionOutput,
    OutboundBenchRecord,
    OutreachValidation,
    PainPointExtraction,
)
from app.dataset.validators import (
    build_record,
    compute_source_quality_score,
    validate_exported_record,
    validate_outreach,
    validate_record,
)


def _sample_extraction() -> LLMExtractionOutput:
    return LLMExtractionOutput(
        industry="saas",
        short_description="Provides workflow automation for GTM teams.",
        target_persona="VP Sales",
        pain_points=[
            PainPointExtraction(
                description="Manual research slows outbound",
                evidence_urls=["https://acme.com/about"],
                evidence_snippets=["Teams spend hours on account research"],
            ),
            PainPointExtraction(
                description="Inconsistent messaging quality",
                evidence_urls=["https://acme.com/customers"],
                evidence_snippets=["Customers need consistent outreach"],
            ),
            PainPointExtraction(
                description="Limited pipeline visibility",
                evidence_urls=["https://acme.com/pricing"],
                evidence_snippets=["Pricing plans for growing teams"],
            ),
        ],
        confidence_score=0.86,
        persona_confidence=0.8,
    )


def _sample_bundle() -> EnrichmentBundle:
    return EnrichmentBundle(
        company_name="Acme",
        website="https://acme.com",
        homepage_scraped=True,
        evidence=[
            EvidenceItem(
                url="https://acme.com",
                snippet="Acme helps GTM teams automate research",
                source_type="website",
            ),
            EvidenceItem(
                url="https://news.example.com/acme",
                snippet="Acme announced a new outbound platform",
                source_type="news",
            ),
            EvidenceItem(
                url="https://acme.com/careers",
                snippet="Hiring SDR and RevOps roles",
                source_type="careers",
            ),
        ],
    )


def test_schema_validation() -> None:
    record = OutboundBenchRecord(
        company_name="Acme",
        website="https://acme.com",
        industry="saas",
        short_description="desc",
        target_persona="VP Sales",
        pain_points=["pain"],
        evidence_urls=["https://acme.com"],
        evidence_snippets=["snippet"],
        reference_outreach="Hello",
        confidence_score=0.9,
        needs_human_review=False,
        source_quality_score=0.8,
        generated_at=datetime.now(tz=UTC),
    )
    assert record.company_name == "Acme"


def test_csv_export(tmp_path: Path) -> None:
    record = _sample_bundle()
    extraction = _sample_extraction()
    outreach = validate_outreach(
        "Hi Acme team, noticed your GTM automation focus and manual research pain.",
        company_name="Acme",
        pain_points=[p.description for p in extraction.pain_points],
        evidence_snippets=[e.snippet for e in record.evidence],
    )
    built = build_record(bundle=record, extraction=extraction, outreach=outreach)
    csv_path = tmp_path / "out.csv"
    export_csv([built], csv_path)
    with csv_path.open("r", encoding="utf-8") as file:
        rows = list(csv.DictReader(file))
    assert len(rows) == 1
    assert rows[0]["company_name"] == "Acme"


def test_jsonl_export(tmp_path: Path) -> None:
    built = build_record(
        bundle=_sample_bundle(),
        extraction=_sample_extraction(),
        outreach=OutreachValidation(
            email_body="email",
            word_count=1,
            includes_company_fact=True,
            includes_pain_point=True,
        ),
    )
    jsonl_path = tmp_path / "out.jsonl"
    export_jsonl([built], jsonl_path)
    lines = jsonl_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["company_name"] == "Acme"


def test_needs_human_review_logic() -> None:
    bundle = _sample_bundle()
    extraction = _sample_extraction()
    extraction.confidence_score = 0.5
    outreach = OutreachValidation(
        email_body="x" * 200,
        word_count=200,
        includes_company_fact=False,
        includes_pain_point=False,
        unsupported_claims=["unsupported claim"],
    )
    needs_review, reasons = validate_record(
        bundle=bundle,
        extraction=extraction,
        outreach=outreach,
        source_quality_score=0.5,
    )
    assert needs_review is True
    assert "low_confidence_score" in reasons


def test_source_quality_score_logic() -> None:
    score = compute_source_quality_score(_sample_bundle())
    assert score >= 0.7


def test_validate_outreach_allows_paraphrased_pain_point() -> None:
    outreach = validate_outreach(
        (
            "Hi Stripe team, I saw Stripe powers global payment infrastructure. "
            "Many finance teams struggle with cross-border payment complexity. "
            "Open to a quick call next week?"
        ),
        company_name="Stripe",
        pain_points=["Challenges integrating global payment processing efficiently"],
        evidence_snippets=[
            "Stripe provides financial infrastructure for global payment processing",
        ],
    )
    assert outreach.includes_pain_point is True
    assert outreach.unsupported_claims == []


def test_validate_exported_record_passes_good_row() -> None:
    outreach = validate_outreach(
        "Hi Acme, Acme helps GTM teams automate research and manual research slows outbound.",
        company_name="Acme",
        pain_points=["Manual research slows outbound"],
        evidence_snippets=["Acme helps GTM teams automate research"],
    )
    needs_review, reasons = validate_exported_record(
        industry="SaaS",
        pain_points=["Manual research slows outbound"],
        evidence_urls=["https://acme.com", "https://news.example.com/acme"],
        confidence_score=0.9,
        outreach=outreach,
    )
    assert needs_review is False
    assert reasons == []


def test_review_queue_export(tmp_path: Path) -> None:
    good = build_record(
        bundle=_sample_bundle(),
        extraction=_sample_extraction(),
        outreach=OutreachValidation(
            email_body="ok",
            word_count=1,
            includes_company_fact=True,
            includes_pain_point=True,
        ),
    )
    bad = good.model_copy(update={"needs_human_review": True, "company_name": "Beta"})
    export_review_queue([good, bad], tmp_path / "review.csv")
    with (tmp_path / "review.csv").open("r", encoding="utf-8") as file:
        rows = list(csv.DictReader(file))
    assert len(rows) == 1
    assert rows[0]["company_name"] == "Beta"
