import json
import sys
import pytest

from fastapi.testclient import TestClient

from dashboard import agents, core, watcher
from dashboard.server import app


def test_pending_rules(root):
    core.create_thread("task from gorka", "task", core.HUMAN, "do it")          # pending
    core.create_thread("agent question", "question", "agent:a", "?")            # waiting on gorka
    core.create_thread("idea", "idea", "agent:a")                               # waiting on none
    assert [t["id"] for t in core.pending_threads()] == [1]
    core.add_comment(1, "agent:a", "on it", status="in-progress")               # agent replied
    assert core.pending_threads() == []
    core.add_comment(2, core.HUMAN, "answer")                                   # gorka answered
    assert [t["id"] for t in core.pending_threads()] == [2]


def test_snooze_wakes_up(root):
    core.create_thread("train", "task", core.HUMAN)
    core.snooze(1, "agent:a", "2000-01-01 00:00", "training")
    t = core.get_thread(1)
    assert t["wake_at"] == "2000-01-01 00:00" and t["waiting_on"] == "agents"
    assert core.pending_threads()[0]["trigger"].startswith("snooze expired")
    core.set_meta(1, wake_at="2999-01-01 00:00")
    assert core.pending_threads() == []


def _fake_claude(tmp_path, reply: bool):
    """A stand-in for `claude -p` that writes stream-json and optionally replies on the thread."""
    script = tmp_path / "fake_claude.py"
    script.write_text(f"""
import json, sys
sys.path.insert(0, {str(core.Path(__file__).resolve().parents[2])!r})
from dashboard import core
core.ROOT = core.Path({str(tmp_path)!r})
if {reply}:
    core.add_comment(1, "agent:worker", "done", status="resolved")
print(json.dumps({{"type": "assistant", "message": {{"content": [{{"type": "text", "text": "working"}},
      {{"type": "tool_use", "name": "Bash", "input": {{"command": "./dash show 1"}}}}]}}}}))
print(json.dumps({{"type": "result", "subtype": "success", "result": "all good", "total_cost_usd": 0.12,
      "num_turns": 3, "duration_ms": 4000}}))
""")
    wrapper = tmp_path / "claude"
    wrapper.write_text(f"#!/bin/sh\nexec {sys.executable} {script}\n")
    wrapper.chmod(0o755)
    return str(wrapper)


def test_watcher_run_records_transcript(root, monkeypatch):
    monkeypatch.setenv("CLAUDE_BIN", _fake_claude(root, reply=True))
    core.create_thread("task", "task", core.HUMAN, "x")
    run = watcher.handle(core.pending_threads()[0])
    assert run["status"] == "done" and run["cost_usd"] == 0.12 and run["model"] == core.DEFAULT_MODEL
    kinds = [e["kind"] for e in agents.transcript(run["id"])]
    assert kinds == ["text", "tool", "result"]
    t = core.get_thread(1)
    assert t["status"] == "resolved" and core.last_author(t) == "agent:worker"  # no false hand-back
    assert core.pending_threads() == []
    c = TestClient(app)
    assert c.get("/agents").status_code == 200
    assert "./dash show 1" in c.get(f"/agents/{run['id']}").text


def test_watcher_hands_back_silent_runs(root, monkeypatch):
    monkeypatch.setenv("CLAUDE_BIN", _fake_claude(root, reply=False))
    core.create_thread("task", "task", core.HUMAN, "x")
    watcher.handle(core.pending_threads()[0])
    t = core.get_thread(1)
    assert t["waiting_on"] == core.HUMAN and core.last_author(t) == "agent:watcher"
    assert core.pending_threads() == []  # no relaunch loop


def test_pause_toggle(root):
    c = TestClient(app)
    c.post("/agents/pause", data={"paused": "1"})
    assert agents.is_paused()
    assert json.loads(c.get("/api/agents").text)["paused"] is True
    c.post("/agents/pause", data={"paused": "0"})
    assert not agents.is_paused()


def test_watcher_liveness(root):
    assert not agents.watcher_alive()
    c = TestClient(app)
    assert "watcher not running" in c.get("/agents").text
    agents.heartbeat()  # this (alive) process acts as the watcher
    assert agents.watcher_alive()
    assert "watcher running" in c.get("/agents").text


def test_model_per_thread(root):
    t = core.create_thread("default model", "task", core.HUMAN)
    assert t["model"] == "" and core.thread_model(t) == core.DEFAULT_MODEL
    other = next(m for m in core.AGENT_MODELS if m != core.DEFAULT_MODEL) if len(core.AGENT_MODELS) > 1 else None
    t = core.create_thread("chosen model", "task", core.HUMAN, model=core.DEFAULT_MODEL)
    assert t["model"] == core.DEFAULT_MODEL
    with pytest.raises(ValueError):
        core.create_thread("bad", "task", core.HUMAN, model="not-a-model")
    # unchanged model on a reply: no note; changed: logged and sticky
    t = core.add_comment(1, core.HUMAN, "go", model=core.DEFAULT_MODEL)
    assert "model:" not in t["comments"][-1]["body"]
    if other:
        t = core.add_comment(1, core.HUMAN, "harder now", model=other)
        assert t["model"] == other and f"model: {core.DEFAULT_MODEL} → {other}" in t["comments"][-1]["body"]
        t = core.add_comment(1, "agent:a", "ok")
        assert core.thread_model(t) == other
    assert "--model" in (cmd := watcher.build_cmd("p", "sid", 1, "sonnet")) and cmd[cmd.index("--model") + 1] == "sonnet"


def test_model_dropdowns(root):
    c = TestClient(app)
    r = c.post("/discussion/new", data={"title": "x", "type": "task", "model": core.AGENT_MODELS[-1]},
               follow_redirects=False)
    assert r.status_code == 303 and core.get_thread(1)["model"] == core.AGENT_MODELS[-1]
    page = c.get("/discussion/1").text
    assert 'name="model"' in page and f"<option selected>{core.AGENT_MODELS[-1]}</option>" in page
    c.post("/discussion/1/comment", data={"body": "switch", "model": core.AGENT_MODELS[0]})
    assert core.get_thread(1)["model"] == core.AGENT_MODELS[0]
    assert 'name="model"' in c.get("/discussion/new").text
