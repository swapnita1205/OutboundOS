from typing import cast

from redis.asyncio import Redis

from app.utils.settings import Settings


def create_redis_client(settings: Settings) -> Redis:
    password = settings.redis_password.get_secret_value() if settings.redis_password else None
    client = Redis.from_url(settings.redis_url, password=password, decode_responses=True)
    return cast(Redis, client)
