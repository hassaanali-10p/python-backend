"""Analytics computations.

Chosen criterion: **prime counting**. Primes have meaningful density at every
scale (unlike, say, perfect numbers, which are vanishingly rare), so the
"handle large ranges efficiently" requirement is a real test.

Algorithm: a **segmented sieve of Eratosthenes**. A plain sieve needs an array
the size of the whole range; the segmented version only ever holds:
  - the base primes up to sqrt(end), and
  - one fixed-size window (segment) at a time.
So memory stays bounded regardless of how large `end` is, and composites are
struck out with C-level slice assignment rather than a Python loop.
"""

from __future__ import annotations

import math

# 64 KB window: big enough to amortize the per-segment overhead, small enough
# to keep memory flat for arbitrarily large `end`.
_SEGMENT_SIZE = 1 << 16


def _simple_sieve(limit: int) -> list[int]:
    """Return all primes in [2, limit] via a basic sieve."""
    if limit < 2:
        return []
    is_prime = bytearray([1]) * (limit + 1)
    is_prime[0] = is_prime[1] = 0
    for i in range(2, math.isqrt(limit) + 1):
        if is_prime[i]:
            is_prime[i * i :: i] = b"\x00" * len(is_prime[i * i :: i])
    return [i for i in range(2, limit + 1) if is_prime[i]]


def count_primes(start: int, end: int) -> int:
    """Count prime numbers in the inclusive range [start, end].

    Uses a segmented sieve so memory stays O(sqrt(end) + segment), not O(end).
    """
    if end < 2 or end < start:
        return 0
    low = max(start, 2)  # 0 and 1 are not prime
    if low > end:
        return 0

    base_primes = _simple_sieve(math.isqrt(end))

    count = 0
    seg_low = low
    while seg_low <= end:
        seg_high = min(seg_low + _SEGMENT_SIZE - 1, end)
        size = seg_high - seg_low + 1
        segment = bytearray([1]) * size  # 1 = prime, 0 = composite

        for p in base_primes:
            # First multiple of p to strike out: the larger of p*p and the
            # first multiple of p at or after seg_low.
            first = max(p * p, ((seg_low + p - 1) // p) * p)
            if first > seg_high:
                continue
            idx = first - seg_low
            strikes = (size - idx + p - 1) // p
            segment[idx::p] = b"\x00" * strikes

        count += sum(segment)  # remaining 1s are primes
        seg_low = seg_high + 1

    return count
