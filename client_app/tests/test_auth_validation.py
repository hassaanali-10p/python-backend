"""Local RS256 token validation, RBAC, and the /profile service lookup."""

from tests.conftest import JWKS, auth_header, make_token


def test_whoami_requires_token(client):
    # No token -> 401 before any JWKS fetch is even needed.
    r = client.get("/whoami")
    assert r.status_code == 401
    assert r.headers.get("www-authenticate") == "Bearer"


def test_whoami_accepts_valid_token(client, jwks_route):
    token = make_token(sub="abc-123", role="user")
    r = client.get("/whoami", headers=auth_header(token))
    assert r.status_code == 200
    body = r.json()
    assert body["user_id"] == "abc-123"
    assert body["role"] == "user"
    assert body["issuer"] == "identity-service"


def test_whoami_rejects_garbage_token(client):
    r = client.get("/whoami", headers=auth_header("not.a.jwt"))
    assert r.status_code == 401


def test_whoami_rejects_tampered_token(client, jwks_route):
    token = make_token()
    head, payload, sig = token.split(".")
    tampered = f"{head}.{payload}X.{sig}"  # mutate payload -> signature no longer matches
    r = client.get("/whoami", headers=auth_header(tampered))
    assert r.status_code == 401


def test_whoami_rejects_expired_token(client, jwks_route):
    r = client.get("/whoami", headers=auth_header(make_token(expired=True)))
    assert r.status_code == 401


def test_whoami_rejects_wrong_audience(client, jwks_route):
    # Signed with the right key, but intended for a different service.
    r = client.get("/whoami", headers=auth_header(make_token(audience="other-app")))
    assert r.status_code == 401


def test_whoami_rejects_wrong_issuer(client, jwks_route):
    r = client.get("/whoami", headers=auth_header(make_token(issuer="evil-issuer")))
    assert r.status_code == 401


def test_whoami_rejects_unknown_kid(client, jwks_route):
    # Header references a key id that JWKS doesn't publish -> no key -> 401.
    r = client.get("/whoami", headers=auth_header(make_token(kid="unknown-kid")))
    assert r.status_code == 401


def test_admin_summary_forbidden_for_regular_user(client, jwks_route):
    r = client.get("/admin/summary", headers=auth_header(make_token(role="user")))
    assert r.status_code == 403  # valid token, insufficient role


def test_admin_summary_allowed_for_admin(client, jwks_route):
    r = client.get("/admin/summary", headers=auth_header(make_token(role="admin")))
    assert r.status_code == 200


def test_profile_fetches_user_from_identity(client, jwks_route):
    # /profile validates locally, then calls Identity's /me service-to-service.
    profile = {"id": "abc-123", "email": "alice@example.com", "role": "user"}
    jwks_route.get("http://localhost:8001/me").respond(json=profile)

    r = client.get("/profile", headers=auth_header(make_token(sub="abc-123")))
    assert r.status_code == 200
    assert r.json()["email"] == "alice@example.com"
