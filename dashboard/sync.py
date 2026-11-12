"""Git sync between the team's clones: `./dash sync`, the dashboard's Sync button, and the agent watcher.

sync() runs, under a lock:
  1. fetch origin;
  2. renumber MY new threads/labs whose number someone else pushed first (links in what I added follow);
  3. rebase my commits onto theirs (uncommitted work is stashed and re-applied). Thread files changed
     on both sides are merged by dashboard/merge_thread.py: comments from both, in date order;
  4. push (with notes tags), retrying if someone pushed in between.

"Held" messages: a message a person wrote for their own agent stays uncommitted until that agent
starts on it (the watcher then commits and pushes it), so nobody else sees an unclaimed request.
Without an `origin` remote everything still works locally; sync just reports "no remote".
"""
from __future__ import annotations

import datetime as dt
import fcntl
import json
import os
import re
import subprocess
import sys
import threading
from contextlib import contextmanager
from pathlib import Path

import yaml

from . import core

CODE = Path(__file__).resolve().parent
MERGE_DRIVER = "dash-thread"
KINDS = {"thread": ("discussion", 4), "lab": ("labs", 3)}  # kind -> (folder, digits in the name)
ID_RE = re.compile(r"^(\d+)-")


class SyncError(RuntimeError):
    pass


# ---------------------------------------------------------------- git helpers

def git(*args: str, timeout: float = 120) -> subprocess.CompletedProcess:
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GIT_EDITOR="true")
    return subprocess.run(["git", *args], cwd=core.ROOT, capture_output=True, text=True,
                          timeout=timeout, env=env)


def _ok(*args: str, **kw) -> str:
    r = git(*args, **kw)
    if r.returncode != 0:
        raise SyncError(f"git {' '.join(args[:3])}: {(r.stderr or r.stdout).strip()[:600]}")
    return r.stdout


def is_repo() -> bool:
    try:
        return git("rev-parse", "--is-inside-work-tree").returncode == 0
    except OSError:
        return False


def remote_url() -> str:
    r = git("remote", "get-url", "origin")
    return r.stdout.strip() if r.returncode == 0 else ""


def branch() -> str:
    return git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip() or "main"


def _has_rev(rev: str) -> bool:
    return git("rev-parse", "--verify", "--quiet", rev).returncode == 0


def ensure_config() -> None:
    """Register the thread merge driver in this clone (.gitattributes routes discussion/*.md to it)."""
    if not is_repo():
        return
    driver = f'"{sys.executable}" "{CODE / "merge_thread.py"}" %O %A %B'
    if git("config", f"merge.{MERGE_DRIVER}.driver").stdout.strip() != driver:
        git("config", f"merge.{MERGE_DRIVER}.name", "dashboard threads: keep comments from both sides")
        git("config", f"merge.{MERGE_DRIVER}.driver", driver)


# ---------------------------------------------------------------- status

def _status_file() -> Path:
    return core.local_dir() / "sync.json"


def _save_status(**kw) -> dict:
    st = {"last": core.now(), "ok": True, "error": "", "notes": [], **kw}
    _status_file().write_text(json.dumps(st))
    return st


def status() -> dict:
    """For the dashboard: last sync, error, notes (renumbering), and how many messages are held."""
    try:
        st = json.loads(_status_file().read_text())
    except (OSError, ValueError):
        st = {"last": "", "ok": True, "error": "", "notes": []}
    st["remote"] = bool(is_repo() and remote_url())
    st["held"] = len(held_threads())
    st["ago"] = _ago(st.get("last", ""))
    return st


