import shutil
import subprocess

import pytest
from fastapi.testclient import TestClient

from dashboard import core, notes
from dashboard.server import app

pytestmark = pytest.mark.skipif(not shutil.which("latexmk"), reason="LaTeX not installed")


@pytest.fixture
def git_root(root, monkeypatch):
    for k, v in {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
                 "GIT_COMMITTER_EMAIL": "t@t"}.items():
        monkeypatch.setenv(k, v)
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    (root / ".gitignore").write_text("notes/build/\nnotes/version.tex\n*.aux\n*.log\n*.fls\n*.fdb_latexmk\n.dash.lock\n")
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=root, check=True)
    return root


def test_notes_build_release_and_pages(git_root):
    c = TestClient(app)
    assert "No notes yet" in c.get("/notes").text
    notes.init()
    with pytest.raises(ValueError):
        notes.init()
    r = notes.build()
    assert r["ok"] and r["pages"] and not [p for p in r["problems"] if p.startswith("ERROR")]
    assert c.get("/notes/draft").status_code == 200

    v1 = notes.release("first", "agent:t", ["a"], thread="3")
    assert v1["version"] == "v001" and v1["git"] == "committed + tagged"
    sec = git_root / "notes" / "sections" / "00-reading-guide.tex"
    sec.write_text(sec.read_text() + "\nA new sentence.\n")
    v2 = notes.release("second", "agent:t")
    assert v2["diff"] == "diff PDF created"

    vs = notes.list_versions()
    assert [v["version"] for v in vs] == ["v002", "v001"] and vs[1]["thread"] == "3"
    flat = (git_root / vs[0]["tex"]).read_text()
    assert flat.startswith("\\def\\NotesVersion{v002}") and "\\input{sections/00" not in flat
    tags = subprocess.run(["git", "tag"], cwd=git_root, capture_output=True, text=True).stdout.split()
    assert tags == ["notes-v001", "notes-v002"]
    assert subprocess.run(["git", "status", "--porcelain"], cwd=git_root, capture_output=True,
                          text=True).stdout.strip() == ""

    page = c.get("/notes").text
    assert "Latest: v002" in page and "notes-v002-diff.pdf" in page
    assert c.get("/notes/v001").status_code == 200 and c.get("/notes/v009").status_code == 404
    assert c.get("/raw/notes/versions/v002/notes-v002.pdf").headers["content-type"] == "application/pdf"


def test_failed_build_releases_nothing(git_root):
    notes.init()
    sec = git_root / "notes" / "sections" / "00-reading-guide.tex"
    sec.write_text(sec.read_text() + "\n\\undefinedmacro\n")
    with pytest.raises(ValueError, match="build failed"):
        notes.release("broken", "agent:t", use_git=False)
    assert notes.list_versions() == []
