"""Task B — aggregation: concurrent fan-out and partial-success behaviour.

All three upstreams are mocked with respx, so these tests are deterministic and
offline (no real network).
"""

import re

import httpx

GREENHOUSE = "https://boards-api.greenhouse.io/v1/boards/acme/jobs"
GITHUB = "https://api.github.com/orgs/acme"
HN = re.compile(r"https://hn\.algolia\.com/api/v1/search.*")


def test_all_sources_ok(client, respx_mock):
    respx_mock.get(GREENHOUSE).respond(
        json={"jobs": [{"title": "Engineer", "location": {"name": "Remote"}}]}
    )
    respx_mock.get(GITHUB).respond(
        json={"name": "Acme", "public_repos": 12, "followers": 100, "html_url": "https://github.com/acme"}
    )
    respx_mock.get(HN).respond(
        json={"nbHits": 3, "hits": [{"title": "Acme raises", "points": 50, "num_comments": 10, "objectID": "1"}]}
    )

    r = client.get("/aggregate/company", params={"company": "ACME"})  # case-insensitive
    assert r.status_code == 200
    body = r.json()
    assert body["company"] == "acme"
    assert body["meta"]["fetched"] == 3
    assert body["meta"]["failed"] == 0
    assert body["sources"]["jobs"]["data"]["open_roles"] == 1
    assert body["sources"]["github"]["data"]["public_repos"] == 12
    assert body["sources"]["hacker_news"]["data"]["mentions"] == 3


def test_partial_failure_degrades_gracefully(client, respx_mock):
    respx_mock.get(GREENHOUSE).respond(404)  # company not on Greenhouse
    respx_mock.get(GITHUB).respond(json={"public_repos": 5, "followers": 9})
    respx_mock.get(HN).respond(json={"nbHits": 0, "hits": []})

    r = client.get("/aggregate/company", params={"company": "acme"})
    assert r.status_code == 200  # still 200 — failure is per-source, not fatal
    body = r.json()
    assert body["meta"]["fetched"] == 2
    assert body["meta"]["failed"] == 1
    assert body["sources"]["jobs"]["status"] == "error"
    assert body["sources"]["jobs"]["data"] is None
    assert "not found" in body["sources"]["jobs"]["error"]
    assert body["sources"]["github"]["status"] == "ok"
    assert body["sources"]["hacker_news"]["status"] == "ok"


def test_source_timeout_is_isolated(client, respx_mock):
    respx_mock.get(GREENHOUSE).mock(side_effect=httpx.TimeoutException("slow"))
    respx_mock.get(GITHUB).respond(json={"public_repos": 5})
    respx_mock.get(HN).respond(json={"nbHits": 1, "hits": []})

    r = client.get("/aggregate/company", params={"company": "acme"})
    body = r.json()
    assert body["sources"]["jobs"]["status"] == "error"
    assert "timeout" in body["sources"]["jobs"]["error"]
    assert body["meta"]["fetched"] == 2


def test_empty_company_is_rejected(client):
    assert client.get("/aggregate/company", params={"company": ""}).status_code == 422


import pytest


@pytest.mark.parametrize("bad", ["a/b", "../etc", "a.b", "user@host", "has space"])
def test_unsafe_company_slug_is_rejected(client, bad):
    # SSRF guard: only a safe slug charset is allowed (no slashes, dots, etc.).
    assert client.get("/aggregate/company", params={"company": bad}).status_code == 422
