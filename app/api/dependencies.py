from collections.abc import AsyncGenerator
from functools import lru_cache
from typing import cast

from arq.connections import ArqRedis
from fastapi import Request
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.services.cache import create_redis_client
from app.services.openai_client import OpenAIClient
from app.utils.settings import Settings, get_settings


@lru_cache(maxsize=1)
def get_openai_client() -> OpenAIClient:
    return OpenAIClient(settings=get_settings())


async def db_session_dependency() -> AsyncGenerator[AsyncSession, None]:
    async for session in get_db_session():
        yield session


def settings_dependency() -> Settings:
    return get_settings()


def redis_dependency(request: Request) -> Redis:
    redis = getattr(request.app.state, "redis", None)
    if redis is None:
        redis = create_redis_client(get_settings())
        request.app.state.redis = redis
    return redis


def job_pool_dependency(request: Request) -> ArqRedis:
    job_pool = getattr(request.app.state, "job_pool", None)
    if job_pool is None:
        raise RuntimeError("Job pool unavailable. Run app lifespan or start worker.")
    return cast(ArqRedis, job_pool)
