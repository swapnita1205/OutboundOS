import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from statistics import mean
from typing import TypedDict


class DatasetRow(TypedDict):
    company_name: str
    website: str
    industry: str
    short_description: str
    target_persona: str
    pain_points: list[str]
    evidence_urls: list[str]
    evidence_snippets: list[str]
    reference_outreach: str
    confidence_score: float
    needs_human_review: bool
    source_quality_score: float
    generated_at: str
    validation_reasons: list[str]


def load_records_from_csv(path: Path) -> list[DatasetRow]:
    rows: list[DatasetRow] = []
    with path.open("r", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        for row in reader:
            rows.append(
                DatasetRow(
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
                    generated_at=row["generated_at"],
                    validation_reasons=json.loads(row["validation_reasons"]),
                )
            )
    return rows


def print_quality_report(records: list[DatasetRow]) -> None:
    total = len(records)
    passed = sum(1 for row in records if not row["needs_human_review"])
    needs_review = total - passed
    avg_conf = mean(row["confidence_score"] for row in records) if records else 0.0
    avg_quality = mean(row["source_quality_score"] for row in records) if records else 0.0

    industries = Counter(row["industry"] for row in records)
    personas = Counter(row["target_persona"] for row in records)
    failure_reasons = Counter(
        reason for row in records for reason in row["validation_reasons"]
    )

    print("OutboundBench Dataset Quality Report")
    print(f"total_companies_processed: {total}")
    print(f"rows_passed_validation: {passed}")
    print(f"rows_needing_human_review: {needs_review}")
    print(f"average_confidence: {avg_conf:.3f}")
    print(f"average_source_quality: {avg_quality:.3f}")
    print("industry_distribution:")
    for key, count in industries.most_common():
        print(f"  {key}: {count}")
    print("persona_distribution:")
    for key, count in personas.most_common():
        print(f"  {key}: {count}")
    print("top_validation_failure_reasons:")
    for key, count in failure_reasons.most_common(10):
        print(f"  {key}: {count}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Print OutboundBench dataset quality report")
    parser.add_argument(
        "--input",
        type=str,
        default="data/human_ground_truth/outboundbench_human.csv",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    records = load_records_from_csv(Path(args.input))
    print_quality_report(records)


if __name__ == "__main__":
    main()