def _ago(stamp: str) -> str:
    try:
        mins = int((dt.datetime.now() - dt.datetime.strptime(stamp, "%Y-%m-%d %H:%M")).total_seconds() // 60)
    except ValueError:
        return "never"
    return "just now" if mins < 1 else f"{mins} min ago" if mins < 120 else f"{mins // 60} h ago"


# ---------------------------------------------------------------- held messages and commits

def held_threads() -> list[dict]:
    """My messages to my own agent that it hasn't started on yet (kept uncommitted, so not pushed)."""
    return [t for t in core.pending_threads() if t["trigger"].startswith("new message")]


def commit(paths, message: str, include_held: bool = False) -> bool:
    """Commit just these paths (files or folders, relative to the project). Held thread files are
    skipped unless include_held (the watcher, when its agent starts)."""
    if not is_repo():
        return False
    held = set() if include_held else {t["path"] for t in held_threads()}
    paths = [p for p in dict.fromkeys(str(p) for p in paths) if p not in held]
    paths = [p for p in paths if (core.ROOT / p).exists()  # or deleted/renamed: still in the index or HEAD
             or git("ls-files", "--error-unmatch", "--", p).returncode == 0
             or git("cat-file", "-e", f"HEAD:{p}").returncode == 0]
    if not paths:
        return False
    present = [p for p in paths if (core.ROOT / p).exists()
               or git("ls-files", "--error-unmatch", "--", p).returncode == 0]
    if present:  # (a path only in HEAD was already staged as removed, e.g. by `git mv`)
        _ok("add", "-A", "--", *present)
    if git("diff", "--cached", "--quiet", "HEAD", "--", *paths).returncode == 0:
        return False
    return git("commit", "-q", "-m", message, "--", *paths).returncode == 0


# ---------------------------------------------------------------- renumbering

def _names_in_tree(rev: str, folder: str) -> set[str]:
    r = git("ls-tree", "--name-only", f"{rev}:{folder}")
    return set(r.stdout.split()) if r.returncode == 0 else set()


def _ids(names) -> set[int]:
    return {int(m.group(1)) for n in names if (m := ID_RE.match(n))}


def _my_files(base: str) -> dict[str, set[str] | None]:
    """Files I changed since `base` -> the lines I added (None = the whole file is mine)."""
    out: dict[str, set[str] | None] = {}
    for f in git("ls-files", "--others", "--exclude-standard").stdout.splitlines():
        out[f] = None
    names = git("diff", "--name-status", base).stdout.splitlines()  # working tree vs base
    for line in names:
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        st, f = parts[0], parts[-1]
        if st.startswith("A"):
            out[f] = None
        elif st.startswith(("M", "R")):
            diff = git("diff", "-U0", base, "--", f).stdout
            out[f] = {l[1:] for l in diff.splitlines() if l.startswith("+") and not l.startswith("+++")}
    return {f: v for f, v in out.items() if f.endswith((".md", ".yaml", ".yml"))}


def _rewrite_links(text: str, mine: set[str] | None, kind: str, old: int, new: int) -> str:
    pat = re.compile(rf"\b{kind}:(?:#|L|l)?0*{old}(?!\d)")
    lines = text.split("\n")
    for i, line in enumerate(lines):
        if mine is None or line in mine:
            lines[i] = pat.sub(f"{kind}:{new}", line)
    return "\n".join(lines)


def _rewrite_lab_lists(path: Path, base: str, rel: str, kind: str, old: int, new: int) -> None:
    """lab.yaml `parents:` (labs) / `threads:` (threads): replace `old` only where I added it."""
    key = "parents" if kind == "lab" else "threads"
    try:
        cur = yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError:
        return
    before = git("show", f"{base}:{rel}")
    old_list = (yaml.safe_load(before.stdout) or {}).get(key, []) if before.returncode == 0 else []
    vals = cur.get(key) or []
    if not isinstance(vals, list) or old not in [int(v) for v in vals if str(v).isdigit()] \
            or old in [int(v) for v in (old_list or []) if str(v).isdigit()]:
        return
    cur[key] = [new if str(v).isdigit() and int(v) == old else v for v in vals]
    path.write_text(yaml.safe_dump(cur, sort_keys=False, allow_unicode=True, width=1000))


def _renumber(base: str, upstream: str) -> tuple[list[str], dict, list[str]]:
    """Renumber my new threads/labs that collide with ones pushed upstream since `base`.
    Returns (changed paths, {(kind, old): new}, human-readable notes)."""
    changed, mapping, notes = [], {}, []
    for kind, (folder, digits) in KINDS.items():
        d = core.ROOT / folder
        if not d.exists():
            continue
        base_ids = _ids(_names_in_tree(base, folder))
        up_names = _names_in_tree(upstream, folder)
        up_new = _ids(up_names) - base_ids
        local = sorted(n for n in os.listdir(d) if ID_RE.match(n))
        mine_new = [n for n in local if int(ID_RE.match(n).group(1)) not in base_ids and n not in up_names]
        if not any(int(ID_RE.match(n).group(1)) in up_new for n in mine_new):
            continue
        # Move ALL my new items of this kind above every existing number, keeping their order, so a
        # lab stays younger than its parents and a thread than the ones it follows up.
        nxt = max(_ids(up_names) | _ids(local)) + 1
        for name in sorted(mine_new, key=lambda n: int(ID_RE.match(n).group(1))):
            old = int(ID_RE.match(name).group(1))
            new, nxt = nxt, nxt + 1
            new_name = f"{new:0{digits}d}" + name[len(ID_RE.match(name).group(1)):]
            src, dst = f"{folder}/{name}", f"{folder}/{new_name}"
            if git("ls-files", "--error-unmatch", "--", src).returncode == 0 or \
                    git("ls-files", "--", src + "/").stdout.strip():
                _ok("mv", src, dst)
                changed.append(src)
            else:
                (core.ROOT / src).rename(core.ROOT / dst)
            changed.append(dst)
            if kind == "thread":
                p = core.ROOT / dst
                p.write_text(re.sub(r"(?m)^id: .*$", f"id: {new}", p.read_text(), count=1))
            elif (core.ROOT / dst / "report.md").exists():  # heading "# L001 · title"
                rp = core.ROOT / dst / "report.md"
                rp.write_text(rp.read_text().replace(f"# {core.lab_code(old)} ", f"# {core.lab_code(new)} ", 1))
            mapping[(kind, old)] = new
            notes.append(f"your {kind} #{old} is now #{new} (others pushed new {kind}s with the same numbers first)")
    if mapping:
        for f, mine in _my_files(base).items():
            p = core.ROOT / f
            if not p.is_file():
                continue
            text = p.read_text()
            new_text = text
            for (kind, old), new in mapping.items():
                new_text = _rewrite_links(new_text, mine, kind, old, new)
            if new_text != text:
                p.write_text(new_text)
                changed.append(f)
            if p.name == "lab.yaml":
                for (kind, old), new in mapping.items():
                    before = p.read_text()
                    _rewrite_lab_lists(p, base, f, kind, old, new)
                    if p.read_text() != before:
                        changed.append(f)
    return changed, mapping, notes


# ---------------------------------------------------------------- sync

@contextmanager
def _lock():
    with open(core.local_dir() / "sync.lock", "w") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def sync(pull: bool = True, attempts: int = 3) -> dict:
    """Fetch, renumber collisions, rebase, push. `pull=False` (used while an agent is working in this
    folder) only pushes when that needs no change to the working tree. Returns the saved status plus
    `mapping` {(kind, old_id): new_id}. Raises SyncError (also recorded in the status)."""
    if not is_repo():
        return _save_status(ok=False, error="not a git repository", mapping={})
    if not remote_url():
        return _save_status(ok=True, error="", notes=["no `origin` remote: working locally only"], mapping={})
    ensure_config()
    br = branch()
    up = f"origin/{br}"
    notes, mapping = [], {}
    try:
        with _lock():
            for _ in range(attempts):
                _ok("fetch", "-q", "origin")
                if _has_rev(up) and _has_rev("HEAD"):
                    base = _ok("merge-base", "HEAD", up).strip()
                    behind = int(_ok("rev-list", "--count", f"HEAD..{up}").strip())
                    if behind and not pull:
                        notes.append("others pushed changes; they will be pulled when your agent finishes")
                        break
                    if behind:
                        changed, m, n = _renumber(base, up)
                        mapping.update(m)
                        notes += n
                        if changed:
                            commit(changed, "sync: renumber " + ", ".join(
                                f"{k} #{o} → #{v}" for (k, o), v in m.items()))
                        r = git("rebase", "--autostash", up)
                        if r.returncode != 0:
                            git("rebase", "--abort")
                            raise SyncError("could not merge others' changes automatically (both sides edited "
                                            "the same lines of a non-thread file). Run `git pull --rebase` and "
                                            f"resolve by hand.\n{(r.stdout + r.stderr).strip()[-600:]}")
                    ahead = int(_ok("rev-list", "--count", f"{up}..HEAD").strip())
                elif _has_rev("HEAD"):
                    ahead = 1  # the remote branch doesn't exist yet: first push
                else:
                    break  # no commits yet
                if not ahead:
                    break
                r = git("push", "-q", "--follow-tags", "-u", "origin", f"HEAD:{br}")
                if r.returncode == 0:
                    break
                if "rejected" not in r.stderr and "fetch first" not in r.stderr:
                    raise SyncError(f"git push failed: {r.stderr.strip()[:600]}")
            else:
                raise SyncError("push kept being rejected (others pushing at the same time); try again")
        info = core.team_info()
        if "github.com" in remote_url() and (info["source"] != "github" or _ago(info["fetched"]).endswith(" h ago")):
            core.refresh_team(timeout=10)  # the team = the repo's collaborators, refreshed hourly
    except SyncError as e:
        _save_status(ok=False, error=str(e), notes=notes)
        raise
    st = _save_status(ok=True, error="", notes=notes)
    st["mapping"] = mapping
    return st


def safe_sync(pull: bool = True) -> dict:
    """sync() that never raises (for the watcher and the dashboard): problems go to the status."""
    try:
        return sync(pull=pull)
    except (SyncError, OSError, subprocess.TimeoutExpired) as e:
        return {"ok": False, "error": str(e), "mapping": {}, "notes": []}


_bg = threading.Lock()


def sync_soon(pull: bool = True) -> None:
    """Sync in a background thread (dashboard actions); skipped if one is already running."""
    if not _bg.acquire(blocking=False):
        return

    def run():
        try:
            safe_sync(pull=pull)
        finally:
            _bg.release()
    threading.Thread(target=run, daemon=True).start()


def after_change(paths, message: str, agent_busy: bool = False) -> None:
    """A person changed something in the dashboard: commit it (unless it's a held message for their
    agent) and sync in the background. While an agent works in this folder, only push.
    Without a remote: nothing (a local-only project)."""
    if not (is_repo() and remote_url()):
        return
    commit(paths, message)
    sync_soon(pull=not agent_busy)
