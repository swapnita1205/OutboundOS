from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl


class GroundTruth(BaseModel):
    industry: str
    persona: str
    pain_points: list[str]
    reference_outreach: str
    icp_target: float = Field(ge=0, le=100)


class EvaluationSample(BaseModel):
    company_name: str
    website: HttpUrl
    hiring_trends: list[str]
    ground_truth: GroundTruth


class EvaluationRecord(BaseModel):
    company_name: str
    research_accuracy: float = Field(ge=0, le=1)
    icp_accuracy: float = Field(ge=0, le=1)
    persona_accuracy: float = Field(ge=0, le=1)
    pain_point_accuracy: float = Field(ge=0, le=1)
    reviewer_agreement: float = Field(ge=0, le=1)
    email_similarity: float = Field(ge=0, le=1)
    latency_ms: float = Field(ge=0)
    cost_usd: float = Field(ge=0)
    tokens: int = Field(ge=0)


class EvaluationSummary(BaseModel):
    run_id: str
    generated_at: datetime
    dataset_size: int
    research_accuracy: float = Field(ge=0, le=1)
    icp_accuracy: float = Field(ge=0, le=1)
    persona_accuracy: float = Field(ge=0, le=1)
    pain_point_accuracy: float = Field(ge=0, le=1)
    reviewer_agreement: float = Field(ge=0, le=1)
    email_similarity: float = Field(ge=0, le=1)
    avg_latency_ms: float = Field(ge=0)
    avg_cost_usd: float = Field(ge=0)
    avg_tokens: float = Field(ge=0)


class EvaluationReport(BaseModel):
    summary: EvaluationSummary
    records: list[EvaluationRecord]


class HistoricalRun(BaseModel):
    run_id: str
    generated_at: datetime
    dataset_size: int
    report_dir: str
    research_accuracy: float
    persona_accuracy: float
    pain_point_accuracy: float
    email_similarity: float
    avg_latency_ms: float
    avg_cost_usd: float


def now_utc() -> datetime:
    return datetime.now(tz=UTC)


def create_run_id(prefix: Literal["eval"] = "eval") -> str:
    return f"{prefix}-{now_utc().strftime('%Y%m%d-%H%M%S')}"


def default_history_dir() -> Path:
    return Path(__file__).resolve().parent / "history"
