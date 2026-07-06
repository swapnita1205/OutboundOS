from typing import Annotated

from fastapi import APIRouter, Depends
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import db_session_dependency, redis_dependency, settings_dependency
from app.schemas.health import HealthResponse
from app.utils.retry import retry_async
from app.utils.settings import Settings

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health(
    settings: Annotated[Settings, Depends(settings_dependency)],
    db: Annotated[AsyncSession, Depends(db_session_dependency)],
    redis: Annotated[Redis, Depends(redis_dependency)],
) -> HealthResponse:
    database = "ok"
    redis_status = "ok"
    try:
        await retry_async(lambda: db.execute(text("SELECT 1")))
    except Exception:  # noqa: BLE001
        database = "error"

    try:
        await retry_async(redis.ping)
    except Exception:  # noqa: BLE001
        redis_status = "error"

    overall = "ok" if database == "ok" and redis_status == "ok" else "degraded"
    return HealthResponse(
        status=overall,
        service=settings.app_name,
        database=database,
        redis=redis_status,
    )
