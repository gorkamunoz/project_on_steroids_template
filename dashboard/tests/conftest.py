import pytest

from dashboard import core


@pytest.fixture
def root(tmp_path, monkeypatch):
    """An empty project tree; core reads ROOT at call time."""
    for d in ("wiki", "labs", "discussion", "refs", "skills", "src"):
        (tmp_path / d).mkdir()
    monkeypatch.setattr(core, "ROOT", tmp_path)
    return tmp_path


@pytest.fixture
def seeded(root):
    (root / "refs" / "k2014").mkdir()
    (root / "refs" / "k2014" / "ref.yaml").write_text("title: VAE paper\nyear: 2014\n")
    core.create_wiki("elbo", "ELBO", "agent:t")
    a = core.create_lab("root lab", "agent:t")
    core.create_lab("child", "agent:t", parents="1")
    core.create_lab("merge", "agent:t", parents=[1, 2])
    core.create_thread("Pick a metric", "decision", "agent:t", "See [[lab:2]] and [[elbo]].", links=["lab:1"])
    core.create_thread("Do the thing", "task", core.HUMAN, "please")
    return root
