import csv
import json
from pathlib import Path

from app.evaluation.models import EvaluationReport, HistoricalRun, default_history_dir

HISTORY_FILE = "history_index.jsonl"


def write_report_files(report: EvaluationReport, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_summary_json(report, output_dir / "summary.json")
    _write_records_csv(report, output_dir / "records.csv")


def append_historical_run(record: HistoricalRun, history_dir: Path | None = None) -> None:
    target = history_dir or default_history_dir()
    target.mkdir(parents=True, exist_ok=True)
    path = target / HISTORY_FILE
    with path.open("a", encoding="utf-8") as file:
        file.write(record.model_dump_json())
        file.write("\n")


def load_historical_runs(history_dir: Path | None = None) -> list[HistoricalRun]:
    target = history_dir or default_history_dir()
    path = target / HISTORY_FILE
    if not path.exists():
        return []

    runs: list[HistoricalRun] = []
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            stripped = line.strip()
            if stripped:
                runs.append(HistoricalRun.model_validate_json(stripped))
    return runs


def _write_summary_json(report: EvaluationReport, path: Path) -> None:
    with path.open("w", encoding="utf-8") as file:
        json.dump(report.summary.model_dump(mode="json"), file, indent=2)


def _write_records_csv(report: EvaluationReport, path: Path) -> None:
    fields = [
        "company_name",
        "research_accuracy",
        "icp_accuracy",
        "persona_accuracy",
        "pain_point_accuracy",
        "reviewer_agreement",
        "email_similarity",
        "latency_ms",
        "cost_usd",
        "tokens",
    ]
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        for item in report.records:
            writer.writerow(item.model_dump())
