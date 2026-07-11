import json
import logging
from collections.abc import AsyncGenerator
from typing import Annotated, Any

from arq.connections import ArqRedis
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, HttpUrl
from redis.asyncio import Redis

from app.api.dependencies import job_pool_dependency, redis_dependency
from app.graph.builder import build_graph
from app.graph.state import OutboundWorkflowState, create_initial_state

logger = logging.getLogger("outboundos.api.ops")

router = APIRouter(prefix="/ops", tags=["ops"])


class BenchmarkRequest(BaseModel):
    dataset_size: int = Field(default=100, ge=1, le=1000)


class StreamWorkflowRequest(BaseModel):
    company_name: str
    website: HttpUrl
    hiring_trends: list[str] = Field(default_factory=list)
    max_iterations: int = Field(default=4, ge=1, le=10)


@router.post("/jobs/evaluation")
async def enqueue_evaluation(
    payload: BenchmarkRequest,
    job_pool: Annotated[ArqRedis, Depends(job_pool_dependency)],
) -> dict[str, str]:
    job = await job_pool.enqueue_job("run_evaluation_job", payload.dataset_size)
    if job is None:
        raise RuntimeError("Failed to enqueue evaluation job")
    return {"job_id": job.job_id}


@router.get("/cache/{key}")
async def get_cached_value(
    key: str,
    redis: Annotated[Redis, Depends(redis_dependency)],
) -> dict[str, str | None]:
    value = await redis.get(key)
    return {"key": key, "value": value}


STAGE_LABELS: dict[str, str] = {
    "research": "Research Agent",
    "icp_analysis": "ICP Agent",
    "pain_point_analysis": "Pain Point Agent",
    "persona_selection": "Persona Agent",
    "email_generation": "Messaging Agent",
    "rewrite": "Messaging Agent (rewrite)",
    "reviewer": "Reviewer Agent",
}


def _stage_payload(stage: str, state: OutboundWorkflowState) -> dict[str, Any]:
    trace = state.get("reasoning_trace") or []
    payload: dict[str, Any] = {
        "type": "stage",
        "stage": stage,
        "label": STAGE_LABELS.get(stage, stage),
        "detail": trace[-1] if trace else "",
        "metrics": {
            "latency_ms": state.get("total_latency_ms", 0.0),
            "cost_usd": state.get("total_cost_usd", 0.0),
            "tokens": state.get("total_token_usage", 0),
        },
    }

    if stage == "research" and "company_summary" in state:
        payload["company_summary"] = state["company_summary"].model_dump()
    if stage == "icp_analysis" and "icp_score" in state:
        payload["icp_score"] = state["icp_score"].model_dump()
    if stage == "pain_point_analysis" and "pain_points" in state:
        payload["pain_points"] = state["pain_points"].model_dump()
    if stage == "persona_selection" and "persona_selection" in state:
        payload["persona_selection"] = state["persona_selection"].model_dump()
    if stage in ("email_generation", "rewrite") and "message_bundle" in state:
        payload["message_bundle"] = state["message_bundle"].model_dump()
    if stage == "reviewer" and "reviewer_critique" in state:
        payload["reviewer_critique"] = state["reviewer_critique"].model_dump()
        payload["reviewer_decision"] = state.get("reviewer_decision")
        payload["quality_score"] = state.get("quality_score")
        payload["iteration_count"] = state.get("iteration_count")

    return payload


@router.post("/stream")
async def stream_workflow(payload: StreamWorkflowRequest) -> StreamingResponse:
    async def event_stream() -> AsyncGenerator[str, None]:
        graph = build_graph()
        state = create_initial_state(
            company_name=payload.company_name,
            website=str(payload.website),
            hiring_trends=payload.hiring_trends,
            max_iterations=payload.max_iterations,
        )
        latest_state: OutboundWorkflowState = state

        try:
            yield f"data: {json.dumps({'type': 'started', 'company_name': payload.company_name})}\n\n"

            async for update in graph.astream(state, stream_mode="updates"):
                for stage, node_state in update.items():
                    latest_state = node_state
                    yield f"data: {json.dumps(_stage_payload(stage, node_state))}\n\n"

            final_payload = {
                "type": "final",
                "final_decision": latest_state.get("reviewer_decision"),
                "metrics": {
                    "latency_ms": latest_state.get("total_latency_ms", 0.0),
                    "cost_usd": latest_state.get("total_cost_usd", 0.0),
                    "tokens": latest_state.get("total_token_usage", 0),
                    "iterations": latest_state.get("iteration_count", 0),
                },
            }
            yield f"data: {json.dumps(final_payload)}\n\n"
        except Exception as exc:  # noqa: BLE001
            logger.exception("stream_workflow_failed")
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"
        finally:
            yield "event: end\ndata: done\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
