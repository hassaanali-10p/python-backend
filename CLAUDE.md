# FastAPI Developer Technical Assessment — Project Log

This file is the running record of the build. Each phase is logged here so
decisions, rationale, and verification steps are never lost between sessions.

---

## 1. Assessment Overview

Two **independent** FastAPI applications evaluating design, auth, authorization,
API development, scalability, performance, and code quality.

### Application 1 — Identity Service (auth provider)
- User registration, login
- JWT access token generation + refresh token support
- User profile endpoint
- Role-based access control (Admin / User)
- PostgreSQL integration
- OpenAPI/Swagger docs

### Application 2 — Client Application (resource server)
- Uses App 1 as the authentication provider
- Protected endpoints validate issued tokens
- Retrieves user info from the Identity Service
- Proper error handling for invalid/expired tokens
- **Task A — Analytics:** endpoint takes a numerical range, returns total count
  of matching results + execution duration + structured JSON; must handle large
  ranges efficiently.
- **Task B — Data Aggregation:** fetch from ≥3 external APIs, handle failures
  gracefully, meaningful errors, unified response.

### General requirements
Python 3.11+ · FastAPI · PostgreSQL · SQLAlchemy (or equiv ORM) · env-based
config · Docker · unit tests · logging + error handling · clean structure ·
README. Graded on: code quality, architecture, **security**, **performance**,
**testing**, docs, **resilience**.

---

## 2. Locked Architectural Decisions

| Decision | Choice | Rationale |
|---|---|---|
| **Token validation between services** | **RS256 + JWKS** | Identity signs with a private key; Client validates **locally** using public keys from a `/.well-known/jwks.json` endpoint (cached). No auth network hop per request → scalable; no shared secret → secure. How real OAuth2/OIDC providers work. |
| **User info retrieval** | Service-to-service HTTP call to Identity | Satisfies "retrieve user info from Identity Service" while tokens are still validated locally. |
| **Refresh tokens** | Stored **hashed** in DB, with **rotation + reuse detection** | Enables revocation; rotation limits blast radius of a leaked token. |
| **Password hashing** | Argon2 (via `pwdlib`) | Modern, memory-hard. |
| **RBAC** | `role` enum on user + FastAPI dependency (`require_role(...)`) | Reusable, declarative authorization. |
| **ORM / DB access** | SQLAlchemy 2.0 **async** + `asyncpg` + Alembic | Non-blocking I/O (matters for Task B fan-out); migrations for reproducibility. |
| **Client app database** | **None** | Client is stateless; trusts Identity for auth. Only Identity uses Postgres. |
| **Task A criterion** | **Prime counting** via **segmented sieve** | Meaningful density at all scales; segmented sieve handles large ranges with bounded memory. Pluggable-criteria registry so it's extensible. Input bounded to prevent DoS. |
| **Task B theme** | **Company Snapshot** over 3 **keyless** APIs | Greenhouse jobs + GitHub org + Hacker News (Algolia), all keyed on one company slug → coherent, useful combined result. Keyless → reproducible Docker/CI, no secrets. (Original plan was a weather "City Briefing"; switched because REST Countries v3.1 was deprecated and a jobs theme is more compelling.) |
| **Logging** | Structured JSON to stdout | 12-factor, aggregator-ready. |
| **Dependency mgmt** | **Poetry** (`package-mode = false`) | Resolved lockfiles for reproducibility; apps not libraries. |

### Task A response shape (target)
```json
{ "criteria": "prime", "range": {"start": 1, "end": 1000000},
  "count": 78498, "execution_ms": 42.7, "algorithm": "segmented_sieve" }
```

### Task B unified envelope (actual)
```json
{ "company": "stripe",
  "sources": {
    "jobs":        {"status": "ok",    "data": {"open_roles": 496, "sample": []}},
    "github":      {"status": "ok",    "data": {"public_repos": 0, "followers": 0}},
    "hacker_news": {"status": "error", "error": "upstream timeout"}
  },
  "meta": {"fetched": 2, "failed": 1, "duration_ms": 312} }
```
Per-source status → partial success; one dead API degrades gracefully.

