"""Task B — aggregation response schemas (the unified envelope)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class SourceResult(BaseModel):
    """Per-source outcome. Either `data` (ok) or `error` (failed) is populated."""

    status: str  # "ok" | "error"
    data: dict[str, Any] | None = None
    error: str | None = None


class Meta(BaseModel):
    fetched: int
    failed: int
    duration_ms: float


class CompanySnapshot(BaseModel):
    company: str
    sources: dict[str, SourceResult]
    meta: Meta
