# Identity & Client Services

Two independent FastAPI applications demonstrating a real microservice auth
architecture: an **Identity Service** that issues signed JWTs, and a **Client
Application** (resource server) that validates those tokens **locally** and hosts
two functional services — an analytics endpoint and a multi-source data
aggregator.

The services are deliberately decoupled the way production OAuth2/OIDC systems
are: the Client never shares the Identity Service's signing key and never calls
it to validate a token on the request hot path.

---

## Table of contents
- [Architecture](#architecture)
- [Features](#features)
- [Tech stack](#tech-stack)
- [Project structure](#project-structure)
- [Getting started (Docker)](#getting-started-docker)
- [Getting started (local)](#getting-started-local)
- [Configuration](#configuration)
- [API reference](#api-reference)
- [Task A — Analytics](#task-a--analytics)
- [Task B — Data Aggregation](#task-b--data-aggregation)
- [Testing & coverage](#testing--coverage)
- [Design decisions](#design-decisions)

---

## Architecture

![System Architecture](docs/architecture.png)

**How auth works:** the Identity Service signs access tokens with an RSA private
key (RS256) and publishes the matching **public** key at a JWKS endpoint. The
Client fetches that public key once, caches it, and verifies every token itself.
This means no per-request network call to validate a token, no shared secret, and
the Client keeps working even if the Identity Service is briefly unavailable. The
Client only calls the Identity Service when it needs fresh profile data (`/me`).

For a deeper, plain-language walkthrough of each service — features, the design
choices and *why* we made them, and what every file does — see:
- [`docs/identity-service.md`](docs/identity-service.md)
- [`docs/client-app.md`](docs/client-app.md)

---

## Features

**Identity Service (App 1)**
- User registration and login (OAuth2 password flow)
- **RS256** JWT access tokens + **JWKS** endpoint for local verification
- Refresh tokens stored **hashed**, with **rotation and reuse detection**
- **Argon2** password hashing; constant-time login (no account enumeration)
- Role-based access control (admin / user)
- Async SQLAlchemy 2.0 + PostgreSQL + Alembic migrations

**Client Application (App 2)**
- Local RS256 token validation via cached JWKS (no per-request hop)
- Protected endpoints; role gating from the token claim
- Service-to-service user lookup (`/profile` → Identity `/me`)
- **Task A — Analytics:** prime counting over a numeric range via a segmented
  sieve, with execution timing (handles large ranges with bounded memory)
- **Task B — Data Aggregation:** concurrent fan-out to three external APIs with
  graceful partial-failure handling and a unified response

**Across both**
- Environment-based config, structured JSON logging, healthchecks
- Docker / docker-compose for the full stack
- Unit + integration tests (~93–94% coverage)

---

## Tech stack

| Concern | Choice |
|---|---|
| Language / framework | Python 3.11, FastAPI |
| Database / ORM | PostgreSQL, SQLAlchemy 2.0 (async) + asyncpg, Alembic |
| Auth | PyJWT (RS256), `cryptography`, `pwdlib` (Argon2) |
| HTTP client | httpx (async) |
| Config / logging | pydantic-settings, structured JSON to stdout |
| Tests | pytest, respx (HTTP mocking), pytest-cov |
| Tooling | Poetry, Docker, docker-compose |

---

## Project structure

```
backend/
├── docker-compose.yml          # postgres + identity-service + client-app
├── .env.example                # copy to .env for docker-compose
├── identity_service/           # App 1 — auth provider
│   ├── app/
│   │   ├── api/                # auth, users, jwks, health routers
│   │   ├── core/               # config, logging, security, jwt, keys (RSA/JWKS)
│   │   ├── db/                 # async engine + session
│   │   ├── models/             # User, RefreshToken
│   │   ├── schemas/            # Pydantic request/response models
│   │   ├── services/           # auth logic (register/login/rotate/revoke)
│   │   └── main.py
│   ├── alembic/                # migrations
│   ├── tests/
│   └── Dockerfile
├── client_app/                 # App 2 — resource server
│   ├── app/
│   │   ├── api/                # protected, analytics, aggregation, health, deps
│   │   ├── core/               # config, logging, jwks client, token validation
│   │   ├── schemas/
│   │   ├── services/           # identity lookup, analytics, aggregation
│   │   └── main.py
│   ├── tests/
│   └── Dockerfile
└── docs/
    ├── architecture.png
    ├── identity-service.md      # Identity Service explained (features, decisions, files)
    └── client-app.md            # Client App explained (incl. Task A/B justifications)
```

The Client App has **no database** — it is stateless and trusts the Identity
Service for authentication.

---

## Getting started (Docker)

The simplest way to run the whole stack.

**Prerequisites:** Docker + docker-compose.

```bash
# 1. Provide configuration (compose requires these — no baked-in defaults)
cp .env.example .env            # edit values if you like

# 2. Build and run all three services
docker-compose up --build
```

That starts:

| Service | URL | Notes |
|---|---|---|
| Identity Service | http://localhost:8001 | Swagger: `/docs` |
| Client App | http://localhost:8002 | Swagger: `/docs` |
| PostgreSQL | `localhost:5434` | host 5434 → container 5432 |

> Postgres is published on host **5434** to avoid clashing with a local
> PostgreSQL on 5432. The services reach it internally as `postgres:5432`.

Migrations run automatically on Identity Service startup. If you set
`BOOTSTRAP_ADMIN_EMAIL` / `BOOTSTRAP_ADMIN_PASSWORD` in `.env`, an admin user is
seeded so you can exercise the role-protected endpoints.

Useful commands:
```bash
docker-compose ps                       # status
docker-compose logs -f identity-service # follow logs (JSON)
docker-compose down                     # stop (keeps the DB volume)
docker-compose down -v                  # stop and wipe the DB volume
```

---

## Getting started (local)

Run the apps directly with Poetry (useful for fast iteration). You still need a
PostgreSQL for the Identity Service.

**Prerequisites:** Python 3.11+, Poetry, and a reachable PostgreSQL.

```bash
# Install dependencies (one venv per app)
poetry -C identity_service install
poetry -C client_app install
```

**Identity Service** (needs a database):
```bash
cd identity_service
export DATABASE_URL="postgresql+asyncpg://identity:identity@localhost:5432/identity"
poetry run alembic upgrade head
poetry run uvicorn app.main:app --reload --port 8001
```

**Client App** (separate terminal; defaults to `http://localhost:8001` for Identity):
```bash
cd client_app
poetry run uvicorn app.main:app --reload --port 8002
```

> On Windows PowerShell, set env vars with `$env:DATABASE_URL="..."`, or place
> them in an `.env` file in the app folder (loaded automatically).

---

## Configuration

All configuration comes from the environment (12-factor). Identity Service:

| Variable | Required | Default | Description |
|---|---|---|---|
| `DATABASE_URL` | ✅ | — | Async Postgres DSN (`postgresql+asyncpg://…`) |
| `JWT_PRIVATE_KEY_PATH` | | (ephemeral) | Path to a PEM RSA key; generated + persisted if absent |
| `JWT_ISSUER` | | `identity-service` | `iss` claim |
| `JWT_AUDIENCE` | | `client-app` | `aud` claim |
| `ACCESS_TOKEN_TTL_SECONDS` | | `900` | Access-token lifetime |
| `REFRESH_TOKEN_TTL_SECONDS` | | `604800` | Refresh-token lifetime |
| `BOOTSTRAP_ADMIN_EMAIL` / `_PASSWORD` | | — | If both set, seed an admin on startup |
| `LOG_LEVEL` / `ENVIRONMENT` | | `INFO` / `development` | |

Client App:

| Variable | Default | Description |
|---|---|---|
| `IDENTITY_SERVICE_URL` | `http://localhost:8001` | Base URL of the Identity Service |
| `JWT_ISSUER` / `JWT_AUDIENCE` | `identity-service` / `client-app` | Must match what Identity issues |
| `HTTP_TIMEOUT_SECONDS` | `5.0` | Outbound HTTP timeout |
| `ANALYTICS_MAX_END` | `100000000` | Upper bound for the analytics range (DoS guard) |

Secrets and connection strings are **never** committed — `.env`, `.env.test`, and
RSA private keys are gitignored; only `.env.example` / `.env.test.example`
templates are tracked.

---

## API reference

Full, interactive schemas are at each service's Swagger UI (`/docs`). Summary:

### Identity Service (`:8001`)
| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/auth/register` | — | Create a user |
| POST | `/auth/login` | — | Exchange credentials for access + refresh tokens |
| POST | `/auth/refresh` | — | Rotate a refresh token → new token pair |
| POST | `/auth/logout` | — | Revoke a refresh token |
| GET | `/me` | Bearer | Current user's profile |
| GET | `/users` | Bearer (admin) | List users |
| GET | `/users/{id}` | Bearer (admin) | Get a user by id |
| GET | `/.well-known/jwks.json` | — | Public keys for token verification |

### Client App (`:8002`)
| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/whoami` | Bearer | Identity from the token (validated locally) |
| GET | `/profile` | Bearer | Full profile, fetched from Identity `/me` |
| GET | `/admin/summary` | Bearer (admin) | Role-gated example |
| GET | `/analytics/primes` | — | Task A — count primes in a range |
| GET | `/aggregate/company` | — | Task B — company snapshot |

**Quick try:**
```bash
# Register + log in
curl -X POST localhost:8001/auth/register -H "Content-Type: application/json" \
  -d '{"email":"alice@example.com","password":"supersecret1"}'
TOKEN=$(curl -s -X POST localhost:8001/auth/login \
  -d "username=alice@example.com&password=supersecret1" | jq -r .access_token)

# Use the token against the Client App
curl localhost:8002/whoami -H "Authorization: Bearer $TOKEN"
```

---

## Task A — Analytics

`GET /analytics/primes?start=1&end=1000000`

Counts prime numbers in a range and reports how long it took.

```json
{
  "criteria": "prime",
  "range": { "start": 1, "end": 1000000 },
  "count": 78498,
  "execution_ms": 22.1,
  "algorithm": "segmented_sieve"
}
```

- **Segmented sieve of Eratosthenes** — holds only the base primes up to
  `√end` plus one fixed 64 KB window at a time, so memory stays bounded no matter
  how large `end` is. Composites are struck with C-level slice assignment.
- Input is bounded (`0 ≤ start ≤ end ≤ ANALYTICS_MAX_END`) → `422` otherwise.
- The CPU-bound work runs in a threadpool so it never blocks the event loop.

Verified against known values (π(10⁶)=78498, π(10⁷)=664579, π(10⁸)=5761455).

> **Scaling note:** the endpoint is synchronous because the spec asks for the
> execution duration in the response. For *unbounded* ranges the right evolution
> is a job-queue model (`202 Accepted` + a status/poll endpoint) so requests never
> block; the input bound + threadpool keep the synchronous version responsive here.

---

## Task B — Data Aggregation

`GET /aggregate/company?company=stripe`

A **company snapshot** built from three keyless public APIs, all keyed on one
company slug:

| Source | API | Contributes |
|---|---|---|
| `jobs` | Greenhouse job board | open roles + sample postings |
| `github` | GitHub organization | public repos, followers, description |
| `hacker_news` | HN (Algolia) search | recent discussion / buzz |

```json
{
  "company": "stripe",
  "sources": {
    "jobs":        { "status": "ok",    "data": { "open_roles": 496, "sample": [] } },
    "github":      { "status": "ok",    "data": { "public_repos": 0, "followers": 0 } },
    "hacker_news": { "status": "error", "error": "upstream timeout" }
  },
  "meta": { "fetched": 2, "failed": 1, "duration_ms": 312 }
}
```

- The three sources are independent, so they run **concurrently** with
  `asyncio.gather` — total latency ≈ the slowest call, not the sum.
- Each source is isolated: a timeout / HTTP error / parse error becomes a
  per-source `{"status":"error"}` instead of failing the whole response
  (**partial success**). The endpoint always returns `200` with the unified
  envelope; an empty company → `422`.

---

## Testing & coverage

```bash
# Client App — fully offline (mocks external APIs with respx)
poetry -C client_app run pytest

# Identity Service — integration tests against a real Postgres
#   copy identity_service/.env.test.example -> identity_service/.env.test
#   (point TEST_DATABASE_URL at a throwaway database)
poetry -C identity_service run pytest
```

The suites are predominantly **integration tests** (API-level, through the
framework — against a real Postgres for Identity, and against respx-mocked
external APIs for the Client), plus **unit tests** for the prime-counting
algorithm. Together they cover the high-risk paths: auth flow, refresh
**rotation + reuse detection**, RBAC denial, invalid/expired/tampered tokens,
Task A correctness + bounds, and Task B partial-failure.

Coverage report (HTML):
```bash
poetry -C client_app run pytest --cov=app --cov-report=html
poetry -C identity_service run pytest --cov=app --cov-report=html
# open <app>/htmlcov/index.html   (~93% client, ~94% identity)
```

---

## Design decisions

| Decision | Choice | Why |
|---|---|---|
| Token validation between services | **RS256 + JWKS** | Client validates locally with the published public key — no shared secret, no per-request hop, survives Identity downtime. How real OIDC works. |
| Refresh tokens | Opaque random, stored **hashed**, rotated, with **reuse detection** | Revocable (unlike a bare JWT); a replayed rotated token revokes the family, limiting theft blast radius. |
| Passwords | **Argon2** + dummy-verify on unknown users | Memory-hard hashing; constant login timing prevents account enumeration. |
| Primary keys | **UUID** | No sequential id enumeration. |
| Client database | **None** | Stateless resource server; authorization comes from the token's `role` claim. |
| Task A algorithm | **Segmented sieve** | Bounded memory for arbitrarily large ranges; meaningful prime density at every scale. |
| Task B resilience | `asyncio.gather` + per-source isolation | Concurrent fan-out with graceful partial success. |
| Config | Environment only, no committed secrets | 12-factor; fail-fast on missing required config. |
