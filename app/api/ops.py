import json
from collections.abc import AsyncGenerator
from typing import Annotated

from arq.connections import ArqRedis
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, HttpUrl
from redis.asyncio import Redis

from app.api.dependencies import job_pool_dependency, redis_dependency
from app.graph.builder import build_graph
from app.graph.state import create_initial_state

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
        result = await graph.ainvoke(state)
        trace = result.get("reasoning_trace", [])
        for item in trace:
            yield f"data: {json.dumps({'trace': item})}\n\n"
        yield f"data: {json.dumps({'final_decision': result.get('reviewer_decision')})}\n\n"
        yield "event: end\ndata: done\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