---

## 3. Build Plan (phased, time-boxed)

| Phase | Scope | Status |
|---|---|---|
| **0** | Foundation: skeletons, docker-compose + Postgres, config, JSON logging, healthchecks | ✅ Done |
| **1** | Identity core: async models + Alembic, Argon2, register/login, RS256 + JWKS, refresh + rotation, `/me`, RBAC | ✅ Done |
| **2** | Client cross-service auth: JWKS client + cached keys, local validation, protected endpoint, user lookup, 401/403 | ✅ Done |
| **3** | Task A — analytics (segmented-sieve prime counter, bounded input, timing) | ✅ Done |
| **4** | Task B — aggregation (3 keyless APIs, concurrent fan-out, partial-success envelope) | ✅ Done |
| **5** | Tests: auth flow, RBAC denial, expired/invalid token, Task A correctness+perf, Task B partial-failure | ⏳ Next |
| **6** | README + polish (decision write-ups) | ⬜ |

**If time runs short:** trim test breadth → simplify refresh rotation → Task B
to 3 sources. **Never cut:** RS256/JWKS, async/pooling.

---

## 4. Environment / Tooling
- Python 3.11.2 available; Poetry 2.4.0 (local venvs resolved to a 3.14 interpreter — fine, `requires-python = ">=3.11,<4.0"`; Docker pins 3.11-slim).
- Docker 27.2.0; Compose is the **standalone** `docker-compose` (v2.29.2), **not** the `docker compose` plugin.
- Postgres only inside Docker (no local `psql`).

### Common commands
```bash
# Install deps (creates/uses a Poetry venv per app)
poetry -C identity_service install
poetry -C client_app install

# Run an app locally (needs DATABASE_URL for identity)
DATABASE_URL=postgresql+asyncpg://identity:identity@localhost:5432/identity \
  poetry -C identity_service run uvicorn app.main:app --reload --port 8001

# Full stack
docker-compose up --build        # NOTE: standalone binary, hyphenated

# Ports: identity → 8001, client → 8002 (both listen on 8000 in-container)
```

---

## 5. Phase Logs

### Phase 0 — Foundation ✅ (completed 2026-06-10)

**Goal:** two bootable, independent app skeletons with config, JSON logging,
Docker, Postgres, and healthchecks — no business logic yet.

**Structure created:**
```
backend/
├── docker-compose.yml          # postgres:16-alpine + identity + client
├── .env.example                # POSTGRES_*, LOG_LEVEL, ENVIRONMENT, DATABASE_URL note
├── .gitignore
├── CLAUDE.md                   # this file
├── identity_service/
│   ├── app/
│   │   ├── main.py             # FastAPI + lifespan + JSON logging wired
│   │   ├── core/config.py      # pydantic-settings (app meta + required database_url)
│   │   ├── core/logging.py     # JsonFormatter + dictConfig (root + uvicorn loggers)
│   │   └── api/health.py       # GET /health
│   ├── pyproject.toml + poetry.lock
│   ├── Dockerfile              # python:3.11-slim, non-root, dep layer cached
│   └── .dockerignore
└── client_app/                 # same layout; config has identity_service_url + http_timeout, NO database
```

**Dependencies (resolved versions) — what each one does:**

