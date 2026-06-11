# Authentication Concepts — Deep Explanation & Dry Runs

A from-scratch reference for the auth design in this project: JWTs, RS256,
public/private keys, JWKS, and the full request flows. Written to be re-read
later. Uses real values from this project plus tiny toy numbers where the math
matters.

---

## 0. The big picture in three sentences

1. The **Identity Service** signs login tokens with a **private key** that never
   leaves it.
2. Anyone can verify those tokens using the matching **public key**, which is
   published openly at a **JWKS** endpoint.
3. The public key can only *check* signatures, never *create* them — so sharing
   it is safe, and verifiers never need to call the Identity Service per request.

---

## 1. What a JWT actually is

A JWT (JSON Web Token) is a string with **three parts joined by dots**:

```
header . payload . signature
```

- The 3rd part is a **signature**, NOT a key. **The key is never inside the token.**
- Parts 1 and 2 are **Base64url-encoded JSON** — i.e. *readable by anyone*
  (Base64 is reversible encoding, not encryption). They are **not secret**.
- Security does **not** come from hiding the data. It comes entirely from the
  **signature**, which makes the token tamper-evident.

### Real example (an access token issued by this project)

```
eyJhbGciOiJSUzI1NiIsImtpZCI6IjBqM2ZicVVBNlRjRDlJOTNoeU9lQmxGWHBvbFRfRXVZWlNiR3lLekVqS2siLCJ0eXAiOiJKV1QifQ
.
eyJpc3MiOiJpZGVudGl0eS1zZXJ2aWNlIiwiYXVkIjoiY2xpZW50LWFwcCIsInN1YiI6ImU1YTVmY2M4LTI2YWMtNDVkOS1iZDRlLWMzMjEwZmZiYWU0MCIsInJvbGUiOiJ1c2VyIiwiaWF0IjoxNzgxMTI2OTcyLCJuYmYiOjE3ODExMjY5NzIsImV4cCI6MTc4MTEyNzg3MiwianRpIjoiZDBkMzU3ZGItYWYyMC00NTU2LTlkNzQtYjkyY2JjOTYwMTE1IiwidG9rZW5fdHlwZSI6ImFjY2VzcyJ9
.
PiNZ8o9tGmzU...(signature bytes)...
```

---

## 2. The HEADER — "how is this token signed?"

Decoding part 1 gives:

```json
{
  "alg": "RS256",
  "kid": "0j3fbqUA6TcD9I93hyOeBlFXpolT_EuYZSbGyKzEjKk",
  "typ": "JWT"
}
```

| Field | Meaning |
|---|---|
| `alg` | **Algorithm** used to sign. `RS256` = RSA signature over a SHA-256 hash. Tells the verifier *how* to check the signature. |
| `kid` | **Key ID** — *which* key signed this (see §4). Lets the verifier pick the right public key from JWKS. |
| `typ` | **Type** — just says "this is a JWT". |

---

## 3. The PAYLOAD — "who is this, and what are the rules?"

Decoding part 2 gives (these facts are called **claims**):

```json
{
  "iss": "identity-service",
  "aud": "client-app",
  "sub": "e5a5fcc8-26ac-45d9-bd4e-c3210ffbae40",
  "role": "user",
  "iat": 1781126972,
  "nbf": 1781126972,
  "exp": 1781127872,
  "jti": "d0d357db-af20-4556-9d74-b92cbc960115",
  "token_type": "access"
}
```

| Claim | Standard? | Meaning |
|---|---|---|
| `iss` | ✅ | **Issuer** — who created the token. Verifier trusts only `identity-service`. |
| `aud` | ✅ | **Audience** — who the token is *for* (`client-app`). Stops a token meant for one service being replayed at another. |
| `sub` | ✅ | **Subject** — *who the token is about*: the **user's UUID**. This is the identity. `/me` reads this to know who you are. |
| `role` | ✗ (custom) | Used for RBAC. Because it's *inside* the signed token, authorization needs no DB lookup, and it can't be changed to `admin` without breaking the signature. |
| `iat` | ✅ | **Issued At** — Unix timestamp (seconds since 1970) when created. |
| `nbf` | ✅ | **Not Before** — token invalid before this time. |
| `exp` | ✅ | **Expiration** — token dead after this time. Here `exp − iat = 900s = 15 min`. |
| `jti` | ✅ | **JWT ID** — unique id for this specific token (useful for tracking/blacklisting). |
| `token_type` | ✗ (custom) | Marks this as an `access` token (vs a refresh token), so a token is only usable for its intended purpose. |

