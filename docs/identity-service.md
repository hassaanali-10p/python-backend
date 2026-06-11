# Identity Service — Explained

This document explains the **Identity Service** in plain language: what it does,
the choices we made and why, and what every file is for.

---

## 1. What this service does

The Identity Service is the **login system**. It is the only place that:
- stores users and their passwords, and
- can create login tokens.

Every other app trusts it to answer one question: *"is this person really who
they say they are?"*

It offers:
- **Register** — create an account
- **Login** — check email + password, hand back tokens
- **Refresh** — swap an expiring token for a fresh one
- **Logout** — cancel a refresh token
- **Profile** (`/me`) — tell a logged-in user their own details
- **Roles** — mark some users as `admin`, and protect admin-only endpoints
- **JWKS** — publish a "public key" so other apps can check its tokens themselves

---

## 2. The main ideas (and why we chose them)

### a. Two kinds of tokens: access and refresh

When you log in you get **two** tokens:

| Token | What it is | Lives | Used for |
|---|---|---|---|
| **Access token** | a signed JWT (carries your id + role) | short (15 min) | sent on every request to prove who you are |
| **Refresh token** | a random secret string | long (7 days) | only used to get a new access token |

**Why two?** A JWT is fast to check (no database needed) but it **cannot be
cancelled** before it expires. So we keep it **short-lived** to limit damage if
it leaks. The refresh token is **long-lived but cancellable** (we store it in the
database), so users don't have to log in every 15 minutes, and we can revoke it
if needed. Best of both worlds.

### b. RS256 + JWKS — how other apps trust our tokens

We sign access tokens with a **private key** (RS256). We never share that key.
Instead we publish the matching **public key** at `/.well-known/jwks.json`.

- The **private key** can *create* signatures (only we have it).
- The **public key** can only *check* signatures — it **cannot** create them.

So we can hand the public key to anyone, and they can verify our tokens without
being able to forge new ones, and **without calling us on every request**.

**Why not a shared password (HS256)?** With a shared secret, anyone who can
*check* a token can also *make* one. RS256 splits those two abilities, which is
why real systems (Google, Auth0, etc.) use it.

### c. Refresh tokens: hashed, rotated, with reuse detection

- We store only a **hash** of each refresh token (like we do for passwords), so a
  database leak doesn't expose usable tokens.
- Each time a refresh token is used, we **rotate** it — issue a brand-new one and
  retire the old one.
- If an **old, already-used** refresh token shows up again, that usually means it
  was stolen. We treat it as theft and **cancel every token for that user**, so
  both the thief and the real user are logged out. This is "reuse detection."

### d. Argon2 password hashing + constant-time login

- Passwords are hashed with **Argon2** (a modern, deliberately slow hashing
  method) so they can't be reversed if the database leaks. We never store the
  real password.
- On login, even if the **email doesn't exist**, we still run a fake password
  check so the response takes the **same amount of time**. This stops attackers
  from discovering which emails are registered by measuring response speed.
- The login error is always generic ("Incorrect email or password") so it never
  reveals whether the email or the password was the wrong part.

### e. UUID ids

User ids are random UUIDs (like `e5a5fcc8-...`) instead of `1, 2, 3...`. With
sequential numbers, anyone could guess `/users/2`, `/users/3` and enumerate the
whole table. Random ids make that impossible.

### f. Async database + migrations

We use **async SQLAlchemy** so the server can handle many requests at once
without blocking. **Alembic** manages the database schema as versioned
"migrations," so the schema can be recreated reliably anywhere.

---

## 3. What each file does

```
identity_service/app/
├── main.py                  # starts the app, wires routers, seeds the admin
├── core/
│   ├── config.py            # reads settings from environment variables
│   ├── logging.py           # JSON logging setup
│   ├── keys.py              # loads/generates the RSA key; builds the JWKS
│   ├── security.py          # password hashing + refresh-token generation
│   └── jwt.py               # creates and verifies access tokens (RS256)
├── db/
│   ├── base.py              # the base class all database models inherit
│   └── session.py           # the async database connection + session
├── models/
│   ├── user.py              # the "users" table (id, email, password hash, role)
│   └── refresh_token.py     # the "refresh_tokens" table (hashed, expiry, revoked)
├── schemas/
│   ├── user.py              # request/response shapes for users
│   └── token.py             # request/response shapes for tokens
├── services/
│   └── auth.py              # the actual logic: register, login, rotate, revoke
└── api/
    ├── deps.py              # shared helpers: "get current user", "require admin"
    ├── auth.py              # endpoints: /auth/register, /login, /refresh, /logout
    ├── users.py            # endpoints: /me, /users, /users/{id}
    ├── jwks.py              # endpoint: /.well-known/jwks.json
    └── health.py            # endpoint: /health
```

**A bit more detail on the important ones:**

- **`core/keys.py`** — On startup it loads the RSA private key from a file (or
  generates one). The public half is turned into the JWKS format (two numbers,
  `n` and `e`) that we publish. It also creates a `kid` (key id) so verifiers know
  which key signed a token.

- **`core/jwt.py`** — `create_access_token` packs your id, role, and an expiry
  time into a JWT and signs it. `decode_access_token` checks the signature, the
  issuer, the audience, and the expiry. If anything is wrong, it rejects the token.

- **`core/security.py`** — `hash_password` / `verify_password` use Argon2.
  `dummy_verify` is the fake check used for unknown emails (constant timing).
  `generate_refresh_token` makes a random secret; `hash_refresh_token` hashes it
  for storage.

- **`services/auth.py`** — the brain of the service. `register_user`,
  `authenticate` (login), `issue_token_pair`, `rotate_refresh_token` (with reuse
  detection), and `revoke_refresh_token` (logout) all live here, separate from the
  web layer so they can be tested on their own.

- **`api/deps.py`** — `get_current_user` reads the token from the request and
  loads the user; `require_role("admin")` blocks non-admins with a 403. Endpoints
  reuse these instead of repeating the checks.

- **`main.py`** — creates the FastAPI app, includes all the routers, and (if
  configured) seeds an admin user on startup so the admin endpoints can be tested.

---

## 4. The flow, end to end

1. **Register** → password is Argon2-hashed and the user is saved.
2. **Login** → password is checked; we return an access token (signed JWT) and a
   refresh token (random, stored hashed).
3. **Use the access token** → other services verify it with our public key.
4. **Access token expires** → the client calls **/refresh** with the refresh
   token; we rotate it and return a new pair.
5. **Logout** → the refresh token is revoked.

For a deeper, from-scratch explanation of JWTs and signing, see the README's
"How auth works" section.