*Identity Service (runtime):*
| Package | Version | Purpose |
|---|---|---|
| `fastapi` | 0.136.3 | Web framework — routing, request/response validation via Pydantic, auto OpenAPI/Swagger docs. |
| `uvicorn[standard]` | 0.49.0 | ASGI server that runs the app. `[standard]` adds `uvloop`/`httptools`/`watchfiles` for speed + `--reload`. |
| `pydantic-settings` | 2.14.1 | Loads/validates config from environment variables into the typed `Settings` model. |
| `sqlalchemy[asyncio]` | 2.0.50 | Async ORM — models, queries, session/connection pooling against Postgres. |
| `asyncpg` | 0.31.0 | High-performance async PostgreSQL driver that SQLAlchemy's async engine talks through. |
| `alembic` | 1.18.4 | Database migrations — versioned, reproducible schema changes. |
| `pyjwt[crypto]` | 2.13.0 | Encode/decode + sign/verify JWTs. `[crypto]` pulls the RSA backend for **RS256** signing. |
| `cryptography` | 48.0.1 | Low-level crypto primitives; provides the RSA key handling PyJWT uses for RS256 / JWKS. |
| `pwdlib[argon2]` | 0.3.0 | Password hashing/verification using **Argon2** (memory-hard, modern). |
| `python-multipart` | 0.0.32 | Parses `application/x-www-form-urlencoded` bodies — required for OAuth2 password-form login. |

*Identity Service (dev):*
| Package | Version | Purpose |
|---|---|---|
| `pytest` | 9.0.3 | Test runner / framework. |
| `pytest-asyncio` | 1.4.0 | Lets pytest run `async def` tests (async DB/endpoint tests). |
| `httpx` | 0.28.1 | HTTP client used by FastAPI's `TestClient` to exercise endpoints in tests. |

*Client App (runtime):*
| Package | Version | Purpose |
|---|---|---|
| `fastapi` | 0.136.3 | Web framework (same role as above). |
| `uvicorn[standard]` | 0.49.0 | ASGI server. |
| `pydantic-settings` | 2.14.1 | Env-based config (`identity_service_url`, timeouts, etc.). |
| `httpx` | 0.28.1 | **Async** HTTP client — Task B external API fan-out **and** service-to-service calls to Identity (incl. fetching JWKS). Runtime dep here (not just tests). |
| `pyjwt[crypto]` | 2.13.0 | Verifies RS256 access tokens issued by Identity. |
| `cryptography` | 48.0.1 | RSA backend for verifying token signatures against JWKS public keys. |

*Client App (dev):*
| Package | Version | Purpose |
|---|---|---|
| `pytest` | 9.0.3 | Test runner. |
| `pytest-asyncio` | 1.4.0 | Async test support. |
| `respx` | 0.23.1 | Mocks `httpx` requests — simulate external APIs (Task B partial failures) and Identity calls without real network. |

Note: the Client app does **not** include `sqlalchemy`/`asyncpg`/`alembic` — it is
stateless and has no database.

**Key implementation notes:**
- `main.py` uses the modern `lifespan` context manager (not deprecated `on_event`).
- `JsonFormatter` promotes any `extra={...}` context to top-level JSON fields;
  reserved LogRecord attrs filtered out. uvicorn loggers routed through it.
- Docker healthchecks use a `python -c urllib.request` one-liner (no curl in slim image).
- `docker-compose`: Postgres has `pg_isready` healthcheck; services use
  `depends_on: condition: service_healthy` for ordered startup. Client points at
  `http://identity-service:8000` over the compose network.

**Decision correction during Phase 0:**
- Originally `database_url` had a localhost default with embedded credentials.
  Changed to a **required field with no default** (`database_url: str`). Reason:
  (1) connection strings/credentials must not live in source, even as placeholders;
  (2) a required external dependency should **fail fast** on misconfig rather than
  silently fall back to localhost. Documented in `.env.example`.
- Left `client_app.identity_service_url` with a `localhost:8001` default — it's a
  non-sensitive service URL, so a dev-convenience default is acceptable (different
  risk profile from a credentialed DB string).

**Verification performed:**
- ✅ Both apps boot via TestClient; `GET /health` → `200 {"status":"ok"}`.
- ✅ Logs emit as structured JSON.
- ✅ `poetry.lock` written for both apps.
- ✅ Identity fails fast with clear `database_url Field required` error when unset;
  boots when `DATABASE_URL` provided.
