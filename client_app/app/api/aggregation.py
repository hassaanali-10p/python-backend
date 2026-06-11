"""Task B — Data Aggregation: unified "Company Snapshot" from multiple APIs."""

from __future__ import annotations

from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, Query

from app.api.deps import get_http_client
from app.schemas.aggregation import CompanySnapshot
from app.services.aggregation import build_company_snapshot

router = APIRouter(prefix="/aggregate", tags=["aggregation"])


@router.get(
    "/company",
    response_model=CompanySnapshot,
    summary="Aggregate jobs, GitHub, and Hacker News for a company",
)
async def company_snapshot(
    company: Annotated[
        str,
        Query(
            min_length=1,
            max_length=100,
            # Restrict to a safe slug charset: prevents path/redirect tricks that
            # could turn this into an SSRF vector (the value goes into outbound URLs).
            pattern=r"^[A-Za-z0-9-]+$",
            description="Company slug, e.g. 'stripe'",
        ),
    ],
    http_client: Annotated[httpx.AsyncClient, Depends(get_http_client)],
) -> CompanySnapshot:
    # Always returns 200 with the unified envelope; individual upstream failures
    # are reported per-source (partial success), not as a top-level error.
    return await build_company_snapshot(http_client, company)
