"""Task A — analytics endpoint: correctness, bounds, and response shape."""

import pytest

from app.services.analytics import count_primes


# --- Algorithm correctness (the part that matters most) ---

@pytest.mark.parametrize(
    "start,end,expected",
    [
        (0, 1, 0),          # neither 0 nor 1 is prime
        (0, 10, 4),         # 2,3,5,7
        (10, 20, 4),        # 11,13,17,19
        (1, 100, 25),       # pi(100)
        (1, 1000, 168),     # pi(1000)
        (1, 1_000_000, 78498),  # pi(1e6) — known value
    ],
)
def test_count_primes_matches_known_values(start, end, expected):
    assert count_primes(start, end) == expected


def test_count_primes_empty_range_is_zero():
    assert count_primes(50, 10) == 0  # end < start


# --- Endpoint behaviour ---

def test_endpoint_returns_structured_result(client):
    r = client.get("/analytics/primes", params={"start": 1, "end": 1000})
    assert r.status_code == 200
    body = r.json()
    assert body["criteria"] == "prime"
    assert body["algorithm"] == "segmented_sieve"
    assert body["range"] == {"start": 1, "end": 1000}
    assert body["count"] == 168
    assert isinstance(body["execution_ms"], (int, float))
    assert body["execution_ms"] >= 0


def test_endpoint_rejects_end_before_start(client):
    r = client.get("/analytics/primes", params={"start": 100, "end": 10})
    assert r.status_code == 422


def test_endpoint_rejects_over_cap(client):
    r = client.get("/analytics/primes", params={"start": 0, "end": 999_999_999})
    assert r.status_code == 422


def test_endpoint_rejects_negative_start(client):
    r = client.get("/analytics/primes", params={"start": -5, "end": 10})
    assert r.status_code == 422