- ✅ `docker-compose config` validates.
- ⚠️ Did **not** run full `docker-compose build` (time). Plan: do one real
  build + up after Phase 1 to validate the container path.

---

### Phase 1 — Identity Service core ✅ (completed 2026-06-10)

**Goal:** full auth provider — models + migrations, registration, login, RS256
JWT issuance, refresh rotation, `/me`, RBAC, JWKS.

**Files added (identity_service/app):**
```
core/keys.py        # RSA key load/generate/persist; RFC 7638 kid; JWKS builder
core/security.py    # Argon2 hash/verify + dummy_verify (timing); refresh token gen + SHA-256 hash
core/jwt.py         # RS256 access-token encode/decode (iss/aud/exp/kid validated)
db/base.py          # DeclarativeBase
db/session.py       # async engine (pool_pre_ping) + session dependency
models/user.py      # User (UUID pk, email unique, role enum, is_active, ts)
models/refresh_token.py  # RefreshToken (user_id FK, token_hash unique, expires/revoked)
schemas/user.py     # UserCreate (pwd 8..128), UserRead
schemas/token.py    # TokenPair, RefreshRequest
services/auth.py    # register/authenticate/issue/rotate/revoke + reuse detection
api/deps.py         # oauth2 scheme, get_current_user, require_role factory
api/auth.py         # POST /auth/{register,login,refresh,logout}
api/users.py        # GET /me, GET /users (admin), GET /users/{id} (admin)
api/jwks.py         # GET /.well-known/jwks.json
alembic/ + alembic.ini + versions/0001_initial.py
```
`main.py` wires routers + optional bootstrap-admin seed on startup.
`config.py` gained JWT settings, token TTLs, key path, bootstrap-admin vars.
Added `email-validator` dep (for `EmailStr`).

**Security decisions implemented:**
- **Argon2** password hashing; **dummy-verify** on unknown users → constant login timing (no account enumeration).
- Generic `Incorrect email or password` on login (no field leak).
- **RS256**: private key in Identity only, **never committed**. Loaded from `JWT_PRIVATE_KEY_PATH`, else generated+persisted there, else ephemeral in-memory (dev) with a loud warning. `kid` = RFC 7638 thumbprint in token header + JWKS → clean rotation.
- Access-token claims: `iss/aud/sub/iat/nbf/exp/jti/role/token_type`; decode validates signature + iss + aud + exp and requires `token_type == "access"`.
- **Refresh tokens are opaque random (~256-bit) strings, stored SHA-256-hashed** — never JWTs. Rotated on every use; **reuse of a rotated token revokes the whole family** (theft defense).
- **UUID** PKs (no ID enumeration). 401 vs 403 correct; `WWW-Authenticate: Bearer` on 401.

**Token-validation contract for Phase 2 (Client):** validate RS256 locally via
JWKS public key; expect `iss=identity-service`, `aud=client-app`; select key by
`kid`. Fetch user profile by calling Identity `GET /me` with the bearer token.

**docker-compose / Docker changes:**
- identity Dockerfile copies `alembic/` + `alembic.ini`.
- identity service `command` runs `alembic upgrade head` before uvicorn.
- env added: `JWT_PRIVATE_KEY_PATH=/home/appuser/keys/jwt_private.pem` (stable
  across restarts; appuser-writable), `BOOTSTRAP_ADMIN_EMAIL/PASSWORD`.

**Verification performed (against real Postgres on :5433 via TestClient):**
- ✅ `alembic upgrade head` creates schema cleanly.
- ✅ 16/16 e2e checks PASS: register 201 / dup 409 / weak-pwd 422 / wrong-pwd 401 /
  login 200 / `/me` 401-no-token & 200-with-token / `/users` 403 as user & 200 as
  admin / refresh rotates / **reuse old refresh → 401 + family revoked** / JWKS RSA.
