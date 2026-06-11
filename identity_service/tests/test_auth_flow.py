"""Registration, login, and refresh-token lifecycle."""

from tests.conftest import access_token, login, register, unique_email


def test_register_creates_user_with_user_role(client):
    email = unique_email()
    r = register(client, email)
    assert r.status_code == 201
    body = r.json()
    assert body["email"] == email
    assert body["role"] == "user"  # cannot self-assign admin
    assert "password" not in body and "hashed_password" not in body


def test_register_duplicate_email_conflicts(client):
    email = unique_email()
    assert register(client, email).status_code == 201
    assert register(client, email).status_code == 409


def test_register_rejects_weak_password(client):
    r = register(client, unique_email(), "short")  # < 8 chars
    assert r.status_code == 422


def test_login_returns_token_pair(client):
    email = unique_email()
    register(client, email)
    r = login(client, email)
    assert r.status_code == 200
    body = r.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] > 0
    assert body["access_token"] and body["refresh_token"]


def test_login_wrong_password_is_unauthorized(client):
    email = unique_email()
    register(client, email)
    r = login(client, email, "wrong-password")
    assert r.status_code == 401
    # Generic message — must not reveal which field was wrong.
    assert "email or password" in r.json()["detail"].lower()


def test_login_unknown_user_is_unauthorized(client):
    r = login(client, unique_email(), "whatever123")
    assert r.status_code == 401


def test_refresh_rotates_tokens(client):
    email = unique_email()
    register(client, email)
    rt1 = login(client, email).json()["refresh_token"]

    r = client.post("/auth/refresh", json={"refresh_token": rt1})
    assert r.status_code == 200
    rt2 = r.json()["refresh_token"]
    assert rt2 != rt1  # rotation: a new refresh token each time

    # The newly issued token still works...
    assert client.post("/auth/refresh", json={"refresh_token": rt2}).status_code == 200
    # ...but the rotated-away token does not.
    assert client.post("/auth/refresh", json={"refresh_token": rt1}).status_code == 401


def test_refresh_reuse_detection_revokes_family(client):
    email = unique_email()
    register(client, email)
    rt1 = login(client, email).json()["refresh_token"]

    rt2 = client.post("/auth/refresh", json={"refresh_token": rt1}).json()["refresh_token"]

    # Replaying the already-rotated rt1 is treated as theft -> 401...
    assert client.post("/auth/refresh", json={"refresh_token": rt1}).status_code == 401
    # ...and it revokes the whole family, so the live rt2 is now dead too.
    assert client.post("/auth/refresh", json={"refresh_token": rt2}).status_code == 401


def test_logout_revokes_refresh_token(client):
    email = unique_email()
    register(client, email)
    rt = login(client, email).json()["refresh_token"]

    assert client.post("/auth/logout", json={"refresh_token": rt}).status_code == 204
    assert client.post("/auth/refresh", json={"refresh_token": rt}).status_code == 401
