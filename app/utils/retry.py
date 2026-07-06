import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

T = TypeVar("T")


async def retry_async(  # noqa: UP047
    fn: Callable[[], Awaitable[T]],
    *,
    attempts: int = 3,
    initial_delay_s: float = 0.1,
    backoff: float = 2.0,
) -> T:
    delay = initial_delay_s
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return await fn()
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if attempt < attempts:
                await asyncio.sleep(delay)
                delay *= backoff
    if last_error is not None:
        raise last_error
    raise RuntimeError("retry_async exhausted without captured exception")