- ✅ JWT round-trip; JWKS `kid` matches token header `kid`.
- ✅ Bootstrap admin seeded on startup; RBAC enforced.
- (e2e was a throwaway script, removed; formal pytest suite is Phase 5.)

**Environment note / gotcha for next session:**
- Host machine runs a **PostgreSQL 15 Windows service** (`postgresql-x64-15`) on
  **5432** that we could not stop (needs elevation; user's stop attempt didn't
  take). For local validation we ran the test Postgres container on **5433**.
  **For `docker-compose up` to work, host 5432 must be freed** (stop that service
  from an elevated shell) — otherwise the postgres port mapping won't bind.
- Test container still running: `docker rm -f assess_pg` to clean up.
- Poetry local venv uses Python 3.14 (fine); Docker pins 3.11.

---

### Phase 2 — Client cross-service auth ✅ (completed 2026-06-11)

**Goal:** Client App validates Identity's RS256 tokens **locally** via cached
JWKS public keys (no per-request hop), exposes protected endpoints, and does a
service-to-service profile lookup.

**Files added (client_app/app):**
```
core/jwks.py        # JWKSClient: fetch + cache public keys by kid; refetch on miss; asyncio.Lock
core/security.py    # verify_access_token: local RS256 verify w/ cached public key (mirrors Identity decode)
services/identity.py# fetch_user_profile -> Identity GET /me (service-to-service); IdentityServiceError
api/deps.py         # HTTPBearer(auto_error=False) -> 401; get_current_claims; require_role(*roles)
api/protected.py    # GET /whoami (from claims), /profile (calls Identity /me), /admin/summary (admin-only)
```
`config.py` gained `jwks_path`, `jwt_issuer`, `jwt_audience`, `jwt_algorithm`,
and a `jwks_url` property. `main.py` lifespan creates a **shared `httpx.AsyncClient`**
(connection pooling, reused by JWKS fetch + /me calls + future Task B) and a
`JWKSClient`, both on `app.state`.

**Design decisions:**
- **Local validation, no hot-path network call.** JWKS fetched once, cached by
  `kid`; refetch only on a cache miss (unknown `kid` ⇒ handles key rotation).
  `asyncio.Lock` prevents a fetch stampede. Public key built via
  `jwt.algorithms.RSAAlgorithm.from_jwk`.
- **Authorization from the token's `role` claim** — no DB, no lookup (client is
  stateless).
- **HTTPBearer (not OAuth2PasswordBearer)** — client is a resource server, not a
  token issuer; Swagger shows a "paste your token" box. `auto_error=False` so a
  missing header returns **401** (+ `WWW-Authenticate: Bearer`), not FastAPI's 403.
- **User lookup** = the one deliberate call to Identity (`/me`), only when full
  profile is needed; failures map to **502** with a clear message.

**Verification (Identity live on :8001 + Postgres :5433; client via TestClient):**
- ✅ 7/7 checks PASS: `/whoami` 401-no-token / 401-garbage / 401-tampered (sig fail)
  / 200-valid-user; `/profile` 200 (fetches Identity `/me`); `/admin/summary`
  403-as-user & 200-as-admin.
- ✅ Logs confirm JWKS fetched **once** then served from cache (no per-request hop).
- (Throwaway script, removed; formal pytest suite is Phase 5.)

---

### Phase 3 — Task A: Analytics ✅ (completed 2026-06-11)

**Goal:** endpoint that takes a numerical range and returns count of matching
results + execution duration + structured JSON; must handle large ranges
efficiently.

**Criterion chosen:** **prime counting** (meaningful density at every scale).
**Algorithm:** **segmented sieve of Eratosthenes** — only holds base primes up to
`sqrt(end)` + one 64 KB window at a time ⇒ **memory bounded regardless of `end`**.
Composites struck out with C-level slice assignment (no Python inner loop).

