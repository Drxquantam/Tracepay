"""Fire-and-forget work that must not hold up an HTTP request (e.g. a payment waiting on
a slow bank in the mock switch).

Why not FastAPI's BackgroundTasks? They run after the response is sent, but inside the
same request cycle, so the server won't read the *next* request on that keep-alive
connection until they finish. The k6 load test exposed it: clients queued for seconds
behind other payments' 2-second bank delays. A detached asyncio task ends the request
cycle immediately.

Trade-off (also in the README): tasks live in this process's memory. If the server
restarts, in-flight work is lost. That's safe here because the deadline sweep finds any
payment stranded in flight. A production system would use a durable queue instead.
"""

import asyncio
import logging
from collections.abc import Coroutine
from typing import Any

log = logging.getLogger("tracepay.worker")

# Strong references: asyncio only keeps weak references to tasks, so an unreferenced task
# can be garbage-collected before it finishes.
_tasks: set[asyncio.Task[Any]] = set()


def spawn(coro: Coroutine[Any, Any, Any]) -> None:
    task = asyncio.create_task(coro)
    _tasks.add(task)
    task.add_done_callback(_finished)


def _finished(task: asyncio.Task[Any]) -> None:
    _tasks.discard(task)
    if not task.cancelled() and task.exception() is not None:
        log.error("Background task failed", exc_info=task.exception())


async def drain() -> None:
    """Wait until all spawned work (and anything it spawns) is done. Used by tests so each
    request's follow-up work has finished before the test looks at the result. Re-raises
    the first failure, so bugs in background work fail the test instead of hiding."""
    while _tasks:
        results = await asyncio.gather(*list(_tasks), return_exceptions=True)
        for r in results:
            if isinstance(r, BaseException):
                raise r
