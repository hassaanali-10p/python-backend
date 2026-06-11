# Client Application — Explained

This document explains the **Client Application** in plain language: what it does,
the choices we made and why (including **why prime numbers** and **why the
segmented sieve** for Task A), and what every file is for.

---

## 1. What this service does

The Client App is a **resource server** — an app that holds protected features and
trusts the Identity Service for login. It does **not** store users or passwords.

It offers:
- **Protected endpoints** that only work with a valid token (`/whoami`, `/profile`)
- An **admin-only** endpoint (`/admin/summary`)
- **Task A — Analytics** (`/analytics/primes`): count special numbers in a range
- **Task B — Data Aggregation** (`/aggregate/company`): combine several APIs into
  one response

---

## 2. The main ideas (and why we chose them)

### a. It checks tokens by itself (no call to the login server every time)

When a request arrives with a token, the Client checks it **locally** using the
Identity Service's **public key**. It fetches that key once (from the JWKS URL),
keeps it in memory, and reuses it.

**Why:** this is fast (no network call to validate each request) and resilient
(the Client keeps working even if the Identity Service is briefly down). It only
calls the Identity Service when it needs **fresh profile data** (`/profile` →
Identity's `/me`).

### b. No database

The Client is **stateless**. Whether you're an admin or a normal user is written
*inside* the token (the `role` claim), so the Client can decide what you're
allowed to do without looking anything up. Fewer moving parts, easier to scale.

### c. Correct error codes

- **401 Unauthorized** — we don't know who you are (missing / bad / expired token).
- **403 Forbidden** — we know who you are, but you're not allowed (wrong role).

---

## 3. Task A — Analytics (the key choices)

**The endpoint:** `GET /analytics/primes?start=1&end=1000000` → returns the count
of matching numbers, how long it took, and a structured JSON response.

### Why count *prime numbers*?

The task says "count matching results in a range" and lets us choose the
criterion. We chose **prime numbers**. Here's the reasoning:

- The real challenge in the task is **"handle large ranges efficiently."** That
  only matters if the thing we're counting stays **common** as numbers grow.
- **Primes stay common at every scale** — there are always plenty of them, even up
  to a billion. So counting them across a huge range is a genuine performance test.
- We rejected the obvious alternatives because they're **too rare** to be a real
  test:
  - **Perfect numbers** — only a handful are known *in all of history*. Counting
    them in a range is trivial; there's nothing to optimize.
  - **Armstrong numbers** — there are only about 88 of them total in base 10. Same
    problem — the count flattens out and "large range efficiency" becomes meaningless.

So primes give us a criterion that is **meaningful, dense, and actually hard to do
fast** — which is exactly what lets us show good performance work.

### Why the *segmented sieve* algorithm?

To count primes you must find them. There are three ways, from worst to best:

1. **Check each number one by one** (trial division) — far too slow for large
   ranges (would take minutes or hours at a billion).
2. **Basic Sieve of Eratosthenes** — fast, but it needs an array as big as the
   whole range. For a range up to a billion that's about **1 GB of memory** — it
   won't fit.
3. **Segmented sieve** (what we use) — the same "cross out the multiples" idea, but
   done **one small window at a time**. It only ever holds:
   - the small list of base primes up to the square root of `end`, plus
   - **one 64 KB window** of the range.

   So the **memory stays tiny and constant** no matter how big the range is. That's
   the whole point: it handles huge ranges efficiently, which is what the task asks
   for.

**Other safeguards:**
- The CPU work runs in a **threadpool**, so a big calculation doesn't freeze the
  server for other users.
- The range is **bounded** (`end ≤ 100,000,000`) so nobody can send a
  ridiculous value and tie up the server (a simple denial-of-service guard).
- Timing is measured with a precise clock and returned as `execution_ms`.

Verified correct against well-known values: π(1,000,000) = 78,498, etc.

---

## 4. Task B — Data Aggregation

**The endpoint:** `GET /aggregate/company?company=stripe` → a single "company
snapshot" built from three public APIs:

| Source | API | What it adds |
|---|---|---|
| `jobs` | Greenhouse job board | how many roles they're hiring for |
| `github` | GitHub organization | their open-source presence (repos, followers) |
| `hacker_news` | Hacker News search | recent discussion / buzz |

### Why these, and why this shape?

- All three are **keyless** (no API keys needed), so the app runs anywhere with no
  secrets to manage.
- They all key off **one input** (a company name), so the combined result is
  coherent — a quick "what's this company like?" snapshot for someone researching
  a job.

### How it handles speed and failures

- The three calls are **independent**, so we run them **at the same time** with
  `asyncio.gather`. Total time ≈ the slowest single call, not the sum of all three.
- Each source is **isolated**: if one API times out or errors, that source comes
  back as `{"status": "error"}` while the others still succeed. The endpoint always
  returns `200` with a unified envelope — **one dead API never sinks the whole
  response** ("partial success"). The `meta` section reports how many succeeded.

---

## 5. What each file does

```
client_app/app/
├── main.py                  # starts the app; creates the shared HTTP client + JWKS client
├── core/
│   ├── config.py            # reads settings from environment variables
│   ├── logging.py           # JSON logging setup
│   ├── jwks.py              # fetches + caches the Identity public key (by kid)
│   └── security.py          # verifies an access token locally (RS256)
├── schemas/
│   ├── analytics.py         # response shape for Task A
│   └── aggregation.py       # response shape for Task B
├── services/
│   ├── identity.py          # calls Identity's /me to fetch a full profile
│   ├── analytics.py         # the segmented-sieve prime counter
│   └── aggregation.py       # the 3 fetchers + concurrent fan-out logic
└── api/
    ├── deps.py              # shared helpers: extract token, validate, require role
    ├── protected.py         # endpoints: /whoami, /profile, /admin/summary
    ├── analytics.py         # endpoint: /analytics/primes  (Task A)
    ├── aggregation.py       # endpoint: /aggregate/company (Task B)
    └── health.py            # endpoint: /health
```

**A bit more detail on the important ones:**

- **`core/jwks.py`** — the `JWKSClient`. It downloads the Identity Service's public
  keys once, stores them in memory keyed by `kid`, and reuses them. It only goes
  back to the network if a token arrives signed by a key it hasn't seen (which
  happens after the Identity Service rotates its key). A lock makes sure a burst of
  requests triggers just one download, not many.