**Files added (client_app/app):**
```
services/analytics.py   # _simple_sieve + count_primes (segmented sieve)
schemas/analytics.py    # NumberRange, AnalyticsResult
api/analytics.py        # GET /analytics/primes?start&end
```
`config.py` gained `analytics_max_end = 100_000_000` (DoS guard on range size).
`main.py` includes the analytics router. Endpoint is **public** (Task A/B are
standalone functional services; auth is demonstrated on the /protected routes).

**Design notes:**
- CPU-bound work runs via `run_in_threadpool` so it never blocks the event loop.
- Input bounded: `start>=0`, `end>=start`, `end<=analytics_max_end` → else **422**.
- Timing measured with `perf_counter` around the computation only.
- Response shape: `{criteria, range:{start,end}, count, execution_ms, algorithm}`.

**Verification:**
- ✅ Correct vs known prime counts: π(10)=4, π(100)=25, π(1000)=168,
  π(10⁶)=78498, π(10⁷)=664579, π(10⁸)=5761455; range `[10,20]`=4; `[0,1]`=0.
- ✅ Performance: 10⁶ ≈ 20 ms, 10⁷ ≈ 265 ms, 10⁸ (cap) ≈ 5.4 s, flat memory.
- ✅ Endpoint: 200 structured response; 422 for end<start / over-cap / negative.
- (Throwaway scripts removed; formal pytest suite is Phase 5.)

---

### Phase 4 — Task B: Data Aggregation ✅ (completed 2026-06-11)

**Goal:** endpoint that fetches from ≥3 external APIs, handles failures
gracefully with meaningful errors, and returns a unified response.

**Theme:** **Company Snapshot** — one input (a company slug, e.g. `stripe`),
three keyless public APIs fanned out concurrently:
- `jobs`        → Greenhouse `boards-api/v1/boards/{slug}/jobs` (open roles + samples)
- `github`      → GitHub `api.github.com/orgs/{slug}` (repos, followers, description)
- `hacker_news` → HN Algolia `hn.algolia.com/api/v1/search?query={slug}` (recent stories)

**Files added (client_app/app):**
```
services/aggregation.py  # 3 fetchers + _run_source isolation + build_company_snapshot (asyncio.gather)
schemas/aggregation.py   # SourceResult, Meta, CompanySnapshot
api/aggregation.py       # GET /aggregate/company?company=
```
`main.py` shared `httpx.AsyncClient` now sets `follow_redirects=True` + a
`User-Agent` (GitHub rejects requests without one). Endpoint **public**.

**Design notes (async + resilience):**
- Sources are **independent** ⇒ `asyncio.gather` runs all three concurrently;
  total latency ≈ slowest call, not the sum. (No prerequisite step.)
- `_run_source` wraps each call: timeout / HTTP status / network / parse errors
  become a per-source `{"status":"error","error":...}` ⇒ **partial success**.
- Endpoint always returns **200** with the unified envelope; per-source failures
  are reported inside it (not as a top-level error). Empty company → **422**.
- Envelope: `{company, sources:{name:{status,data|error}}, meta:{fetched,failed,duration_ms}}`.

**Gotcha discovered:** original weather "City Briefing" plan abandoned —
**REST Countries v3.1 is deprecated** (returns a migrate-to-v5 error), and the
forecast host had a live 502 during testing. Jobs theme is more compelling and
all three chosen APIs are stable + keyless.

**Verification (live external APIs via TestClient):**
- ✅ `company=stripe` → all 3 ok (jobs reported 496 open roles + samples).
- ✅ `company=google` → **partial success**: jobs 404 (`upstream not found`),
  github + hacker_news ok; `meta {fetched:2, failed:1}`.
- ✅ empty company → 422.
- (Throwaway script removed; formal pytest suite is Phase 5.)

**Note:** unauthenticated GitHub API is rate-limited (~60 req/hr/IP) — fine for
the assessment; an optional token would raise it (left out to stay keyless).
