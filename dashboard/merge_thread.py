"""Git merge driver for discussion threads (discussion/*.md, routed here by .gitattributes).

When two people (or their agents) change the same thread before syncing, git calls
    python dashboard/merge_thread.py <ancestor> <ours> <theirs>
and this writes the merged thread into <ours>:
  - comments: everything from both sides, without duplicates, in date order;
  - front matter: per field, the side that changed it; if both changed it, the side updated last;
  - description: the side that changed it.
Registered per clone by `./dash sync` / `./setup.sh` (git config merge.dash-thread.driver).
Exit 0 = merged; 1 = couldn't parse (git then reports a normal conflict).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dashboard import core  # noqa: E402


def _parse(text: str):
    meta, body = core.split_fm(text)
    parts = core.COMMENT_RE.split(body)
    comments = [(parts[i], parts[i + 1], parts[i + 2].strip()) for i in range(1, len(parts), 3)]
    return meta, parts[0].strip(), comments


def merge(base: str, ours: str, theirs: str) -> str:
    mo, ho, co = _parse(base) if base.strip() else ({}, "", [])
    ma, ha, ca = _parse(ours)
    mb, hb, cb = _parse(theirs)
    if not ma or not mb:
        raise ValueError("not a thread file (no front matter)")
    theirs_later = str(mb.get("updated", "")) > str(ma.get("updated", ""))
    meta = {}
    for k in list(ma) + [k for k in mb if k not in ma]:
        va, vb, vo = ma.get(k), mb.get(k), mo.get(k)
        if va == vb:
            v = va
        elif va == vo:
            v = vb
        elif vb == vo:
            v = va
        else:
            v = vb if theirs_later else va
        if v is not None:
            meta[k] = v
    meta["updated"] = max(str(ma.get("updated", "")), str(mb.get("updated", "")))
    if "id" in meta:
        meta["id"] = int(meta["id"])
    head = hb if ha == ho else ha
    seen, comments = set(), []
    for c in ca + cb:
        if c not in seen:
            seen.add(c)
            comments.append(c)
    comments.sort(key=lambda c: c[1])  # by date; same-minute comments keep their order
    body = head + "".join(f'\n\n<!-- comment author="{a}" date="{d}" -->\n{t}\n' for a, d, t in comments)
    return core.join_fm(meta, body)


def main(argv=None) -> int:
    base, ours, theirs = (argv or sys.argv[1:])[:3]
    try:
        merged = merge(Path(base).read_text(), Path(ours).read_text(), Path(theirs).read_text())
    except (OSError, ValueError) as e:
        print(f"merge_thread: {e}", file=sys.stderr)
        return 1
    Path(ours).write_text(merged)
    return 0


if __name__ == "__main__":
    sys.exit(main())
