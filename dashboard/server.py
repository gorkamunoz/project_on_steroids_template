"""Local research dashboard. Run with ./run_server.sh  ->  http://localhost:<port from project.yaml>

HTML pages for the human, a small JSON API under /api for agents/scripts.
Everything is read from disk on each request (manual refresh = latest state).
"""
from __future__ import annotations

import mimetypes
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from . import agents, core, notes, sync

HERE = Path(__file__).parent
app = FastAPI(title=f"{core.PROJECT_NAME} dashboard")
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
templates = Jinja2Templates(directory=HERE / "templates")
TEXT_EXT = {".py", ".md", ".txt", ".yaml", ".yml", ".json", ".toml", ".cfg", ".sh", ".tex", ".bib",
            ".csv", ".tsv", ".log", ".ini", ".jl", ".ipynb", ".html", ".js", ".css", ""}


def page(request: Request, name: str, **ctx) -> HTMLResponse:
    idx = core.link_index()
    ctx.update(
        request=request, idx=idx, core=core,
        md=lambda text, base=None: core.render(text, idx, base),
        nav_waiting=sum(1 for t in core.list_threads() if t["waiting_on"] == core.ME),
        nav_active=agents.active_runs(), nav_paused=agents.is_paused(),
        nav_alive=agents.watcher_alive(), nav_pending=bool(core.pending_threads()), team=core.team(),
        nav_sync=sync.status(), nav_changes=sync.uncommitted(limit=0)["count"],
    )
    return templates.TemplateResponse(request, name, ctx)


def safe_path(path: str) -> Path:
    p = (core.ROOT / path).resolve()
    root = core.ROOT.resolve()
    if p != root and root not in p.parents:
        raise HTTPException(403, "outside project")
    if any(part.startswith(".") for part in p.relative_to(root).parts):
        raise HTTPException(403, "hidden path")
    if not p.exists():
        raise HTTPException(404, f"{path} not found")
    return p


# ---------------------------------------------------------------- pages

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    threads = core.list_threads()
    labs = core.list_labs()
    wiki = sorted(core.list_wiki(), key=lambda w: w["mtime"], reverse=True)
    counts = {s: sum(1 for l in labs if l["status"] == s) for s in core.LAB_STATUSES}
    return page(request, "home.html",
                mine=[t for t in threads if t["waiting_on"] == core.ME],
                agents=[t for t in threads if t["waiting_on"] == "agents"],
                recent=sorted(threads, key=lambda t: t["updated"], reverse=True)[:8],
                labs=list(reversed(labs))[:6], lab_counts=counts, wiki=wiki[:6])


@app.get("/discussion", response_class=HTMLResponse)
def discussion(request: Request, view: str = "open", type: str = ""):
    threads = core.list_threads()
    views = {
        "open": lambda t: t["status"] in ("open", "in-progress"),
        "mine": lambda t: t["waiting_on"] == core.ME,
        "agents": lambda t: t["waiting_on"] == "agents",
        "closed": lambda t: t["status"] in ("resolved", "closed"),
        "all": lambda t: True,
    }
    sel = [t for t in threads if views.get(view, views["open"])(t) and (not type or t["type"] == type)]
    sel.sort(key=lambda t: t["updated"], reverse=True)
    counts = {k: sum(1 for t in threads if f(t)) for k, f in views.items()}
    return page(request, "discussion.html", threads=sel, view=view, type=type, counts=counts)


@app.get("/discussion/new", response_class=HTMLResponse)
def discussion_new_form(request: Request, link: str = ""):
    return page(request, "thread_new.html", link=link)


@app.post("/discussion/new")
def discussion_new(title: str = Form(...), type: str = Form(...), body: str = Form(""),
                   links: str = Form(""), waiting_on: str = Form("agents"), model: str = Form("")):
    t = core.create_thread(title, type, core.ME, body, links=links, waiting_on=waiting_on, model=model or None)
    sync.after_change([t["path"]], f"thread #{t['id']}: new {type} by {core.ME}", agent_busy=bool(agents.active_runs()))
    return RedirectResponse(f"/discussion/{t['id']}", status_code=303)


@app.get("/discussion/{tid}", response_class=HTMLResponse)
def thread_page(request: Request, tid: int):
    t = core.get_thread(tid)
    if not t:
        raise HTTPException(404, "thread not found")
    links = [(*core.resolve_link(x, core.link_index()), x) for x in t["links"]]
    held = any(h["id"] == tid for h in sync.held_threads())
    return page(request, "thread.html", t=t, links=links, held=held)


