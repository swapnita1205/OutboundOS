import csv
import json
from pathlib import Path

from app.dataset.schemas import OutboundBenchRecord


def export_csv(records: list[OutboundBenchRecord], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "company_name",
        "website",
        "industry",
        "short_description",
        "target_persona",
        "pain_points",
        "evidence_urls",
        "evidence_snippets",
        "reference_outreach",
        "confidence_score",
        "needs_human_review",
        "source_quality_score",
        "generated_at",
        "validation_reasons",
    ]
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        for record in records:
            row = record.model_dump()
            row["pain_points"] = json.dumps(row["pain_points"])
            row["evidence_urls"] = json.dumps(row["evidence_urls"])
            row["evidence_snippets"] = json.dumps(row["evidence_snippets"])
            row["validation_reasons"] = json.dumps(row["validation_reasons"])
            row["generated_at"] = record.generated_at.isoformat()
            writer.writerow({key: row[key] for key in fields})


def export_jsonl(records: list[OutboundBenchRecord], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        for record in records:
            file.write(record.model_dump_json())
            file.write("\n")


def export_review_queue(records: list[OutboundBenchRecord], path: Path) -> None:
    review_rows = [record for record in records if record.needs_human_review]
    export_csv(review_rows, path)
