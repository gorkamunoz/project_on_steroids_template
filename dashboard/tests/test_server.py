import pytest
from fastapi.testclient import TestClient

from dashboard import core
from dashboard.server import app


@pytest.fixture
def client(seeded):
    return TestClient(app)


@pytest.mark.parametrize("url", [
    "/", "/discussion", "/discussion?view=mine", "/discussion?view=all&type=task", "/discussion/new",
    "/discussion/1", "/labs", "/labs?focus=2", "/labs/1", "/labs/3", "/wiki", "/wiki/elbo", "/wiki/missing",
    "/refs", "/refs/k2014", "/skills", "/browse", "/browse/labs", "/search?q=lab",
])
def test_pages_render(client, url):
    r = client.get(url)
    assert r.status_code == 200, r.text[:500]


def test_404s_and_path_safety(client):
    assert client.get("/discussion/99").status_code == 404
    assert client.get("/labs/99").status_code == 404
    assert client.get("/raw/..%2f..%2fetc%2fpasswd").status_code in (403, 404)
    assert client.get("/raw/.dash.lock").status_code == 403


def test_waiting_badge_on_home(client):
    r = client.get("/")
    assert "Pick a metric" in r.text and "Waiting on you (1)" in r.text


def test_forms_create_and_comment(client):
    r = client.post("/discussion/new", data={"title": "From UI", "type": "idea", "body": "hi",
                                             "links": "lab:1, wiki:elbo", "waiting_on": "none"},
                    follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/discussion/3"
    t = core.get_thread(3)
    assert t["author"] == core.ME and t["links"] == ["lab:1", "wiki:elbo"]
    client.post("/discussion/1/comment", data={"body": "Go with MIG", "status": "open", "waiting_on": ""})
    t = core.get_thread(1)
    assert t["comments"][-1]["body"].startswith("Go with MIG") and t["waiting_on"] == "agents"


def test_json_api(client):
    r = client.post("/api/threads", json={"title": "API", "type": "question", "author": "agent:x"})
    assert r.status_code == 201 and r.json()["waiting_on"] == core.ME
    tid = r.json()["id"]
    r = client.post(f"/api/threads/{tid}/comments", json={"author": "agent:x", "status": "closed"})
    assert r.json()["status"] == "closed"
    assert client.post("/api/threads", json={"title": "x", "type": "bad", "author": "a"}).status_code == 422
    assert len(client.get("/api/threads?waiting_on=agents").json()) == 1
    g = client.get("/api/labs/graph").json()
    assert len(g["nodes"]) == 3 and len(g["edges"]) == 3
    assert client.get("/api/check").json() == {"problems": []}
