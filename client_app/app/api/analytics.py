"""Task A — Analytics: count matching numbers in a range, with timing.

Chosen criterion is prime counting (see services/analytics.py). The CPU-bound
work runs in a threadpool so it never blocks the event loop, and the range is
bounded to keep response times sane.
"""

from __future__ import annotations

from time import perf_counter
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.concurrency import run_in_threadpool

from app.core.config import get_settings
from app.schemas.analytics import AnalyticsResult, NumberRange
from app.services.analytics import count_primes

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get(
    "/primes",
    response_model=AnalyticsResult,
    summary="Count prime numbers in a range, with execution time",
)
async def count_primes_in_range(
    start: Annotated[int, Query(ge=0, description="Range start (inclusive)")] = 0,
    end: Annotated[int, Query(ge=0, description="Range end (inclusive)")] = 100,
) -> AnalyticsResult:
    settings = get_settings()

    if end < start:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="`end` must be greater than or equal to `start`",
        )
    if end > settings.analytics_max_end:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"`end` must not exceed {settings.analytics_max_end}",
        )

    started = perf_counter()
    count = await run_in_threadpool(count_primes, start, end)
    execution_ms = round((perf_counter() - started) * 1000, 3)

    return AnalyticsResult(
        criteria="prime",
        range=NumberRange(start=start, end=end),
        count=count,
        execution_ms=execution_ms,
        algorithm="segmented_sieve",
    )
