import asyncio
from pathlib import Path
from statistics import mean
from typing import Any, cast

from app.evaluation.dataset import generate_dataset
from app.evaluation.metrics import score_record
from app.evaluation.models import (
    EvaluationRecord,
    EvaluationReport,
    EvaluationSample,
    EvaluationSummary,
    HistoricalRun,
    create_run_id,
    default_history_dir,
    now_utc,
)
from app.evaluation.storage import append_historical_run, load_historical_runs, write_report_files
from app.graph.builder import build_graph
from app.graph.state import OutboundWorkflowState, create_initial_state


class EvaluationRunner:
    def __init__(
        self,
        *,
        dataset_size: int = 100,
        max_concurrency: int = 8,
        dataset_path: Path | None = None,
        quality_threshold: float = 0.7,
    ) -> None:
        self.dataset_size = dataset_size
        self.max_concurrency = max_concurrency
        self.dataset_path = dataset_path
        self.quality_threshold = quality_threshold

    async def run(self) -> EvaluationReport:
        dataset = self._load_dataset()
        graph = build_graph()
        semaphore = asyncio.Semaphore(self.max_concurrency)
        tasks = [self._evaluate_one(graph, semaphore, sample) for sample in dataset]
        records = await asyncio.gather(*tasks)
        summary = _summarize(records, dataset_size=len(dataset))
        return EvaluationReport(summary=summary, records=records)

    def _load_dataset(self) -> list[EvaluationSample]:
        if self.dataset_path is not None:
            from app.evaluation.outboundbench_loader import load_outboundbench_dataset

            return load_outboundbench_dataset(self.dataset_path, limit=self.dataset_size)
        return generate_dataset(size=self.dataset_size)

    async def _evaluate_one(
        self,
        graph: Any,
        semaphore: asyncio.Semaphore,
        sample: EvaluationSample,
    ) -> EvaluationRecord:
        async with semaphore:
            state = create_initial_state(
                company_name=sample.company_name,
                website=str(sample.website),
                hiring_trends=sample.hiring_trends,
                quality_threshold=self.quality_threshold,
                max_iterations=4,
            )
            result = await graph.ainvoke(state)
            typed_result = cast(OutboundWorkflowState, result)
            return score_record(sample, typed_result)


def export_evaluation_artifacts(report: EvaluationReport, output_root: Path | None = None) -> Path:
    run_id = report.summary.run_id
    history_dir = default_history_dir()
    base = output_root or history_dir
    report_dir = base / run_id
    write_report_files(report, report_dir)

    prior_runs = load_historical_runs(history_dir=history_dir)
    current_record = HistoricalRun(
        run_id=run_id,
        generated_at=report.summary.generated_at,
        dataset_size=report.summary.dataset_size,
        report_dir=str(report_dir),
        research_accuracy=report.summary.research_accuracy,
        persona_accuracy=report.summary.persona_accuracy,
        pain_point_accuracy=report.summary.pain_point_accuracy,
        email_similarity=report.summary.email_similarity,
        avg_latency_ms=report.summary.avg_latency_ms,
        avg_cost_usd=report.summary.avg_cost_usd,
    )
    append_historical_run(current_record, history_dir=history_dir)
    from app.evaluation.charts import generate_report_charts

    generate_report_charts(report.summary, prior_runs + [current_record], report_dir)
    return report_dir


def _summarize(records: list[EvaluationRecord], dataset_size: int) -> EvaluationSummary:
    return EvaluationSummary(
        run_id=create_run_id(),
        generated_at=now_utc(),
        dataset_size=dataset_size,
        research_accuracy=mean(item.research_accuracy for item in records),
        icp_accuracy=mean(item.icp_accuracy for item in records),
        persona_accuracy=mean(item.persona_accuracy for item in records),
        pain_point_accuracy=mean(item.pain_point_accuracy for item in records),
        reviewer_agreement=mean(item.reviewer_agreement for item in records),
        email_similarity=mean(item.email_similarity for item in records),
        avg_latency_ms=mean(item.latency_ms for item in records),
        avg_cost_usd=mean(item.cost_usd for item in records),
        avg_tokens=mean(item.tokens for item in records),
    )
