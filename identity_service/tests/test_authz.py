"""Token validation, the /me profile, and role-based access control."""

from tests.conftest import (
    ADMIN_EMAIL,
    ADMIN_PASSWORD,
    access_token,
    make_expired_token,
    register,
    unique_email,
)


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_me_requires_a_token(client):
    r = client.get("/me")
    assert r.status_code == 401
    assert r.headers.get("www-authenticate") == "Bearer"


def test_me_returns_current_user(client):
    email = unique_email()
    register(client, email)
    token = access_token(client, email)
    r = client.get("/me", headers=_auth(token))
    assert r.status_code == 200
    assert r.json()["email"] == email


def test_me_rejects_garbage_token(client):
    r = client.get("/me", headers=_auth("not.a.real.token"))
    assert r.status_code == 401


def test_me_rejects_expired_token(client):
    r = client.get("/me", headers=_auth(make_expired_token()))
    assert r.status_code == 401


def test_regular_user_cannot_list_users(client):
    email = unique_email()
    register(client, email)
    token = access_token(client, email)
    r = client.get("/users", headers=_auth(token))
    assert r.status_code == 403  # authenticated but not authorized


def test_admin_can_list_users(client):
    token = access_token(client, ADMIN_EMAIL, ADMIN_PASSWORD)
    r = client.get("/users", headers=_auth(token))
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_admin_endpoint_requires_authentication(client):
    # No token at all -> 401 (not 403): we don't know who you are yet.
    assert client.get("/users").status_code == 401