### The SIGNATURE (part 3)
`PiNZ8o9t...` — the output of `sign(header + payload, PRIVATE key)`. Not readable,
not a key. The tamper-proof seal over parts 1 and 2.

---

## 4. What is `kid` (Key ID)?

`kid` is a **name/label for a specific key**.

**Why it exists:** a service can have **more than one signing key at the same
time** — most commonly during **key rotation** (a new key is introduced while
tokens signed by the old key are still valid). When a token arrives, the verifier
must know *which* key to check it against. The token's header says
`kid: 0j3fbq...`, so the verifier looks up that exact key in JWKS.

**Analogy:** a hotel key card printed with "Room 412" — the lock system knows
which room's settings to check.

**In this project:** the `kid` is a **fingerprint computed from the public key
itself** (RFC 7638 JWK thumbprint), so it's a stable, unique name. The token
header's `kid` and the JWKS entry's `kid` always match.

---

## 5. The security paradox: "if the public key is shared, what stops forgery?"

This is the most important concept. The answer is why RS256 exists.

### Password thinking (WRONG model here)
With a shared **password/secret**, anyone who knows it can both create and check —
so sharing it means anyone can forge. This is **symmetric** (same key both ways).

### RS256 uses TWO different, linked keys (asymmetric)

| Key | Can do | CANNOT do | Who has it |
|---|---|---|---|
| 🔒 **Private key** | **Create** signatures | — | Only the Identity Service |
| 🔓 **Public key** | **Check** signatures | ❌ Create signatures | Everyone (published) |

**The public key can only verify. It physically cannot create a valid
signature.** So publishing and caching it gives away **zero** forging power.

**Why can't you forge with the public key?** A signature is produced by a math
operation that requires the private key. The public key only *reverse-checks*.
Mathematically: the private key is two secret primes; the public key is their
product. Multiplying is easy (public derived from private); factoring the product
back into the primes is effectively impossible for large numbers, so you cannot
derive the private key or sign without it.

### Wax-seal analogy (precise)
- 🔒 Private key = the **signet ring**. Only the king has it. Makes a unique seal.
- 🔓 Public key = a **high-res photo of the genuine seal**. Everyone gets a copy.
- With the photo you can **inspect any seal and say genuine/fake**. ✅
- With the photo you **cannot carve the ring** to make new seals. ❌

**Bottom line:** the only secret is the **private key**. The public key is *meant*
to be shared and cached — that's the design, not a leak.

---

## 6. How the keypair is generated (with real tiny numbers)

RSA key generation:

1. Pick two **secret** primes: `p = 5`, `q = 11`. *(secret)*
2. Multiply: `n = p × q = 55`. *(PUBLIC)*
3. Pick public exponent: `e = 3`. *(PUBLIC; real systems use 65537 → `"e":"AQAB"` in JWKS)*
4. Compute private exponent from the secret primes: `d = 27`. *(secret)*

Result:
- 🔓 **Public key = (n=55, e=3)** → published in JWKS as `n` and `e`
- 🔒 **Private key = (n=55, d=27)** → stored in `.devkeys/jwt_private.pem`

In code (`identity_service/app/core/keys.py`):
```python
private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
public_key  = private_key.public_key()          # public key extracted from private
public_numbers = public_key.public_numbers()    # → n and e
```
**The public key is a byproduct of generating the private key** — we never
generate it separately. It is just the two numbers `n` and `e`.

**Why sharing (n, e) is safe:** finding `d` requires factoring `n` back into its
primes. For `n=55` that's trivial, but a real `n` is ~617 digits and factoring it
would take longer than the age of the universe.

