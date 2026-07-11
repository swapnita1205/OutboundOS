import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from time import perf_counter

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address
from starlette.middleware.base import RequestResponseEndpoint

from app.api import api_router
from app.db.base import Base
from app.db.session import engine
from app.models import SystemRecord  # noqa: F401
from app.services.cache import create_redis_client
from app.services.jobs import create_job_pool
from app.services.observability import configure_otel, instrument_fastapi
from app.utils.logging import configure_logging
from app.utils.settings import get_settings

logger = logging.getLogger("outboundos.access")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level)
    configure_otel(settings)
    app.state.redis = create_redis_client(settings)
    app.state.job_pool = await create_job_pool(settings)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield
    finally:
        await app.state.job_pool.close()
        await app.state.redis.aclose()
        await engine.dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    limiter = Limiter(
        key_func=get_remote_address,
        default_limits=[f"{settings.rate_limit_per_minute}/minute"],
    )
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]
    app.add_middleware(SlowAPIMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.dashboard_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(api_router, prefix="/api/v1")
    instrument_fastapi(app)

    @app.middleware("http")
    async def access_log_middleware(
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        started = perf_counter()
        response = await call_next(request)
        duration_ms = (perf_counter() - started) * 1000
        logger.info(
            "request_completed",
            extra={
                "path": request.url.path,
                "method": request.method,
                "status_code": response.status_code,
                "latency_ms": round(duration_ms, 2),
            },
        )
        return response

    return app


app = create_app()
