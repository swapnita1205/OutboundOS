"""Merge a filled-in human worksheet into an OutboundBenchRecord-compatible CSV.

Reads everything — including the full evidence_urls/evidence_snippets — from
the worksheet itself (it embeds the complete evidence as hidden JSON columns),
so this script has no dependency on the original LLM-generated dataset CSV.
The human-authored fields (industry,
short_description, target_persona, pain_points, reference_outreach) come
entirely from what was typed into the worksheet. Rows that are still
incomplete are skipped by default so this can be run incrementally on
partially-labeled batches.
"""

import argparse
import csv
import json
from pathlib import Path

from app.dataset.schemas import OutboundBenchRecord

REQUIRED_FIELDS = (
    "human_industry",
    "human_persona",
    "human_pain_point_1",
    "human_reference_outreach",
)


def load_worksheet_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8") as file:
        return list(csv.DictReader(file))


def _is_complete(row: dict[str, str]) -> bool:
    return all(row.get(field, "").strip() for field in REQUIRED_FIELDS)


def _pain_points(row: dict[str, str]) -> list[str]:
    points = []
    for i in range(1, 6):
        value = row.get(f"human_pain_point_{i}", "").strip()
        if value:
            points.append(value)
    return points


def build_human_records(
    worksheet_rows: list[dict[str, str]],
) -> tuple[list[OutboundBenchRecord], list[str]]:
    records: list[OutboundBenchRecord] = []
    incomplete: list[str] = []

    for row in worksheet_rows:
        company_name = row["company_name"]
        if not _is_complete(row):
            incomplete.append(company_name)
            continue

        records.append(
            OutboundBenchRecord(
                company_name=company_name,
                website=row["website"],
                industry=row["human_industry"].strip(),
                short_description=row.get("human_short_description", "").strip(),
                target_persona=row["human_persona"].strip(),
                pain_points=_pain_points(row),
                evidence_urls=json.loads(row["_evidence_urls_full_json"]),
                evidence_snippets=json.loads(row["_evidence_snippets_full_json"]),
                reference_outreach=row["human_reference_outreach"].strip(),
                confidence_score=1.0,
                needs_human_review=False,
                source_quality_score=1.0,
                generated_at=OutboundBenchRecord.now(),
                validation_reasons=["human_authored_ground_truth"],
            )
        )
    return records, incomplete


def write_records_csv(records: list[OutboundBenchRecord], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(OutboundBenchRecord.model_fields.keys())
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        list_fields = ("pain_points", "evidence_urls", "evidence_snippets", "validation_reasons")
        for record in records:
            payload = record.model_dump(mode="json")
            for list_field in list_fields:
                payload[list_field] = json.dumps(payload[list_field])
            writer.writerow(payload)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Merge a filled human-authoring worksheet into a ground-truth CSV"
    )
    parser.add_argument("--worksheet", type=str, default="data/human_ground_truth/worksheet.csv")
    parser.add_argument(
        "--output", type=str, default="data/human_ground_truth/outboundbench_human.csv"
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    worksheet_rows = load_worksheet_rows(Path(args.worksheet))

    records, incomplete = build_human_records(worksheet_rows)
    write_records_csv(records, Path(args.output))

    print(f"Human-authored records written: {len(records)} -> {args.output}")
    if incomplete:
        print(f"Skipped {len(incomplete)} incomplete/unmatched rows (fill these in and re-run):")
        for name in incomplete[:20]:
            print(f"  - {name}")
        if len(incomplete) > 20:
            print(f"  ... and {len(incomplete) - 20} more")


if __name__ == "__main__":
    main()