---

## 7. Signing & verifying, mechanically (same toy numbers)

First the message (`header.payload`) is **hashed** to a number. Say `m = 8`.
(Hashing = turn any text into a fixed number; change the text → different number.)

### Identity SIGNS (needs private key d=27)
```
signature = m^d mod n = 8^27 mod 55 = 2
```
Sends: **message + signature(2)**. Only someone with `d` could compute this.

### Anyone VERIFIES (needs only public key e=3)
```
step 1:  undo signature with public key:  signature^e mod n = 2^3 mod 55 = 8
step 2:  independently hash the message:  hash(message) = 8
step 3:  compare:  8 == 8  →  ✅ VALID  (genuine sender + unchanged content)
```

### Forgery attempt FAILS
Attacker changes `role:user` → `role:admin`; new content hashes to `m' = 9`,
keeps old `signature = 2`:
```
step 1:  2^3 mod 55 = 8
step 2:  hash(tampered message) = 9
step 3:  8 ≠ 9  →  ❌ INVALID
```
To pass, they'd need a signature for `m'=9` = `9^27 mod 55`, which **requires
`d`** (the secret). With only `e` they can check, never create. Forgery blocked.

### What "verify" proves (verify *what*, exactly)
> "Was this exact header+payload signed by the holder of the private key, AND
> unchanged since?"

- **Authenticity** — only Identity's private key produces signatures that pass
  with Identity's public key.
- **Integrity** — the signature is tied to the exact bytes; one changed character
  → hash mismatch → rejected.

---

## 8. JWKS — publisher vs consumer

JWKS (JSON Web Key Set) has **two sides in two different apps**:

| Side | Role | App | Phase |
|---|---|---|---|
| **Publisher** (the endpoint) | "Here is my public key, world." | Identity Service (App 1) | Phase 1 ✅ |
| **Consumer** (the client) | Fetch + cache the key, verify tokens. | Client App (App 2) | Phase 2 ⏳ |

### Live JWKS from this project (`GET http://localhost:8001/.well-known/jwks.json`)
```json
{
  "keys": [
    {
      "kty": "RSA",
      "use": "sig",
      "alg": "RS256",
      "kid": "0j3fbqUA6TcD9I93hyOeBlFXpolT_EuYZSbGyKzEjKk",
      "n": "soWf6-QO4D3NvjSsPkZDT78Le...(big modulus)...zvRTw",
      "e": "AQAB"
    }
  ]
}
```
- `kty` = key type (RSA). `use:sig` = used for signatures. `alg` = RS256.
- `n` + `e` together **are** the public key. `"e":"AQAB"` is the number **65537**.
- The `kid` here matches the `kid` in the token header — that's the link.

**Why the endpoint exists before Phase 2:** publishing the public key is the
Identity Service's job (Phase 1). A signer must share its public key so others can
verify. Phase 2 builds the *consumer* — the Client App code that reads, caches,
and uses this key.

**Analogy:** Phase 1 posts the seal's reference photo on the palace gate;
Phase 2 = shopkeepers copy the photo and start checking letters with it.

---

## 9. Full dry run — logging in

User logs in as `hassaanali723@gmail.com` / `ham12345`
(note: password must be 8+ chars, so `ham123` would return **422**).

1. **Request:** `POST /auth/login`, form body
   `username=hassaanali723@gmail.com&password=ham12345`.
2. **Parse:** `OAuth2PasswordRequestForm` → `form_data.username`, `form_data.password`.
   Endpoint calls `authenticate(email, password)`.
3. **Look up user:** `SELECT * FROM users WHERE email='hassaanali723@gmail.com'`
   → finds row (id `e5a5fcc8-...`, role `user`, Argon2 hash).
