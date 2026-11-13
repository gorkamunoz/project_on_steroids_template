"""Two people, one shared repo: a local bare repo plays GitHub, two clones play alice's and bob's machines."""
import subprocess

import pytest

from dashboard import core, merge_thread, sync, watcher


def _git(cwd, *args):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return r.stdout


@pytest.fixture
def team(tmp_path, monkeypatch):
    """Returns use(name): point core at that person's clone (ROOT and ME)."""
    origin = tmp_path / "origin.git"
    _git(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    seed = tmp_path / "seed"
    _git(tmp_path, "clone", "-q", str(origin), str(seed))
    for d in ("wiki", "labs", "discussion", "refs", "skills", "src"):
        (seed / d).mkdir()
        (seed / d / ".gitkeep").write_text("")
    (seed / ".gitignore").write_text(".dash/\n.agents/\n.dash.lock\nlabs/*/outputs/\n")
    (seed / ".gitattributes").write_text("discussion/*.md merge=dash-thread\n")
    clones = {}
    monkeypatch.setattr(core, "ROOT", seed)
    monkeypatch.setattr(core, "ME", "alice")
    monkeypatch.delenv("DASH_REQUESTER", raising=False)
    core.create_thread("Shared question", "question", "agent:worker", "Which seed?", waiting_on="none")
    _git(seed, "add", "-A")
    _git(seed, "-c", "user.name=seed", "-c", "user.email=s@x", "commit", "-q", "-m", "seed")
    _git(seed, "push", "-q", "origin", "main")
    for who in ("alice", "bob"):
        c = tmp_path / who
        _git(tmp_path, "clone", "-q", str(origin), str(c))
        _git(c, "config", "user.name", who)
        _git(c, "config", "user.email", f"{who}@example.org")
        clones[who] = c

    def use(who):
        monkeypatch.setattr(core, "ROOT", clones[who])
        monkeypatch.setattr(core, "ME", who)
        return clones[who]
    return use


def _titles():
    return {t["id"]: t["title"] for t in core.list_threads()}


def test_merge_driver_keeps_both_comments():
    base = core.join_fm({"id": 1, "title": "t", "status": "open", "waiting_on": "none", "updated": "2026-01-01 10:00"},
                        "Body")
    ours = base.rstrip() + '\n\n<!-- comment author="alice" date="2026-01-01 10:05" -->\nA\n'
    ours = ours.replace("updated: 2026-01-01 10:00", "updated: 2026-01-01 10:05")
    theirs = base.rstrip() + '\n\n<!-- comment author="bob" date="2026-01-01 10:03" -->\nB\n'
    theirs = theirs.replace("waiting_on: none", "waiting_on: alice").replace("updated: 2026-01-01 10:00",
                                                                           "updated: 2026-01-01 10:03")
    out = merge_thread.merge(base, ours, theirs)
    meta, body = core.split_fm(out)
    assert body.index("\nB\n") < body.index("\nA\n")  # date order
    assert meta["waiting_on"] == "alice" and meta["updated"] == "2026-01-01 10:05"
    assert "<<<<" not in out


def test_number_collision_renumbers_the_later_push(team):
    team("alice")
    core.create_thread("Alice's question", "question", "alice", "for bob", waiting_on="bob")
    sync.commit(["discussion"], "alice: new thread")
    team("bob")
    t = core.create_thread("Bob's question", "question", "bob", "Context in [[thread:2]] and [[thread:1]].",
                           waiting_on="alice", links=["thread:2"])
    sync.commit([t["path"]], "bob: new thread")
    team("alice")
    sync.sync()
    team("bob")
    res = sync.sync()
    assert res["mapping"] == {("thread", 2): 3}
    assert _titles() == {1: "Shared question", 2: "Alice's question", 3: "Bob's question"}
    mine = core.get_thread(3)
    assert "[[thread:3]]" in mine["body"] and "[[thread:1]]" in mine["body"] and mine["links"] == ["thread:3"]
    assert any("#2 is now #3" in n for n in sync.status()["notes"])
    team("alice")
    sync.sync()
    assert _titles() == {1: "Shared question", 2: "Alice's question", 3: "Bob's question"}
    assert core.check() == []


def test_both_comment_on_the_same_thread(team):
    team("alice")
    core.add_comment(1, "alice", "Five seeds.", waiting_on="none")
    sync.commit(["discussion"], "alice comments")
    team("bob")
    core.add_comment(1, "bob", "Three seeds for long runs.", waiting_on="alice")
    sync.commit(["discussion"], "bob comments")
    team("alice")
    sync.sync()
    team("bob")
    sync.sync()
    team("alice")
    sync.sync()
    for who in ("alice", "bob"):
        team(who)
        t = core.get_thread(1)
        assert sorted(c["author"] for c in t["comments"]) == ["alice", "bob"]
        assert "<<<<" not in (core.ROOT / t["path"]).read_text()


def test_request_is_held_until_my_agent_starts(team, monkeypatch):
    team("alice")
    t = core.create_thread("Run the sweep", "task", "alice", "please")  # waiting on agents -> held
    sync.after_change([t["path"]], "alice: new task")
    sync.sync()
    assert sync.status()["held"] == 1
    team("bob")
    sync.sync()
    assert 2 not in _titles()                       # nobody else sees an unclaimed request
    assert core.pending_threads() == []             # and bob's agent would never take it
    team("alice")
    monkeypatch.setenv("CLAUDE_BIN", "true")        # an "agent" that does nothing: watcher hands it back
    watcher.handle(core.pending_threads()[0])
    assert sync.status()["held"] == 0
    team("bob")
    sync.sync()
    t = core.get_thread(2)
    assert t["run_by"] == "alice" and t["waiting_on"] == "alice"


def test_held_comment_survives_others_changes(team):
    team("alice")
    core.add_comment(1, "alice", "Agent: try 7 seeds.")       # for alice's agent -> held, uncommitted
    team("bob")
    core.add_comment(1, "bob", "FYI I prefer 5.", waiting_on="alice")
    sync.commit(["discussion"], "bob comments")
    sync.sync()
    team("alice")
    sync.sync()                                                 # rebase with alice's held change stashed
    text = (core.ROOT / core.get_thread(1)["path"]).read_text()
    assert "try 7 seeds" in text and "I prefer 5" in text and "<<<<" not in text
    assert sync.status()["held"] == 0 or core.get_thread(1)["waiting_on"] == "alice"
    assert _git(core.ROOT, "status", "--porcelain").strip()    # alice's message is still not committed


def test_lab_collision_moves_folder_and_parents(team):
    team("alice")
    core.create_lab("alice lab", "agent:worker")
    sync.commit(["labs"], "alice lab")
    team("bob")
    a = core.create_lab("bob lab", "agent:worker")
    (a / "outputs").mkdir()
    (a / "outputs" / "ckpt.bin").write_text("weights")         # git-ignored, must move along
    core.create_lab("bob child", "agent:worker", parents=[1])
    sync.commit(["labs"], "bob labs")
    team("alice")
    sync.sync()
    team("bob")
    res = sync.sync()
    assert res["mapping"] == {("lab", 1): 3, ("lab", 2): 4}  # both of bob's labs move, order kept
    labs = {l["id"]: l for l in core.list_labs()}
    assert labs[1]["title"] == "alice lab"
    bob = next(l for l in labs.values() if l["title"] == "bob lab")
    child = next(l for l in labs.values() if l["title"] == "bob child")
    assert child["parents"] == [bob["id"]] and bob["id"] != 1
    assert (core.ROOT / bob["dir"] / "outputs" / "ckpt.bin").exists()
    assert bob["outputs_on"] == "bob"
    assert core.check() == []


def test_commit_all_lists_a_few_and_blocks_large_files(team):
    c = team("alice")
    many = c / "src" / "generated"
    many.mkdir()
    for i in range(1500):
        (many / f"f{i:04d}.py").write_text(f"x = {i}\n")
    core.create_thread("Agent please", "task", "alice", "go")        # held: not part of "your changes"
    u = sync.uncommitted(limit=5)
    assert u["count"] == 1500 and len(u["files"]) == 5 and u["held"] == 1
    assert u["files"][0][0] == "new"
    (c / "big.bin").write_bytes(b"0" * (6 * 1024 * 1024))
    with pytest.raises(sync.SyncError, match="over 5 MB"):
        sync.commit_all("add generated code")
    (c / "big.bin").unlink()
    with pytest.raises(sync.SyncError, match="message"):
        sync.commit_all("  ")
    assert sync.commit_all("add generated code") == 1500
    assert sync.uncommitted()["count"] == 0 and sync.status()["held"] == 1  # the held message stays held
    sync.sync()
    team("bob")
    sync.sync()
    assert (core.ROOT / "src" / "generated" / "f1499.py").exists()
    assert 2 not in _titles()
