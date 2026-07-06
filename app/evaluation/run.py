import argparse
import asyncio
from pathlib import Path

from app.evaluation.runner import EvaluationRunner, export_evaluation_artifacts


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run OutboundOS evaluation framework")
    parser.add_argument("--dataset-size", type=int, default=100)
    parser.add_argument("--max-concurrency", type=int, default=8)
    parser.add_argument("--output-dir", type=str, default="")
    parser.add_argument(
        "--dataset",
        type=str,
        default="",
        help="Path to OutboundBench CSV/JSONL ground-truth dataset",
    )
    parser.add_argument("--quality-threshold", type=float, default=0.7)
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    dataset_path = Path(args.dataset) if args.dataset else None
    runner = EvaluationRunner(
        dataset_size=args.dataset_size,
        max_concurrency=args.max_concurrency,
        dataset_path=dataset_path,
        quality_threshold=args.quality_threshold,
    )
    report = await runner.run()
    output_dir = Path(args.output_dir) if args.output_dir else None
    report_path = export_evaluation_artifacts(report, output_root=output_dir)
    print(report.summary.model_dump_json(indent=2))
    print(f"Report artifacts: {report_path}")


if __name__ == "__main__":
    asyncio.run(main())