@app.post("/discussion/{tid}/comment")
def thread_comment(tid: int, body: str = Form(""), status: str = Form(""), waiting_on: str = Form(""),
                   model: str = Form("")):
    try:
        t = core.add_comment(tid, core.ME, body, status or None, waiting_on or None, model or None)
        sync.after_change([t["path"]], f"thread #{tid}: comment by {core.ME}", agent_busy=bool(agents.active_runs()))
    except ValueError:
        pass  # empty submit: just reload
    return RedirectResponse(f"/discussion/{tid}#bottom", status_code=303)


@app.get("/changes", response_class=HTMLResponse)
def changes(request: Request, done: int = -1, error: str = ""):
    return page(request, "changes.html", u=sync.uncommitted(limit=20, sizes=True), busy=bool(agents.active_runs()),
                done=done, error=error)


@app.post("/changes")
def changes_commit(message: str = Form("")):
    from urllib.parse import quote
    if agents.active_runs():
        return RedirectResponse("/changes?error=" + quote("An agent is working in this folder; wait until it finishes."),
                                status_code=303)
    try:
        n = sync.commit_all(message)
    except sync.SyncError as e:
        return RedirectResponse("/changes?error=" + quote(str(e)), status_code=303)
    if sync.enabled():
        sync.safe_sync()
    return RedirectResponse(f"/changes?done={n}", status_code=303)


@app.post("/sync")
def sync_now(request: Request):
    sync.safe_sync(pull=not agents.active_runs())  # while an agent works here, only push
    return RedirectResponse(request.headers.get("referer") or "/", status_code=303)


@app.get("/labs", response_class=HTMLResponse)
def labs(request: Request, focus: int | None = None):
    return page(request, "labs.html", labs=core.list_labs(), graph=core.lab_graph(), focus=focus)


@app.get("/labs/{lid}", response_class=HTMLResponse)
def lab_page(request: Request, lid: int):
    lab = core.get_lab(lid)
    if not lab:
        raise HTTPException(404, "lab not found")
    by_id = {l["id"]: l for l in core.list_labs()}
    threads = [t for t in core.list_threads() if t["id"] in lab["threads"]]
    return page(request, "lab.html", lab=lab, by_id=by_id, threads=threads,
                backlinks=core.backlinks("lab", str(lid)))


@app.get("/wiki", response_class=HTMLResponse)
def wiki_index(request: Request, tag: str = ""):
    pages = [w for w in core.list_wiki() if w["slug"] != "index" and (not tag or tag in w["tags"])]
    tags = sorted({t for w in core.list_wiki() for t in w["tags"]})
    intro = core.get_wiki("index")
    return page(request, "wiki_index.html", pages=pages, tags=tags, tag=tag, intro=intro)


@app.get("/wiki/{slug:path}", response_class=HTMLResponse)
def wiki_page(request: Request, slug: str):
    w = core.get_wiki(slug)
    if not w:
        return page(request, "missing.html", what=f"wiki page '{slug}'",
                    hint=f"An agent can create it with: ./dash wiki new {slug} --title \"...\"")
    return page(request, "wiki_page.html", w=w)


@app.get("/refs", response_class=HTMLResponse)
def refs(request: Request):
    return page(request, "refs.html", refs=core.list_refs())


@app.get("/refs/{key}", response_class=HTMLResponse)
def ref_page(request: Request, key: str):
    r = next((r for r in core.list_refs() if r["key"] == key), None)
    if not r:
        raise HTTPException(404, "ref not found")
    return page(request, "ref.html", r=r, backlinks=core.backlinks("ref", key))


@app.get("/skills", response_class=HTMLResponse)
def skills(request: Request):
    return page(request, "skills.html", skills=core.list_skills())


@app.get("/skills/{name}", response_class=HTMLResponse)
def skill_page(request: Request, name: str):
    s = next((s for s in core.list_skills() if s["dir"] == name), None)
    if not s:
        raise HTTPException(404, "skill not found")
    return page(request, "doc.html", title=s["name"], subtitle=s["description"], body=s["body"], path=s["path"])


@app.get("/search", response_class=HTMLResponse)
def search(request: Request, q: str = ""):
    return page(request, "search.html", q=q, results=core.search(q))


@app.get("/browse", response_class=HTMLResponse)
@app.get("/browse/{path:path}", response_class=HTMLResponse)
def browse(request: Request, path: str = ""):
    p = safe_path(path)
    if p.is_dir():
        entries = sorted((x for x in p.iterdir() if not x.name.startswith(".") and x.name != "__pycache__"),
                         key=lambda x: (x.is_file(), x.name))
        return page(request, "browse.html", path=path.strip("/"), entries=entries)
    kind = "text" if p.suffix.lower() in TEXT_EXT and p.stat().st_size < 2_000_000 else "binary"
    if p.suffix.lower() == ".md":
        kind = "md"
    elif p.suffix.lower() in core.FIG_EXT:
        kind = "image"
    elif p.suffix.lower() == ".pdf":
        kind = "pdf"
    content = p.read_text(errors="replace") if kind in ("text", "md") else ""
    if kind == "md":
        content = core.split_fm(content)[1]
    return page(request, "view.html", path=path.strip("/"), kind=kind, content=content, size=p.stat().st_size)


