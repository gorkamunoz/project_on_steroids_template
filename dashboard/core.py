"""File formats and project index, shared by the web server and the `dash` CLI.

Files on disk are the single source of truth; nothing here keeps state between
calls. All YAML is read with BaseLoader (every scalar is a string) so that ids
like `010` are never parsed as octal and dates never become datetime objects.
"""
from __future__ import annotations

import datetime as dt
import fcntl
import getpass
import html
import json
import os
import posixpath
import re
import subprocess
from contextlib import contextmanager
from pathlib import Path

import markdown as md_lib
import yaml

ROOT = Path(os.environ.get("PROJECT_ROOT", Path(__file__).resolve().parent.parent))
_HERE = Path(__file__).resolve().parent.parent
_CONFIG_FILE = _HERE / "project.yaml"   # shared, committed
_LOCAL_FILE = _HERE / "local.yaml"      # this clone only, git-ignored: me, port, conda_env


def _load_yaml_file(path: Path) -> dict:
    try:
        data = yaml.load(path.read_text(), Loader=yaml.BaseLoader)
    except (OSError, yaml.YAMLError):
        data = {}
    return data if isinstance(data, dict) else {}


CONFIG = _load_yaml_file(_CONFIG_FILE)  # project.yaml: name, port, conda_env, agent_models
LOCAL = _load_yaml_file(_LOCAL_FILE)    # local.yaml overrides port / conda_env and says who `me` is
CONFIG.update({k: v for k, v in LOCAL.items() if k in ("port", "conda_env") and v})
PROJECT_NAME = CONFIG.get("name") or "Research project"
PORT = CONFIG.get("port") or "8010"
# The person using this clone: their GitHub username (written to local.yaml by ./setup.sh).
ME = (os.environ.get("DASH_ME") or LOCAL.get("me") or getpass.getuser()).strip()

THREAD_TYPES = ["decision", "task", "question", "idea", "bug"]
THREAD_STATUSES = ["open", "in-progress", "resolved", "closed"]
WAITING_SPECIAL = ["agents", "none"]  # besides these, waiting_on names a person (a team member)
PERSON_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def is_human(author: str) -> bool:
    return bool(author) and not author.startswith("agent:")


def requester() -> str:
    """Who `human` means right now: the person whose message started this agent run (set by the
    watcher), else the person using this clone."""
    return (os.environ.get("DASH_REQUESTER") or ME).strip()


def norm_waiting(w):
    if w is None:
        return None
    w = w.strip()
    if w in ("human", "me"):
        return requester()
    if w not in WAITING_SPECIAL and not PERSON_RE.match(w):
        raise ValueError(f"waiting_on must be 'agents', 'none' or a person's username, not {w!r}")
    return w
LAB_STATUSES = ["planned", "running", "done", "failed", "abandoned"]
FIG_EXT = {".png", ".jpg", ".jpeg", ".svg", ".gif", ".webp"}
LARGE_FILE = 5 * 1024 * 1024


# ---------------------------------------------------------------- utilities

def now() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M")


def today() -> str:
    return dt.date.today().isoformat()


def slugify(text: str, maxlen: int = 50) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    if len(s) > maxlen:
        s = s[:maxlen + 1].rsplit("-", 1)[0]
    return s or "untitled"


def as_list(v) -> list:
    if v is None or v == "":
        return []
    if isinstance(v, list):
        return [x for x in v if x not in (None, "")]
    return [x.strip() for x in str(v).split(",") if x.strip()]


AGENT_MODELS = as_list(CONFIG.get("agent_models")) or ["opus"]  # project.yaml; first = default
DEFAULT_MODEL = AGENT_MODELS[0]


# ---------------------------------------------------------------- team

def local_dir() -> Path:
    """Git-ignored per-clone state (team cache, sync status)."""
    d = ROOT / ".dash"
    d.mkdir(exist_ok=True)
    return d


def _team_cache() -> Path:
    return local_dir() / "team.json"


