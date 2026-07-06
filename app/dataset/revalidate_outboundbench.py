import argparse
import csv
import json
from datetime import datetime
from pathlib import Path

from app.dataset.exporters import export_csv, export_jsonl, export_review_queue
from app.dataset.schemas import OutboundBenchRecord
from app.dataset.validators import validate_exported_record, validate_outreach
from app.utils.logging import configure_logging
from app.utils.settings import get_settings


def load_records_from_csv(path: Path) -> list[OutboundBenchRecord]:
    records: list[OutboundBenchRecord] = []
    with path.open("r", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        for row in reader:
            records.append(
                OutboundBenchRecord(
                    company_name=row["company_name"],
                    website=row["website"],
                    industry=row["industry"],
                    short_description=row["short_description"],
                    target_persona=row["target_persona"],
                    pain_points=json.loads(row["pain_points"]),
                    evidence_urls=json.loads(row["evidence_urls"]),
                    evidence_snippets=json.loads(row["evidence_snippets"]),
                    reference_outreach=row["reference_outreach"],
                    confidence_score=float(row["confidence_score"]),
                    needs_human_review=row["needs_human_review"].lower() == "true",
                    source_quality_score=float(row["source_quality_score"]),
                    generated_at=datetime.fromisoformat(row["generated_at"]),
                    validation_reasons=json.loads(row["validation_reasons"]),
                )
            )
    return records


def revalidate_record(record: OutboundBenchRecord) -> OutboundBenchRecord:
    outreach = validate_outreach(
        record.reference_outreach,
        company_name=record.company_name,
        pain_points=record.pain_points,
        evidence_snippets=record.evidence_snippets,
    )
    needs_review, reasons = validate_exported_record(
        industry=record.industry,
        pain_points=record.pain_points,
        evidence_urls=record.evidence_urls,
        confidence_score=record.confidence_score,
        outreach=outreach,
    )
    return record.model_copy(
        update={
            "needs_human_review": needs_review,
            "validation_reasons": reasons,
        }
    )


def revalidate_records(records: list[OutboundBenchRecord]) -> list[OutboundBenchRecord]:
    return [revalidate_record(record) for record in records]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Revalidate OutboundBench dataset rows in place")
    parser.add_argument("--input", type=str, default="data/outboundbench_companies.csv")
    parser.add_argument("--output", type=str, default="")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    configure_logging(get_settings().log_level)
    input_path = Path(args.input)
    output_path = Path(args.output) if args.output else input_path

    records = revalidate_records(load_records_from_csv(input_path))
    output_jsonl = output_path.with_suffix(".jsonl")
    review_queue = output_path.parent / "outboundbench_review_queue.csv"

    export_csv(records, output_path)
    export_jsonl(records, output_jsonl)
    export_review_queue(records, review_queue)

    passed = sum(1 for record in records if not record.needs_human_review)
    print(f"Revalidated {len(records)} companies")
    print(f"rows_passed_validation: {passed}")
    print(f"rows_needing_human_review: {len(records) - passed}")
    print(f"CSV: {output_path}")
    print(f"JSONL: {output_jsonl}")
    print(f"Review queue: {review_queue}")


if __name__ == "__main__":
    main()
