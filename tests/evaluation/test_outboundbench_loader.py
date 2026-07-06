import json
from pathlib import Path

from app.evaluation.outboundbench_loader import load_outboundbench_dataset


def test_load_outboundbench_dataset_from_csv(tmp_path: Path) -> None:
    csv_path = tmp_path / "bench.csv"
    csv_path.write_text(
        "company_name,website,industry,short_description,target_persona,pain_points,"
        "evidence_urls,evidence_snippets,reference_outreach,confidence_score,"
        "needs_human_review,source_quality_score,generated_at,validation_reasons\n"
        "Acme,https://acme.com,SaaS,desc,VP Sales,"
        '["manual research"],'
        '["https://acme.com"],'
        '["Hiring SDR roles"],'
        '"Hi Acme",0.9,false,0.9,2026-01-01T00:00:00+00:00,[]\n',
        encoding="utf-8",
    )

    samples = load_outboundbench_dataset(csv_path)
    assert len(samples) == 1
    assert samples[0].company_name == "Acme"
    assert samples[0].ground_truth.persona == "VP Sales"
    assert samples[0].ground_truth.pain_points == ["manual research"]
    assert samples[0].hiring_trends[0].startswith("Hiring")


def test_load_outboundbench_dataset_from_jsonl(tmp_path: Path) -> None:
    jsonl_path = tmp_path / "bench.jsonl"
    payload = {
        "company_name": "Beta",
        "website": "https://beta.com",
        "industry": "FinTech",
        "short_description": "desc",
        "target_persona": "CFO",
        "pain_points": ["compliance"],
        "evidence_urls": ["https://beta.com"],
        "evidence_snippets": ["Beta helps finance teams"],
        "reference_outreach": "Hello Beta",
        "confidence_score": 0.8,
        "needs_human_review": False,
        "source_quality_score": 0.8,
        "generated_at": "2026-01-01T00:00:00+00:00",
        "validation_reasons": [],
    }
    jsonl_path.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    samples = load_outboundbench_dataset(jsonl_path)
    assert samples[0].ground_truth.industry == "FinTech"
