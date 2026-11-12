"""State of autonomous agent runs, stored in .agents/ (git-ignored).

.agents/runs/<run_id>.json   metadata (thread, status, session id, cost, ...)
.agents/runs/<run_id>.jsonl  raw `claude -p --output-format stream-json` transcript
.agents/paused               if present, the watcher launches nothing
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from . import core


def agents_dir() -> Path:
    return core.ROOT / ".agents"


def runs_dir() -> Path:
    d = agents_dir() / "runs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_run(run: dict) -> None:
    p = runs_dir() / f"{run['id']}.json"
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(run, indent=1))
    tmp.replace(p)


def _alive(pid) -> bool:
    try:
        os.kill(int(pid), 0)
        return True
    except (OSError, ValueError, TypeError):
        return False


def list_runs(limit: int = 100) -> list[dict]:
    d = agents_dir() / "runs"
    if not d.exists():
        return []
    runs = []
    for p in sorted(d.glob("*.json"), reverse=True)[:limit]:
        try:
            r = json.loads(p.read_text())
        except json.JSONDecodeError:
            continue
        if r.get("status") == "running" and not _alive(r.get("pid")):
            r["status"] = "interrupted"
        runs.append(r)
    return runs


def get_run(rid: str) -> dict | None:
    return next((r for r in list_runs(10_000) if r["id"] == rid), None)


def active_runs() -> list[dict]:
    return [r for r in list_runs(20) if r.get("status") == "running"]


def is_paused() -> bool:
    return (agents_dir() / "paused").exists()


def set_paused(paused: bool) -> None:
    f = agents_dir() / "paused"
    if paused:
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(core.now())
    else:
        f.unlink(missing_ok=True)


def heartbeat() -> None:
    f = agents_dir() / "heartbeat"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(f"{os.getpid()}")


def watcher_alive(max_age_s: int = 120) -> bool:
    """True if the watcher process wrote its heartbeat recently and is still running."""
    import time
    f = agents_dir() / "heartbeat"
    if not f.exists():
        return False
    return time.time() - f.stat().st_mtime < max_age_s and _alive(f.read_text().strip())


def _short(v, n=300) -> str:
    s = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
    return s if len(s) <= n else s[:n] + " …"


def _tool_summary(name: str, inp: dict) -> str:
    for key in ("command", "file_path", "pattern", "path", "url", "query", "skill", "description"):
        if key in inp:
            return _short(inp[key])
    return _short(inp)


def transcript(rid: str) -> list[dict]:
    """Compact, human-readable view of a stream-json log."""
    p = runs_dir() / f"{rid}.jsonl"
    if not p.exists():
        return []
    events = []
    for line in p.read_text(errors="replace").splitlines():
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            if line.strip():
                events.append({"kind": "raw", "text": line})
            continue
        typ = e.get("type")
        if typ == "assistant":
            for b in e.get("message", {}).get("content", []):
                if b.get("type") == "text" and b.get("text", "").strip():
                    events.append({"kind": "text", "text": b["text"]})
                elif b.get("type") == "tool_use":
                    events.append({"kind": "tool", "name": b.get("name", "?"),
                                   "text": _tool_summary(b.get("name", ""), b.get("input", {}) or {})})
        elif typ == "user":
            content = e.get("message", {}).get("content", [])
            for b in content if isinstance(content, list) else []:
                if b.get("type") == "tool_result" and b.get("is_error"):
                    c = b.get("content")
                    txt = c if isinstance(c, str) else " ".join(x.get("text", "") for x in c or [] if isinstance(x, dict))
                    events.append({"kind": "error", "text": _short(txt, 500)})
        elif typ == "result":
            events.append({"kind": "result", "text": e.get("result", "") or e.get("subtype", ""),
                           "cost": e.get("total_cost_usd"), "turns": e.get("num_turns"),
                           "duration_s": round((e.get("duration_ms") or 0) / 1000)})
    return events


def result_of(rid: str) -> dict:
    res = [e for e in transcript(rid) if e["kind"] == "result"]
    return res[-1] if res else {}