- **`core/security.py`** — `verify_access_token` reads the `kid` from the token,
  gets the right public key from the JWKS client, and checks the signature, issuer,
  audience, and expiry. If anything is wrong it raises an error that becomes a 401.

- **`services/analytics.py`** — `count_primes` is the segmented sieve described
  above. `_simple_sieve` builds the small list of base primes it needs.

- **`services/aggregation.py`** — has one fetch function per source
  (`_fetch_jobs`, `_fetch_github`, `_fetch_hacker_news`), a wrapper (`_run_source`)
  that turns any failure into a clean per-source error, and `build_company_snapshot`
  which runs all three concurrently and assembles the unified response.

- **`services/identity.py`** — `fetch_user_profile` makes the one deliberate call
  to the Identity Service (`/me`), forwarding the user's token, for the `/profile`
  endpoint.

- **`api/deps.py`** — `get_token` pulls the Bearer token out of the request,
  `get_current_claims` validates it (401 on failure), and `require_role("admin")`
  enforces roles (403 on failure).

- **`main.py`** — on startup it creates **one shared HTTP client** (reused for JWKS
  fetches, the `/me` lookup, and Task B's external calls — connection pooling) and
  the JWKS client, and includes all the routers.

---

## 6. The flow, end to end

1. A request arrives with `Authorization: Bearer <token>`.
2. The Client reads the token, fetches the Identity public key (once, then cached),
   and **verifies the token itself** — no call to the Identity Service.
3. If valid, the endpoint runs:
   - `/whoami` → returns who you are, straight from the token.
   - `/profile` → also calls Identity's `/me` for your full details.
   - `/analytics/primes` → runs the segmented sieve and returns the count + timing.
   - `/aggregate/company` → fans out to three APIs and returns a combined result.
