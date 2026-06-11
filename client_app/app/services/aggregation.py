"""Task B — Data Aggregation: a "Company Snapshot" over several public APIs.

Theme: everything keys off a single company slug, so the combined result is
coherent and useful for researching a company:
    - jobs        : open roles (Greenhouse job board)
    - github      : open-source / engineering presence (GitHub org)
    - hacker_news : recent discussion / buzz (HN Algolia search)

All three are **keyless** public APIs and **independent**, so they run fully
concurrently with `asyncio.gather` — total latency ≈ the slowest single call,
not the sum. Each source is isolated: a timeout/HTTP/parse error becomes a
per-source {"status": "error", ...} rather than failing the whole response
(partial success). One company missing from one source still yields a useful
combined result.
"""

from __future__ import annotations

import asyncio
import logging
from time import perf_counter
from typing import Any, Awaitable

import httpx

from app.schemas.aggregation import CompanySnapshot, Meta, SourceResult

logger = logging.getLogger(__name__)

GREENHOUSE_URL = "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"
GITHUB_ORG_URL = "https://api.github.com/orgs/{slug}"
HN_SEARCH_URL = "https://hn.algolia.com/api/v1/search"

_SAMPLE_SIZE = 5


# --- The three independent sources. Each returns trimmed data or raises. ---

async def _fetch_jobs(client: httpx.AsyncClient, slug: str) -> dict[str, Any]:
    response = await client.get(GREENHOUSE_URL.format(slug=slug))
    response.raise_for_status()
    jobs = response.json().get("jobs", [])
    sample = [
        {"title": j.get("title"), "location": (j.get("location") or {}).get("name")}
        for j in jobs[:_SAMPLE_SIZE]
    ]
    return {"open_roles": len(jobs), "sample": sample}


async def _fetch_github(client: httpx.AsyncClient, slug: str) -> dict[str, Any]:
    response = await client.get(GITHUB_ORG_URL.format(slug=slug))
    response.raise_for_status()
    org = response.json()
    return {
        "name": org.get("name"),
        "description": org.get("description"),
        "public_repos": org.get("public_repos"),
        "followers": org.get("followers"),
        "location": org.get("location"),
        "url": org.get("html_url"),
    }


async def _fetch_hacker_news(client: httpx.AsyncClient, slug: str) -> dict[str, Any]:
    response = await client.get(
        HN_SEARCH_URL,
        params={"query": slug, "tags": "story", "hitsPerPage": _SAMPLE_SIZE},
    )
    response.raise_for_status()
    payload = response.json()
    recent = [
        {
            "title": h.get("title"),
            "points": h.get("points"),
            "comments": h.get("num_comments"),
            "url": f"https://news.ycombinator.com/item?id={h.get('objectID')}",
        }
        for h in payload.get("hits", [])
    ]
    return {"mentions": payload.get("nbHits"), "recent": recent}


async def _run_source(name: str, awaitable: Awaitable[dict]) -> tuple[str, SourceResult]:
    """Run one source, converting any failure into a per-source error result."""
    try:
        data = await awaitable
        return name, SourceResult(status="ok", data=data)
    except httpx.TimeoutException:
        return name, SourceResult(status="error", error="upstream timeout")
    except httpx.HTTPStatusError as exc:
        detail = "not found" if exc.response.status_code == 404 else f"HTTP {exc.response.status_code}"
        return name, SourceResult(status="error", error=f"upstream {detail}")
    except httpx.RequestError:
        return name, SourceResult(status="error", error="upstream unreachable")
    except Exception as exc:  # parse errors, unexpected shapes, etc.
        logger.warning("aggregation source failed", extra={"source": name, "error": str(exc)})
        return name, SourceResult(status="error", error="unexpected error processing upstream response")


async def build_company_snapshot(client: httpx.AsyncClient, company: str) -> CompanySnapshot:
    slug = company.strip().lower()
    started = perf_counter()

    # Fan out: the three sources are independent and run concurrently.
    results = await asyncio.gather(
        _run_source("jobs", _fetch_jobs(client, slug)),
        _run_source("github", _fetch_github(client, slug)),
        _run_source("hacker_news", _fetch_hacker_news(client, slug)),
    )
    sources = dict(results)

    fetched = sum(1 for r in sources.values() if r.status == "ok")
    duration_ms = round((perf_counter() - started) * 1000, 1)

    return CompanySnapshot(
        company=slug,
        sources=sources,
        meta=Meta(fetched=fetched, failed=len(sources) - fetched, duration_ms=duration_ms),
    )