@app.get("/raw/{path:path}")
def raw(path: str):
    p = safe_path(path)
    if p.is_dir():
        raise HTTPException(400, "is a directory")
    media = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
    if media.startswith("text/") or p.suffix in (".py", ".yaml", ".md"):
        media = "text/plain; charset=utf-8"
    return FileResponse(p, media_type=media)


@app.get("/notes", response_class=HTMLResponse)
def notes_page(request: Request):
    return page(request, "notes.html", versions=notes.list_versions(), draft=notes.draft_info(),
                has_source=(notes.notes_dir() / "main.tex").exists())


@app.get("/notes/{code}", response_class=HTMLResponse)
def notes_version(request: Request, code: str, show: str = "pdf"):
    if code == "draft":
        d = notes.draft_info()
        if not d:
            raise HTTPException(404, "no draft build yet")
        v = {"version": "draft", "pdf": d["pdf"], "date": d["built"], "pages": d["pages"], "summary":
             "Working draft: not a released version", "changes": [], "diff": None, "tex": None}
    else:
        v = notes.get_version(code)
        if not v:
            raise HTTPException(404, "version not found")
    return page(request, "notes_version.html", v=v, show=show if v.get("diff") else "pdf")


@app.get("/agents", response_class=HTMLResponse)
def agents_page(request: Request):
    return page(request, "agents.html", runs=agents.list_runs(100), pending=core.pending_threads(),
                paused=agents.is_paused(), alive=agents.watcher_alive())


@app.post("/agents/pause")
def agents_pause(paused: str = Form("")):
    agents.set_paused(paused == "1")
    return RedirectResponse("/agents", status_code=303)


@app.get("/agents/{rid}", response_class=HTMLResponse)
def agent_run(request: Request, rid: str):
    run = agents.get_run(rid)
    if not run:
        raise HTTPException(404, "run not found")
    return page(request, "agent_run.html", run=run, events=agents.transcript(rid))


# ---------------------------------------------------------------- JSON API

class ThreadIn(BaseModel):
    title: str
    type: str
    author: str
    body: str = ""
    links: list[str] = []
    labels: list[str] = []
    waiting_on: str | None = None


class CommentIn(BaseModel):
    author: str
    body: str = ""
    status: str | None = None
    waiting_on: str | None = None


def _api(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except KeyError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(422, str(e))


@app.get("/api/threads")
def api_threads(status: str = "", waiting_on: str = "", type: str = ""):
    return [t for t in core.list_threads()
            if (not status or t["status"] == status) and (not waiting_on or t["waiting_on"] == waiting_on)
            and (not type or t["type"] == type)]


@app.get("/api/threads/{tid}")
def api_thread(tid: int):
    t = core.get_thread(tid)
    if not t:
        raise HTTPException(404, "thread not found")
    return t


@app.post("/api/threads", status_code=201)
def api_thread_new(t: ThreadIn):
    return _api(core.create_thread, t.title, t.type, t.author, t.body, t.links, t.labels, t.waiting_on)


@app.post("/api/threads/{tid}/comments")
def api_comment(tid: int, c: CommentIn):
    return _api(core.add_comment, tid, c.author, c.body, c.status, c.waiting_on)


@app.get("/api/labs")
def api_labs():
    return core.list_labs()


@app.get("/api/labs/graph")
def api_lab_graph():
    return core.lab_graph()


@app.get("/api/labs/{lid}")
def api_lab(lid: int):
    lab = core.get_lab(lid)
    if not lab:
        raise HTTPException(404, "lab not found")
    return lab


@app.get("/api/wiki")
def api_wiki():
    return core.list_wiki()


@app.get("/api/wiki/{slug:path}")
def api_wiki_page(slug: str):
    w = core.get_wiki(slug)
    if not w:
        raise HTTPException(404, "wiki page not found")
    return w


@app.get("/api/agents")
def api_agents():
    return {"paused": agents.is_paused(), "watcher_alive": agents.watcher_alive(), "pending": [t["id"] for t in core.pending_threads()],
            "runs": agents.list_runs(50)}


@app.get("/api/check")
def api_check():
    return {"problems": core.check()}