def refresh_team(timeout: float = 20) -> list[str] | None:
    """Ask GitHub who can access this repo (`gh` must be installed and logged in). Returns the
    usernames and caches them, or None if GitHub can't be reached."""
    try:
        res = subprocess.run(["gh", "api", "repos/{owner}/{repo}/collaborators", "--paginate",
                              "--jq", ".[].login"], cwd=ROOT, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if res.returncode != 0:
        return None
    people = sorted({x.strip() for x in res.stdout.split() if x.strip()}, key=str.lower)
    _team_cache().write_text(json.dumps({"people": people, "fetched": now()}))
    return people


def team_info() -> dict:
    """{'people': [...], 'fetched': date or '', 'source': 'github' | 'threads'}."""
    try:
        data = json.loads(_team_cache().read_text())
        people, fetched, source = list(data.get("people", [])), data.get("fetched", ""), "github"
    except (OSError, ValueError):
        people, fetched, source = [], "", "threads"
        for t in list_threads():  # no GitHub list yet: everyone who has written in a thread
            people += [a for a in [t["author"], *(c["author"] for c in t["comments"])] if is_human(a)]
    people = sorted(set(people) | {ME}, key=str.lower)
    return {"people": people, "fetched": fetched, "source": source}


def team() -> list[str]:
    return team_info()["people"]


def thread_model(t: dict) -> str:
    """Model the agent runs with on this thread: its `model` field, else the default."""
    return t.get("model") or DEFAULT_MODEL


def _check_model(model: str) -> str:
    if model not in AGENT_MODELS:
        raise ValueError(f"model must be one of {AGENT_MODELS} (agent_models in project.yaml)")
    return model


def load_yaml(text: str) -> dict:
    data = yaml.load(text, Loader=yaml.BaseLoader)
    return data if isinstance(data, dict) else {}


FM_RE = re.compile(r"\A---[ \t]*\n(.*?)\n---[ \t]*(?:\n|\Z)", re.S)


def split_fm(text: str) -> tuple[dict, str]:
    m = FM_RE.match(text)
    if not m:
        return {}, text
    return load_yaml(m.group(1)), text[m.end():]


def join_fm(meta: dict, body: str) -> str:
    head = yaml.safe_dump(meta, sort_keys=False, allow_unicode=True, width=1000)
    return f"---\n{head}---\n\n{body.strip()}\n"


def rel(p: Path) -> str:
    return p.resolve().relative_to(ROOT.resolve()).as_posix()


@contextmanager
def locked():
    """Process-wide lock so concurrent agents don't allocate the same id."""
    with open(ROOT / ".dash.lock", "w") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def lab_code(i: int) -> str:
    return f"L{i:03d}"


# ---------------------------------------------------------------- discussion

COMMENT_RE = re.compile(r'^<!-- comment author="([^"]*)" date="([^"]*)" -->[ \t]*$', re.M)


def thread_path(tid: int) -> Path | None:
    hits = sorted((ROOT / "discussion").glob(f"{int(tid):04d}-*.md"))
    return hits[0] if hits else None


def parse_thread(path: Path) -> dict:
    meta, body = split_fm(path.read_text())
    parts = COMMENT_RE.split(body)
    comments = [
        {"author": parts[i], "date": parts[i + 1], "body": parts[i + 2].strip()}
        for i in range(1, len(parts), 3)
    ]
    m = re.match(r"(\d+)-", path.name)
    status = meta.get("status", "open")
    return {
        "id": int(meta.get("id") or m.group(1)),
        "title": meta.get("title", path.stem),
        "type": meta.get("type", "question"),
        "status": status,
        "author": meta.get("author", "?"),
        "waiting_on": meta.get("waiting_on", "none") if status in ("open", "in-progress") else "none",
        "labels": as_list(meta.get("labels")),
        "links": as_list(meta.get("links")),
        "created": meta.get("created", ""),
        "updated": meta.get("updated", meta.get("created", "")),
        "wake_at": meta.get("wake_at", ""),
        "model": meta.get("model", ""),
        "run_by": meta.get("run_by", ""),
        "body": parts[0].strip(),
        "comments": comments,
        "path": rel(path),
    }


def list_threads() -> list[dict]:
    d = ROOT / "discussion"
    out = [parse_thread(p) for p in d.glob("[0-9]*-*.md")] if d.exists() else []
    return sorted(out, key=lambda t: t["id"])


def get_thread(tid: int) -> dict | None:
    p = thread_path(tid)
    return parse_thread(p) if p else None


def _check_author(author: str) -> str:
    author = (author or "").strip()
    if not author or '"' in author:
        raise ValueError(f"author is required (use '{ME}' or 'agent:<name>') and may not contain quotes")
    return author


def create_thread(title: str, type: str, author: str, body: str = "", links=None,
                  labels=None, waiting_on: str | None = None, model: str | None = None) -> dict:
    author = _check_author(author)
    if model:
        _check_model(model)
    if type not in THREAD_TYPES:
        raise ValueError(f"type must be one of {THREAD_TYPES}")
    if not title.strip():
        raise ValueError("title is required")
    waiting_on = norm_waiting(waiting_on)
    if waiting_on is None:
        if is_human(author):
            waiting_on = "agents"
        else:
            waiting_on = requester() if type in ("decision", "question") else "none"
    d = ROOT / "discussion"
    d.mkdir(exist_ok=True)
    with locked():
        ids = [int(m.group(1)) for p in d.glob("*.md") if (m := re.match(r"(\d+)-", p.name))]
        tid = max(ids, default=0) + 1
        meta = {
            "id": tid, "title": title.strip(), "type": type, "status": "open",
            "author": author, "waiting_on": waiting_on,
            "labels": as_list(labels), "links": as_list(links),
            "created": now(), "updated": now(),
        }
        if model:
            meta["model"] = model
        path = d / f"{tid:04d}-{slugify(title)}.md"
        path.write_text(join_fm(meta, body))
    return parse_thread(path)


def add_comment(tid: int, author: str, body: str = "", status: str | None = None,
                waiting_on: str | None = None, model: str | None = None) -> dict:
    """Append a comment and/or change status / waiting_on / model. Changes are logged in the comment."""
    author = _check_author(author)
    if model:
        _check_model(model)
    waiting_on = norm_waiting(waiting_on)
    with locked():
        path = thread_path(tid)
        if not path:
            raise KeyError(f"thread {tid} not found")
        text = path.read_text()
        meta, rest = split_fm(text)
        notes = []
        old_status = meta.get("status", "open")
        if status and status != old_status:
            if status not in THREAD_STATUSES:
                raise ValueError(f"status must be one of {THREAD_STATUSES}")
            meta["status"] = status
            notes.append(f"status: {old_status} → {status}")
        new_status = meta.get("status", "open")
        if new_status in ("resolved", "closed"):
            waiting_on = "none"
        elif waiting_on is None and is_human(author) and body.strip():
            waiting_on = "agents"  # a person answered -> ball is in the agents' court
        if waiting_on is not None and waiting_on != meta.get("waiting_on"):
            meta["waiting_on"] = waiting_on
            notes.append(f"waiting on: {waiting_on}")
        old_model = meta.get("model") or DEFAULT_MODEL
        if model and model != old_model:
            meta["model"] = model
            notes.append(f"model: {old_model} → {model}")
        if not body.strip() and not notes:
            raise ValueError("nothing to do: empty comment and no change")
        comment = body.strip()
        if notes:
            comment = (comment + "\n\n" if comment else "") + "_" + " · ".join(notes) + "_"
        meta["id"] = int(meta.get("id", tid))
        meta["updated"] = now()
        new_body = rest.rstrip() + f'\n\n<!-- comment author="{author}" date="{now()}" -->\n{comment}\n'
        path.write_text(join_fm(meta, new_body))
    return parse_thread(path)


def set_meta(tid: int, **fields) -> dict:
    """Change thread metadata without adding a comment (None removes a key). Doesn't touch `updated`."""
    with locked():
        path = thread_path(tid)
        if not path:
            raise KeyError(f"thread {tid} not found")
        meta, rest = split_fm(path.read_text())
        for k, v in fields.items():
            if v is None:
                meta.pop(k, None)
            else:
                meta[k] = v
        meta["id"] = int(meta.get("id", tid))
        path.write_text(join_fm(meta, rest))
    return parse_thread(path)


def last_author(t: dict) -> str:
    return t["comments"][-1]["author"] if t["comments"] else t["author"]


def last_human(t: dict) -> str:
    """The person who wrote last on the thread (whose request an agent run serves)."""
    for a in [c["author"] for c in reversed(t["comments"])] + [t["author"]]:
        if is_human(a):
            return a
    return ""


def pending_threads(me: str | None = None) -> list[dict]:
    """Threads the agent watcher of `me` (default: this clone's person) should pick up now. A thread
    waiting on agents is mine when I wrote its latest entry (a new request or answer), or when my
    agent snoozed it and the snooze has expired. Someone else's message on a thread that another
    person's agent has snoozed doesn't start my agent; that agent reads it when it wakes up."""
    me = me or ME
    out = []
    for t in list_threads():
        if t["status"] not in ("open", "in-progress") or t["waiting_on"] != "agents":
            continue
        owner = t["run_by"] or me
        if last_author(t) == me and not (t["wake_at"] and owner != me):
            t["trigger"] = f"new message from {me}"
        elif t["wake_at"] and t["wake_at"] <= now() and owner == me:
            t["trigger"] = f"snooze expired ({t['wake_at']})"
        else:
            continue
        out.append(t)
    return sorted(out, key=lambda t: t["updated"])


def snooze(tid: int, author: str, until: str, body: str = "") -> dict:
    """Agent parks a thread (e.g. while training runs) and gets relaunched after `until`, by the
    watcher of the person whose machine it runs on (`run_by`)."""
    dt.datetime.strptime(until, "%Y-%m-%d %H:%M")  # validate format
    add_comment(tid, author, (body.strip() + "\n\n" if body.strip() else "") + f"_snoozed until {until}_",
                waiting_on="agents")
    return set_meta(tid, wake_at=until, run_by=ME)


# ---------------------------------------------------------------- labs

LAB_DIR_RE = re.compile(r"^(\d+)-(.+)$")


def lab_dir(lid: int) -> Path | None:
    d = ROOT / "labs"
    for p in sorted(d.glob("[0-9]*-*")) if d.exists() else []:
        m = LAB_DIR_RE.match(p.name)
        if p.is_dir() and m and int(m.group(1)) == int(lid):
            return p
    return None


def parse_lab(d: Path) -> dict:
    m = LAB_DIR_RE.match(d.name)
    lid = int(m.group(1))
    meta, error = {}, ""
    y = d / "lab.yaml"
    try:
        meta = load_yaml(y.read_text()) if y.exists() else {}
        if not y.exists():
            error = "missing lab.yaml"
    except yaml.YAMLError as e:
        error = f"lab.yaml parse error: {e}"
    parents = []
    for p in as_list(meta.get("parents")):
        try:
            parents.append(int(str(p).lstrip("Ll")))
        except ValueError:
            error = f"bad parent id {p!r}"
    metrics = meta.get("metrics") if isinstance(meta.get("metrics"), dict) else {}
    return {
        "id": lid, "code": lab_code(lid), "slug": d.name, "dir": rel(d),
        "title": meta.get("title", m.group(2).replace("-", " ")),
        "status": meta.get("status", "planned"),
        "parents": parents, "children": [],
        "created": meta.get("created", ""), "author": meta.get("author", ""),
        "hypothesis": meta.get("hypothesis", ""), "conclusion": meta.get("conclusion", ""),
        "tags": as_list(meta.get("tags")), "metrics": metrics,
        "wiki": as_list(meta.get("wiki")),
        "threads": [int(t) for t in as_list(meta.get("threads")) if str(t).isdigit()],
        "error": error,
    }


def list_labs() -> list[dict]:
    d = ROOT / "labs"
    labs = [parse_lab(p) for p in sorted(d.iterdir()) if p.is_dir() and LAB_DIR_RE.match(p.name)] if d.exists() else []
    by_id = {l["id"]: l for l in labs}
    for l in labs:
        for p in l["parents"]:
            if p in by_id:
                by_id[p]["children"].append(l["id"])
    return sorted(labs, key=lambda l: l["id"])


def get_lab(lid: int) -> dict | None:
    lab = next((l for l in list_labs() if l["id"] == int(lid)), None)
    if not lab:
        return None
    d = ROOT / lab["dir"]
    report = d / "report.md"
    lab["report"] = split_fm(report.read_text())[1] if report.exists() else ""
    lab["figures"] = [rel(p) for p in sorted(d.rglob("*")) if p.suffix.lower() in FIG_EXT and p.is_file()]
    lab["files"] = list_files(d, limit=300)
    return lab


def lab_graph() -> dict:
    labs = list_labs()
    ids = {l["id"] for l in labs}
    nodes = [{"data": {"id": str(l["id"]), "code": l["code"], "label": f'{l["code"]}\n{l["title"] if len(l["title"]) < 48 else l["title"][:45] + "…"}',
                       "title": l["title"], "status": l["status"], "hypothesis": l["hypothesis"],
                       "conclusion": l["conclusion"], "metrics": l["metrics"], "tags": l["tags"],
                       "created": l["created"], "parents": l["parents"], "children": l["children"]}}
             for l in labs]
    edges = [{"data": {"id": f"{p}->{l['id']}", "source": str(p), "target": str(l["id"])}}
             for l in labs for p in l["parents"] if p in ids]
    return {"nodes": nodes, "edges": edges}


def create_lab(title: str, author: str, parents=None, hypothesis: str = "", tags=None) -> Path:
    author = _check_author(author)
    d = ROOT / "labs"
    d.mkdir(exist_ok=True)
    parents = [int(str(p).lstrip("Ll")) for p in as_list(parents)]
    with locked():
        existing = {l["id"] for l in list_labs()}
        missing = [p for p in parents if p not in existing]
        if missing:
            raise ValueError(f"unknown parent lab(s): {missing}")
        lid = max(existing, default=0) + 1
        path = d / f"{lid:03d}-{slugify(title, 40)}"
        (path / "figures").mkdir(parents=True)
        meta = {"title": title, "status": "planned", "parents": parents, "created": today(),
                "author": author, "hypothesis": hypothesis or "TODO: what do we expect and why?",
                "conclusion": "", "tags": as_list(tags), "metrics": {}, "wiki": [], "threads": []}
        (path / "lab.yaml").write_text(yaml.safe_dump(meta, sort_keys=False, allow_unicode=True, width=1000))
        (path / "report.md").write_text(
            f"# {lab_code(lid)} · {title}\n\n## Goal\n\n## Setup\n\n## Results\n\n## Conclusion\n\n## Next steps\n")
    return path


# ---------------------------------------------------------------- wiki / refs / skills

def _title_from(meta: dict, body: str, fallback: str) -> str:
    if meta.get("title"):
        return meta["title"]
    m = re.search(r"^#\s+(.+)$", body, re.M)
    return m.group(1).strip() if m else fallback


def list_wiki() -> list[dict]:
    d = ROOT / "wiki"
    out = []
    for p in sorted(d.rglob("*.md")) if d.exists() else []:
        meta, body = split_fm(p.read_text())
        slug = p.relative_to(d).with_suffix("").as_posix()
        mtime = dt.datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        out.append({"slug": slug, "title": _title_from(meta, body, slug), "tags": as_list(meta.get("tags")),
                    "sources": as_list(meta.get("sources")), "status": meta.get("status", ""),
                    "updated": meta.get("updated", mtime[:10]), "mtime": mtime, "path": rel(p)})
    return out


def get_wiki(slug: str) -> dict | None:
    p = ROOT / "wiki" / f"{slug}.md"
    if not p.is_file() or ".." in slug:
        return None
    page = next(w for w in list_wiki() if w["slug"] == slug)
    page["body"] = split_fm(p.read_text())[1]
    page["backlinks"] = backlinks("wiki", slug)
    return page


def create_wiki(slug: str, title: str, author: str) -> Path:
    p = ROOT / "wiki" / f"{slugify(slug)}.md"
    if p.exists():
        raise ValueError(f"{rel(p)} already exists")
    p.parent.mkdir(exist_ok=True)
    meta = {"title": title, "tags": [], "sources": [], "status": "draft", "updated": today(), "author": author}
    p.write_text(join_fm(meta, f"# {title}\n\n**In one sentence:** TODO\n\n## Definition\n\n## Why it matters here\n\n## Related\n"))
    return p


def list_refs() -> list[dict]:
    d = ROOT / "refs"
    out = []
    for p in sorted(d.iterdir()) if d.exists() else []:
        if not p.is_dir() or p.name.startswith("."):
            continue
        y = p / "ref.yaml"
        meta = load_yaml(y.read_text()) if y.exists() else {}
        out.append({"key": p.name, "title": meta.get("title", p.name), "authors": meta.get("authors", ""),
                    "year": meta.get("year", ""), "venue": meta.get("venue", ""), "url": meta.get("url", ""),
                    "doi": meta.get("doi", ""), "added": meta.get("added", ""),
                    "added_by": meta.get("added_by", ""), "notes": meta.get("notes", ""),
                    "files": [rel(f) for f in sorted(p.iterdir()) if f.is_file() and f.name != "ref.yaml"],
                    "error": "" if y.exists() else "missing ref.yaml"})
    return out


def list_skills() -> list[dict]:
    d = ROOT / "skills"
    out = []
    for p in sorted(d.glob("*/SKILL.md")) if d.exists() else []:
        meta, body = split_fm(p.read_text())
        out.append({"name": meta.get("name", p.parent.name), "dir": p.parent.name,
                    "description": meta.get("description", ""), "body": body, "path": rel(p)})
    return out


def list_files(d: Path, limit: int = 500) -> list[dict]:
    out = []
    for p in sorted(d.rglob("*")):
        if any(part.startswith(".") or part == "__pycache__" for part in p.relative_to(d).parts):
            continue
        if p.is_file():
            out.append({"path": rel(p), "name": p.relative_to(d).as_posix(), "size": p.stat().st_size})
            if len(out) >= limit:
                break
    return out


# ---------------------------------------------------------------- cross-links

LINK_RE = re.compile(r"\[\[([^\]|\n]+)(?:\|([^\]\n]+))?\]\]")
KINDS = ("wiki", "lab", "thread", "ref", "skill", "file")


def link_index() -> dict:
    return {
        "wiki": {w["slug"]: w["title"] for w in list_wiki()},
        "lab": {str(l["id"]): f'{l["code"]} · {l["title"]}' for l in list_labs()},
        "thread": {str(t["id"]): f'#{t["id"]} {t["title"]}' for t in list_threads()},
        "ref": {r["key"]: r["key"] for r in list_refs()},
        "skill": {s["dir"]: s["name"] for s in list_skills()},
    }


def parse_target(target: str) -> tuple[str, str]:
    target = target.strip()
    kind, sep, key = target.partition(":")
    if not sep or kind not in KINDS:
        return "wiki", target
    key = key.strip()
    if kind == "lab":
        key = str(int(key.lstrip("Ll"))) if key.lstrip("Ll").isdigit() else key
    if kind == "thread":
        key = key.lstrip("#")
    return kind, key


def resolve_link(target: str, idx: dict) -> tuple[str, str, bool]:
    """-> (url, default text, exists)"""
    kind, key = parse_target(target)
    if kind == "file":
        return f"/browse/{key}", key, (ROOT / key).exists()
    url = {"wiki": f"/wiki/{key}", "lab": f"/labs/{key}", "thread": f"/discussion/{key}",
           "ref": f"/refs/{key}", "skill": f"/skills/{key}"}[kind]
    known = idx.get(kind, {})
    return url, known.get(key, target), key in known


def links_in(text: str) -> list[tuple[str, str]]:
    return [parse_target(m.group(1)) for m in LINK_RE.finditer(text or "")]


def backlinks(kind: str, key: str) -> list[dict]:
    """Every page whose text (or metadata) links to kind:key."""
    out = []
    want = (kind, str(key))
    for w in list_wiki():
        if want in links_in((ROOT / w["path"]).read_text()):
            out.append({"url": f"/wiki/{w['slug']}", "text": w["title"], "kind": "wiki"})
    for l in list_labs():
        rep = ROOT / l["dir"] / "report.md"
        meta_links = [("wiki", w) for w in l["wiki"]] + [("thread", str(t)) for t in l["threads"]]
        if want in meta_links or (rep.exists() and want in links_in(rep.read_text())):
            out.append({"url": f"/labs/{l['id']}", "text": f"{l['code']} · {l['title']}", "kind": "lab"})
    for t in list_threads():
        texts = t["body"] + "\n".join(c["body"] for c in t["comments"])
        if want in links_in(texts) or want in [parse_target(x) for x in t["links"]]:
            out.append({"url": f"/discussion/{t['id']}", "text": f"#{t['id']} {t['title']}", "kind": "thread"})
    return out


# ---------------------------------------------------------------- markdown

CODE_RE = re.compile(r"^(```|~~~).*?^\1[ \t]*$|`[^`\n]+`", re.M | re.S)
MATH_RE = re.compile(
    r"\$\$(.+?)\$\$|\\\[(.+?)\\\]|\\\((.+?)\\\)"
    r"|(?<![\\$\w])\$([^\s$](?:[^$\n]*?[^\s$\\])?)\$(?![\w$])", re.S)
PH_RE = re.compile(r"⟦(\d+)⟧")
# GitHub-style: a list may start right after a paragraph line (python-markdown needs a blank line)
LIST_START_RE = re.compile(r"(?m)^((?![ \t]*(?:[-*+]|\d+\.)[ \t]).*\S.*)\n(?=[ \t]{0,3}(?:[-*+]|\d+\.)[ \t])")


REL_URL_RE = re.compile(r'(src|href)="(?!/|#|[a-zA-Z][a-zA-Z0-9+.-]*:)([^"]+)"')


def render(text: str, idx: dict | None = None, base: str | None = None) -> str:
    """Markdown -> HTML with protected LaTeX math ($..$, $$..$$, \\(..\\), \\[..\\]) and [[cross-links]].

    `base` = folder (relative to ROOT) the markdown lives in; relative image/link URLs are resolved
    against it (images -> /raw/..., links -> /browse/...).
    """
    if not text:
        return ""
    idx = idx if idx is not None else link_index()
    store: list[str] = []

    def stash(html_: str) -> str:
        store.append(html_)
        return f"⟦{len(store) - 1}⟧"

    def math(m):
        disp = m.group(1) is not None or m.group(2) is not None
        tex = next(g for g in m.groups() if g is not None)
        tag = "div" if disp else "span"
        return stash(f'<{tag} class="math{" display" if disp else ""}">{html.escape(tex)}</{tag}>')

    def link(m):
        url, default, ok = resolve_link(m.group(1), idx)
        label = html.escape(m.group(2) or default)
        extra = "" if ok else ' broken" title="not found'
        return stash(f'<a class="xref{extra}" href="{url}">{label}</a>')

    def protect(segment: str) -> str:
        segment = LIST_START_RE.sub(r"\1\n\n", segment)
        return LINK_RE.sub(link, MATH_RE.sub(math, segment))

    out, pos = [], 0
    for m in CODE_RE.finditer(text):
        out += [protect(text[pos:m.start()]), m.group(0)]
        pos = m.end()
    out.append(protect(text[pos:]))
    body = md_lib.markdown("".join(out), extensions=["fenced_code", "tables", "toc", "sane_lists"])
    body = re.sub(r"<p>(⟦\d+⟧)</p>", r"\1", body)
    if base is not None:
        def fix(m):
            target = posixpath.normpath(posixpath.join(base, m.group(2)))
            return f'{m.group(1)}="/{"raw" if m.group(1) == "src" else "browse"}/{target}"'
        body = REL_URL_RE.sub(fix, body)
    return PH_RE.sub(lambda m: store[int(m.group(1))], body)


# ---------------------------------------------------------------- search & check

def search(q: str) -> list[dict]:
    q = q.strip().lower()
    if not q:
        return []
    out = []

    def hit(kind, url, title, text):
        low = text.lower()
        i = low.find(q)
        if i >= 0 or q in title.lower():
            snip = text[max(0, i - 80): i + 120].replace("\n", " ") if i >= 0 else ""
            out.append({"kind": kind, "url": url, "title": title, "snippet": snip})

    for w in list_wiki():
        hit("wiki", f"/wiki/{w['slug']}", w["title"], (ROOT / w["path"]).read_text())
    for l in list_labs():
        rep = ROOT / l["dir"] / "report.md"
        txt = " ".join([l["hypothesis"], l["conclusion"], " ".join(l["tags"]), rep.read_text() if rep.exists() else ""])
        hit("lab", f"/labs/{l['id']}", f"{l['code']} · {l['title']}", txt)
    for t in list_threads():
        hit("thread", f"/discussion/{t['id']}", f"#{t['id']} {t['title']}",
            t["body"] + "\n" + "\n".join(c["body"] for c in t["comments"]))
    for r in list_refs():
        hit("ref", f"/refs/{r['key']}", r["title"], f"{r['authors']} {r['notes']} {r['key']}")
    for s in list_skills():
        hit("skill", f"/skills/{s['dir']}", s["name"], s["description"] + s["body"])
    return out


def check() -> list[str]:
    """Validate project conventions. Returns human-readable problems (empty list = all good)."""
    problems = []
    idx = link_index()
    labs = list_labs()
    ids = {l["id"] for l in labs}
    for l in labs:
        if l["error"]:
            problems.append(f"{l['dir']}: {l['error']}")
        if l["status"] not in LAB_STATUSES:
            problems.append(f"{l['dir']}: status {l['status']!r} not in {LAB_STATUSES}")
        for p in l["parents"]:
            if p not in ids:
                problems.append(f"{l['dir']}: parent {lab_code(p)} does not exist")
            elif p >= l["id"]:
                problems.append(f"{l['dir']}: parent {lab_code(p)} is not older than the lab itself")
        for w in l["wiki"]:
            if w not in idx["wiki"]:
                problems.append(f"{l['dir']}: wiki page {w!r} does not exist")
    people = team()
    for t in list_threads():
        if t["type"] not in THREAD_TYPES:
            problems.append(f"{t['path']}: type {t['type']!r} not in {THREAD_TYPES}")
        if t["status"] not in THREAD_STATUSES:
            problems.append(f"{t['path']}: status {t['status']!r} not in {THREAD_STATUSES}")
        w = t["waiting_on"]
        if w not in WAITING_SPECIAL and t["status"] in ("open", "in-progress") and w not in people:
            problems.append(f"{t['path']}: waiting on {w!r}, who is not in the team {people}")
        if t["model"] and t["model"] not in AGENT_MODELS and t["status"] in ("open", "in-progress"):
            problems.append(f"{t['path']}: model {t['model']!r} not in agent_models {AGENT_MODELS} (project.yaml)")
    for r in list_refs():
        if r["error"]:
            problems.append(f"refs/{r['key']}: {r['error']}")
    for w in list_wiki():
        for src in w["sources"]:
            if src not in idx["ref"]:
                problems.append(f"{w['path']}: source {src!r} is not in refs/")
    md_files = [ROOT / w["path"] for w in list_wiki()] + [ROOT / l["dir"] / "report.md" for l in labs] \
        + [ROOT / t["path"] for t in list_threads()]
    for f in md_files:
        if f.exists():
            for m in LINK_RE.finditer(f.read_text()):
                if not resolve_link(m.group(1), idx)[2]:
                    problems.append(f"{rel(f)}: broken link [[{m.group(1)}]]")
    problems += large_unignored_files()
    return problems


def large_unignored_files() -> list[str]:
    """Files > 5 MB that git would pick up (they belong in an ignored outputs/ folder)."""
    try:
        res = subprocess.run(["git", "ls-files", "--others", "--cached", "--exclude-standard", "-z"],
                             cwd=ROOT, capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return []
    if res.returncode != 0:
        return []
    out = []
    for f in filter(None, res.stdout.split("\0")):
        p = ROOT / f
        if p.is_file() and p.stat().st_size > LARGE_FILE:
            out.append(f"{f}: {p.stat().st_size / 1e6:.1f} MB would be committed; move it to an outputs/ folder (git-ignored)")
    return out