4. **Check password (Argon2):** `verify_password("ham12345", stored_hash)` —
   Argon2 re-hashes the input with the salt baked into `stored_hash` and compares.
   - If the email did **not** exist, a fake hash check (`dummy_verify`) runs anyway
     so timing is identical → no account enumeration.
   - Failure → **401 "Incorrect email or password"** (generic; doesn't say which field).
5. **Mint access token (JWT):** build claims (§3) + header (§2), then
   `sign(header+payload, PRIVATE key)` → `eyJ...` string. Header carries `kid`.
6. **Mint refresh token (NOT a JWT):** random string; store **SHA-256 hash** in
   `refresh_tokens` (`user_id`, `token_hash`, `expires_at = now + 7 days`); return
   the raw string once.
7. **Response:**
   ```json
   {
     "access_token": "eyJ...",          // short-lived (15 min), signed JWT
     "refresh_token": "WqXJpX06...",     // long-lived (7 days), opaque, hashed in DB
     "token_type": "bearer",
     "expires_in": 900
   }
   ```
   Identity used its **private** key here (signing). No public key involved yet.

---

## 10. Full dry run — calling `/me` with the token (verification)

This is exactly what Phase 2's Client App will do on its own.

1. **Request:** `GET /me`, header `Authorization: Bearer eyJ...`.
2. **Read header** → `kid: 0j3fbq...` → "need public key `0j3fbq...`".
3. **Verify with the PUBLIC key:** check signature (undo with `e`, compare to hash
   of header+payload) **and** `iss==identity-service`, `aud==client-app`,
   now within `nbf`..`exp`, `token_type==access`. All pass → genuine, untampered,
   unexpired.
   - Tampered payload (e.g. `role:admin`) → signature mismatch → **401**.
4. **Load user:** `SELECT * FROM users WHERE id='e5a5fcc8-...'` (the `sub`) →
   active → return profile.

---

## 11. Access token vs refresh token

| | Access token | Refresh token |
|---|---|---|
| Format | JWT (self-contained) | Opaque random string |
| Lifetime | Short (15 min) | Long (7 days) |
| Checked against DB? | No (verified by signature) | Yes (looked up by hash) |
| Revocable before expiry? | No (just expires) | Yes (revoke the DB row) |
| Sent on every request? | Yes (`Authorization: Bearer`) | No (only to `/auth/refresh`) |
| Stored where? | Nowhere server-side | DB, as a **SHA-256 hash** |

**Why two?** A JWT can't be revoked before `exp` (that's the price of not hitting
the DB on each request). So we keep it **short-lived** to limit damage if leaked,
and pair it with a **long-lived, revocable** refresh token to get new ones without
re-login. Refresh tokens are **rotated** on every use; replaying a rotated token
triggers **reuse detection** → the whole family is revoked (theft defense).

**Logout** revokes the refresh token immediately, but the access token keeps
working until `exp` (≤15 min). Instant access-token revocation would require
server-side state on every request (e.g. a Redis denylist), which sacrifices the
statelessness that makes JWTs scale.

---

## 12. Where everything lives in this codebase

| Concept | File |
|---|---|
| RSA key load/generate, JWKS builder, `kid` thumbprint | `identity_service/app/core/keys.py` |
| Access-token sign/verify (RS256) | `identity_service/app/core/jwt.py` |
| Password hashing (Argon2), dummy-verify, refresh token gen/hash | `identity_service/app/core/security.py` |
| Login/register/refresh/logout logic, rotation, reuse detection | `identity_service/app/services/auth.py` |
| `get_current_user`, `require_role` | `identity_service/app/api/deps.py` |
| JWKS endpoint (`/.well-known/jwks.json`) | `identity_service/app/api/jwks.py` |

---

## 13. Phase 2 preview (the consumer side)

Phase 2 teaches the **Client App** to do §10 steps 2–3 by itself:
1. **Fetch** the public key from `/.well-known/jwks.json`.
2. **Cache** it in memory (refetch only on an unknown `kid`, e.g. after rotation).
3. **Verify** every incoming token locally with the cached public key — no call to
   Identity on the hot path.
4. **Protected endpoints** require a valid token; **user lookup** calls Identity's
   `/me` only when full profile data is needed.
5. **401** = bad/missing/expired token; **403** = valid token, wrong role.
```
