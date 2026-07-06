from arq.connections import ArqRedis, RedisSettings, create_pool

from app.utils.settings import Settings


async def create_job_pool(settings: Settings) -> ArqRedis:
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    return await create_pool(redis_settings)
