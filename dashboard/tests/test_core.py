import pytest

from dashboard import core


def test_thread_roundtrip_and_waiting_rules(root):
    t = core.create_thread("Which prior?", "decision", "agent:a", "Body with $x$.", links=["lab:1"])
    assert (t["id"], t["status"], t["waiting_on"]) == (1, "open", core.HUMAN)
    assert t["links"] == ["lab:1"] and t["body"] == "Body with $x$."

    t = core.add_comment(1, core.HUMAN, "Use the categorical one.")
    assert t["waiting_on"] == "agents"  # human reply hands it back
    t = core.add_comment(1, "agent:a", "Done.", status="resolved")
    assert t["status"] == "resolved" and t["waiting_on"] == "none"
    assert [c["author"] for c in t["comments"]] == [core.HUMAN, "agent:a"]
    assert "status: open → resolved" in t["comments"][1]["body"]


def test_thread_defaults_and_ids(root):
    assert core.create_thread("t", "task", core.HUMAN)["waiting_on"] == "agents"
    assert core.create_thread("i", "idea", "agent:a")["waiting_on"] == "none"
    assert [t["id"] for t in core.list_threads()] == [1, 2]


def test_thread_validation(root):
    with pytest.raises(ValueError):
        core.create_thread("x", "nonsense", "agent:a")
    with pytest.raises(ValueError):
        core.create_thread("x", "task", "")
    core.create_thread("x", "task", "agent:a")
    with pytest.raises(ValueError):
        core.add_comment(1, "agent:a", "")  # nothing to do
    with pytest.raises(KeyError):
        core.add_comment(99, "agent:a", "hi")


def test_comment_text_that_looks_like_marker_is_safe(root):
    core.create_thread("x", "task", "agent:a", "body")
    core.add_comment(1, "agent:a", "has --- and # heading\n\n- list")
    t = core.get_thread(1)
    assert len(t["comments"]) == 1 and "- list" in t["comments"][0]["body"]


def test_labs_lineage_and_octal_safe_ids(root):
    core.create_lab("a", "agent:t")
    for i in range(2, 11):
        core.create_lab(f"l{i}", "agent:t", parents=[i - 1])
    (root / "labs" / "011-x").mkdir()
    (root / "labs" / "011-x" / "lab.yaml").write_text("title: x\nparents: [010, 8]\nstatus: done\n")
    labs = {l["id"]: l for l in core.list_labs()}
    assert labs[11]["parents"] == [10, 8]  # 010 must not become octal 8
    assert 11 in labs[10]["children"] and 11 in labs[8]["children"]
    g = core.lab_graph()
    assert {"source": "10", "target": "11"} in [{k: e["data"][k] for k in ("source", "target")} for e in g["edges"]]
    with pytest.raises(ValueError):
        core.create_lab("bad", "agent:t", parents=[99])


def test_render_math_links_and_code(seeded):
    html = core.render("A $a_1 * b_2$ and $$\\sum_i x_i$$ [[elbo]] [[lab:2]] [[nope]] `$not$` costs $5 or $10")
    assert '<span class="math">a_1 * b_2</span>' in html
    assert '<div class="math display">' in html or 'class="math display"' in html
    assert 'href="/wiki/elbo">ELBO</a>' in html
    assert 'href="/labs/2">L002 · child</a>' in html
    assert 'xref broken' in html
    assert "<code>$not$</code>" in html
    assert "$5 or $10" in html


def test_backlinks_and_search(seeded):
    bl = core.backlinks("wiki", "elbo")
    assert any(b["url"] == "/discussion/1" for b in bl)
    assert any(r["url"] == "/discussion/1" for r in core.search("metric"))


def test_check(seeded):
    assert core.check() == []
    (seeded / "wiki" / "bad.md").write_text("---\ntitle: Bad\nsources: [missing]\n---\nSee [[ghost]].\n")
    problems = core.check()
    assert any("ghost" in p for p in problems) and any("missing" in p for p in problems)


def test_human_alias_and_config(root):
    assert core.HUMAN in core.WAITING and core.PROJECT_NAME
    t = core.create_thread("q", "question", "agent:a", waiting_on="human")
    assert t["waiting_on"] == core.HUMAN
    t = core.add_comment(1, "agent:a", "more", waiting_on="human")
    assert t["waiting_on"] == core.HUMAN
