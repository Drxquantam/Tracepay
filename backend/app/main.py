"""TracePay API entry point. SIMULATION ONLY: fake money, fake banks, mock UPI switch."""

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.clock import get_clock
from app.config import settings
from app.db import SessionLocal
from app.jobs import run_due_jobs, start_payments
from app.routers import (
    admin,
    auth,
    chaos,
    clock,
    disputes,
    guardian,
    health,
    mandates,
    notifications,
    payees,
    payments,
)
from app.rules import DEADLINE_SWEEP_INTERVAL_SECONDS

log = logging.getLogger("tracepay")


async def deadline_sweep_loop() -> None:
    """Every few seconds, run everything that happens because time passed: expire or
    release held payments, and open disputes for payments stuck past their deadline
    (including any stranded by a server restart mid-flight)."""
    while True:
        await asyncio.sleep(DEADLINE_SWEEP_INTERVAL_SECONDS)
        try:
            result = await run_due_jobs(SessionLocal, get_clock())
            if result.payments_to_run:
                asyncio.create_task(
                    start_payments(SessionLocal, get_clock(), result.payments_to_run)
                )
            if result.disputes_opened:
                log.info("Deadline sweep opened %d dispute(s)", result.disputes_opened)
        except Exception:  # keep the loop alive; one bad run shouldn't stop future checks
            log.exception("Deadline sweep failed")


@contextlib.asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    task = asyncio.create_task(deadline_sweep_loop()) if settings.run_background_jobs else None
    yield
    if task:
        task.cancel()


app = FastAPI(
    title="TracePay API (simulation only)",
    description="Simulated UPI-style payments. No real money, banks or NPCI integration.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for module in (
    health,
    auth,
    payees,
    payments,
    disputes,
    guardian,
    mandates,
    notifications,
    clock,
    admin,
    chaos,
):
    app.include_router(module.router)
