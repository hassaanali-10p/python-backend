"""Analytics response schemas."""

from __future__ import annotations

from pydantic import BaseModel


class NumberRange(BaseModel):
    start: int
    end: int


class AnalyticsResult(BaseModel):
    criteria: str
    range: NumberRange
    count: int
    execution_ms: float
    algorithm: str
