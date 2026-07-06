import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from functools import wraps
from time import perf_counter
from typing import ParamSpec, TypeVar

P = ParamSpec("P")
R = TypeVar("R")

logger = logging.getLogger("outboundos.tools")


@dataclass(slots=True, frozen=True)
class RetryConfig:
    attempts: int = 3
    initial_delay_seconds: float = 0.2
    backoff_multiplier: float = 2.0


class ToolExecutionError(RuntimeError):
    def __init__(self, tool_name: str, message: str) -> None:
        super().__init__(f"{tool_name}: {message}")
        self.tool_name = tool_name


def _log(event: str, **fields: object) -> None:
    logger.info("%s | %s", event, fields)


def with_retries(
    tool_name: str,
    retry_config: RetryConfig | None = None,
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]:
    config = retry_config or RetryConfig()

    def decorator(func: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            delay = config.initial_delay_seconds
            last_error: Exception | None = None

            for attempt in range(1, config.attempts + 1):
                start = perf_counter()
                try:
                    _log("tool_attempt_started", tool=tool_name, attempt=attempt)
                    result = await func(*args, **kwargs)
                    elapsed_ms = int((perf_counter() - start) * 1000)
                    _log(
                        "tool_attempt_succeeded",
                        tool=tool_name,
                        attempt=attempt,
                        elapsed_ms=elapsed_ms,
                    )
                    return result
                except Exception as exc:  # noqa: BLE001
                    elapsed_ms = int((perf_counter() - start) * 1000)
                    last_error = exc
                    _log(
                        "tool_attempt_failed",
                        tool=tool_name,
                        attempt=attempt,
                        elapsed_ms=elapsed_ms,
                        error=str(exc),
                    )
                    if attempt < config.attempts:
                        await asyncio.sleep(delay)
                        delay *= config.backoff_multiplier

            message = "Tool failed after retries"
            if last_error is not None:
                raise ToolExecutionError(tool_name, message) from last_error
            raise ToolExecutionError(tool_name, message)

        return wrapper

    return decorator


async def execute_tool(  # noqa: UP047
    tool_name: str,
    handler: Callable[[], Awaitable[R]],
) -> R:
    try:
        _log("tool_execution_started", tool=tool_name)
        result = await handler()
        _log("tool_execution_completed", tool=tool_name)
        return result
    except ToolExecutionError:
        _log("tool_execution_failed", tool=tool_name)
        raise
    except Exception as exc:  # noqa: BLE001
        _log("tool_execution_failed", tool=tool_name, error=str(exc))
        raise ToolExecutionError(tool_name, "Unexpected execution error") from exc
