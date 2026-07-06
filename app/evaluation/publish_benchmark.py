"""Publish an evaluation run as the canonical benchmark_results.json artifact."""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from app.evaluation.models import EvaluationSummary

METRIC_DEFINITIONS = {
    "research_accuracy": (
        "Token overlap between predicted and ground-truth industry labels."
    ),
    "icp_accuracy": "1 - |predicted_icp - target_icp| / 100.",
    "pain_point_accuracy": (
        "Fraction of GT pain points with sufficient token overlap in predictions."
    ),
    "persona_accuracy": (
        "Role-family overlap between predicted buyer enum and GT persona text."
    ),
    "email_quality": (
        "Weighted composite: company name (20%), pain overlap (40%), "
        "reference facts (25%), CTA (15%)."
    ),
    "reviewer_agreement": (
        "Agreement with expected reviewer decision derived from research + email quality."
    ),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Publish eval summary.json to data/benchmark_results.json",
    )
    parser.add_argument(
        "summary",
        type=Path,
        help="Path to eval run summary.json (e.g. app/evaluation/history/eval-*/summary.json)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/benchmark_results.json"),
        help="Canonical results output path",
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("data/outboundbench_companies.csv"),
        help="OutboundBench dataset path used for the run",
    )
    parser.add_argument(
        "--notes",
        type=str,
        default="",
        help="Optional note appended to the published record",
    )
    return parser.parse_args()


def publish(
    *,
    summary_path: Path,
    output_path: Path,
    dataset_path: Path,
    notes: str = "",
) -> Path:
    summary = EvaluationSummary.model_validate_json(summary_path.read_text(encoding="utf-8"))
    report_dir = summary_path.parent

    payload = {
        "schema_version": "1.0",
        "published_at": datetime.now(tz=UTC).isoformat(),
        "status": "official",
        "dataset": {
            "name": "OutboundBench",
            "path": str(dataset_path),
            "size": summary.dataset_size,
        },
        "run": {
            "run_id": summary.run_id,
            "generated_at": summary.generated_at.isoformat(),
            "report_dir": str(report_dir),
            "quality_threshold": 0.75,
            "max_concurrency": 2,
            "agents_mode": "live",
        },
        "metrics": {
            "research_accuracy": round(summary.research_accuracy, 4),
            "icp_accuracy": round(summary.icp_accuracy, 4),
            "pain_point_accuracy": round(summary.pain_point_accuracy, 4),
            "persona_accuracy": round(summary.persona_accuracy, 4),
            "email_quality": round(summary.email_similarity, 4),
            "reviewer_agreement": round(summary.reviewer_agreement, 4),
        },
        "operations": {
            "avg_latency_ms": round(summary.avg_latency_ms, 1),
            "avg_cost_usd": round(summary.avg_cost_usd, 6),
            "avg_tokens": round(summary.avg_tokens, 1),
        },
        "metric_definitions": METRIC_DEFINITIONS,
        "notes": notes,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return output_path


def main() -> None:
    args = parse_args()
    output = publish(
        summary_path=args.summary,
        output_path=args.output,
        dataset_path=args.dataset,
        notes=args.notes,
    )
    print(f"Published benchmark results to {output}")


if __name__ == "__main__":
    main()
