from arq.connections import RedisSettings

from app.evaluation.runner import EvaluationRunner, export_evaluation_artifacts
from app.utils.settings import get_settings


async def run_evaluation_job(ctx: dict[str, object], dataset_size: int = 100) -> dict[str, object]:
    runner = EvaluationRunner(dataset_size=dataset_size)
    report = await runner.run()
    report_dir = export_evaluation_artifacts(report)
    return {
        "run_id": report.summary.run_id,
        "report_dir": str(report_dir),
        "summary": report.summary.model_dump(mode="json"),
    }


class WorkerSettings:
    settings = get_settings()
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    functions = [run_evaluation_job]
