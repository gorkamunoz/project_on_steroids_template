"""`./dash` — command-line access to discussion, labs and wiki (works without the server).

Run `./dash -h` or `./dash <command> -h` for usage.
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import sys
import textwrap

from . import core


def _body(args) -> str:
    if getattr(args, "body_file", None):
        return open(args.body_file).read()
    if getattr(args, "body", None) == "-":
        return sys.stdin.read()
    return args.body or ""


def _author(args) -> str:
    a = args.author or os.environ.get("DASH_AUTHOR")
    if not a:
        sys.exit("error: pass --author agent:<name> (or set DASH_AUTHOR)")
    return a


def _row(t) -> str:
    w = f" [waiting on {t['waiting_on']}]" if t["waiting_on"] != "none" else ""
    return f"#{t['id']:<4} {t['type']:<9} {t['status']:<12} {t['title']}{w}  ({t['author']}, {t['updated']})"


def cmd_inbox(args):
    ts = [t for t in core.list_threads() if t["waiting_on"] == "agents"]
    print(f"{len(ts)} open thread(s) waiting on agents:" if ts else "Inbox empty: nothing waiting on agents.")
    for t in ts:
        print("  " + _row(t))
    mine = [t for t in core.list_threads() if t["waiting_on"] not in core.WAITING_SPECIAL]
    if mine:
        print(f"\n{len(mine)} thread(s) waiting on a person (don't act on these until answered):")
        for t in mine:
            print("  " + _row(t))


def cmd_threads(args):
    for t in core.list_threads():
        if args.all or t["status"] in ("open", "in-progress"):
            if (not args.type or t["type"] == args.type) and (not args.waiting_on or t["waiting_on"] == args.waiting_on):
                print(_row(t))


def cmd_show(args):
    t = core.get_thread(args.id)
    if not t:
        sys.exit(f"thread {args.id} not found")
    print(f"#{t['id']} {t['title']}\n{t['type']} · {t['status']} · waiting on {t['waiting_on']} · by {t['author']} · {t['created']}"
          f" · model {core.thread_model(t)}")
    if t["links"]:
        print("links: " + ", ".join(t["links"]))
    print(f"file: {t['path']}\n\n{t['body']}")
    for c in t["comments"]:
        print(f"\n--- {c['author']} · {c['date']}\n{c['body']}")


def cmd_new(args):
    t = core.create_thread(args.title, args.type, _author(args), _body(args), args.link, args.label, args.waiting_on)
    print(f"created #{t['id']} ({t['path']}) waiting on {t['waiting_on']}")


def cmd_comment(args):
    t = core.add_comment(args.id, _author(args), _body(args), args.status, args.waiting_on)
    print(f"#{t['id']} updated: status={t['status']} waiting_on={t['waiting_on']}")


def cmd_lab_new(args):
    from . import sync
    # Reserve the number with the team: pull first, push the new lab right away, so a lab folder never
    # has to be renumbered while a job writes into its outputs/.
    shared = sync.enabled()
    if shared:
        sync.safe_sync()
    p = core.create_lab(args.title, _author(args), args.parents, args.hypothesis or "", args.tags)
    if shared and sync.commit([core.rel(p)], f"{core.lab_code(int(p.name.split('-')[0]))}: created ({p.name})"):
        res = sync.safe_sync()
        new = res.get("mapping", {}).get(("lab", int(p.name.split("-")[0])))
        if new:  # someone pushed the same number in the last seconds
            p = core.lab_dir(new)
    print(f"created {core.rel(p)}/  (lab.yaml, report.md, figures/)")


def cmd_labs(args):
    for l in core.list_labs():
        par = ",".join(core.lab_code(p) for p in l["parents"]) or "root"
        print(f"{l['code']}  {l['status']:<10} {l['title']}  <- {par}" + (f"\n        {l['conclusion']}" if l["conclusion"] else ""))


def cmd_wiki_new(args):
    p = core.create_wiki(args.slug, args.title, _author(args))
    print(f"created {core.rel(p)}")


def cmd_search(args):
    for r in core.search(" ".join(args.query)):
        print(f"[{r['kind']}] {r['title']}  ->  {r['url']}")
        if r["snippet"]:
            print(textwrap.indent(textwrap.shorten(r["snippet"], 160), "    "))


def cmd_pending(args):
    ts = core.pending_threads()
    print(f"{len(ts)} thread(s) the watcher would launch an agent for:" if ts else "Nothing pending.")
    for t in ts:
        print(f"  {_row(t)}  <- {t['trigger']}")


def cmd_snooze(args):
    if args.until:
        until = args.until
    else:
        delta = dt.timedelta(hours=args.hours or 0, minutes=args.minutes or 0)
        if not delta:
            sys.exit("error: give --hours, --minutes or --until")
        until = (dt.datetime.now() + delta).strftime("%Y-%m-%d %H:%M")
    t = core.snooze(args.id, _author(args), until, _body(args))
    print(f"#{t['id']} snoozed until {until}; an agent will be relaunched on it then")


def cmd_team(args):
    if args.refresh and core.refresh_team() is None:
        print("could not reach GitHub (is `gh` installed and logged in, and is there a GitHub remote?)")
    info = core.team_info()
    src = f"GitHub collaborators, fetched {info['fetched']}" if info["source"] == "github" \
        else "you + people who have written in threads; optional: `gh auth login`, then `./dash team --refresh`"
    print(f"you: {core.ME}\nteam ({src}):")
    for p in info["people"]:
        print(f"  {p}")


def cmd_agents(args):
    from . import agents
    if args.pause or args.resume:
        agents.set_paused(bool(args.pause))
    print("watcher: PAUSED" if agents.is_paused() else "watcher: active")
    for r in agents.list_runs(args.n):
        cost = f"${r['cost_usd']:.2f}" if isinstance(r.get("cost_usd"), (int, float)) else ""
        print(f"  {r['id']}  {r['status']:<11} #{r['thread']} {r['title'][:50]}  {cost}  session={r['session_id']}")


def cmd_notes(args):
    from . import notes
    if args.action == "init":
        print(f"created {core.rel(notes.init())}/ from skills/notes/template")
    elif args.action == "build":
        r = notes.build()
        for p in r["problems"]:
            print("  " + p)
        print(f"{'✓ built' if r['ok'] else '✗ build FAILED'}: {r['pdf'] or '-'} ({r['pages'] or '?'} pages)"
              + (f"  view: http://localhost:{core.PORT}/notes" if r["ok"] else ""))
        sys.exit(0 if r["ok"] else 1)
    elif args.action == "release":
        if not args.message:
            sys.exit("error: -m 'one-line summary' is required")
        from . import sync
        if not args.no_git:
            sync.safe_sync()  # take the next version number after the team's latest release
        r = notes.release(args.message, _author(args), args.change, args.thread or "", use_git=not args.no_git)
        if not args.no_git:
            sync.safe_sync()  # push the commit and its tag
        for w in r["warnings"]:
            print("  " + w)
        print(f"released {r['version']} ({r['pages']} pages) in {r['dir']}/ · {r['diff'] or 'first version, no diff'}"
              f" · {r['git']}\n  view: http://localhost:{core.PORT}/notes/{r['version']}")
    else:
        d = notes.draft_info()
        if d:
            print(f"draft   {d['built']}  {d['pages']} pages  {d['pdf']}")
        for v in notes.list_versions():
            print(f"{v['version']}    {v['date']}  {v['pages']} pages  {v['summary']}")


def cmd_sync(args):
    from . import sync
    try:
        r = sync.sync()
    except sync.SyncError as e:
        sys.exit(f"sync problem: {e}")
    for n in r.get("notes", []):
        print("  " + n)
    held = sync.status()["held"]
    print("✓ synced with the team" + (f" ({held} message(s) held until your agent starts on them)" if held else ""))
    n = sync.uncommitted(limit=0)["count"]
    if n:
        print(f"  {n} file(s) you changed are not committed, so not shared: commit them (dashboard → '{n} to commit')")


def cmd_examples(args):
    if not args.remove:
        sys.exit("usage: ./dash examples --remove   (deletes the template's example content)")
    for p in core.remove_examples():
        print(f"  removed {p}")


def cmd_merge_thread(args):
    from . import merge_thread
    sys.exit(merge_thread.main([args.base, args.ours, args.theirs]))


def cmd_check(args):
    problems = core.check()
    for p in problems:
        print("✗ " + p)
    print("✓ all conventions OK" if not problems else f"\n{len(problems)} problem(s)")
    sys.exit(1 if problems else 0)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="dash", description="Project dashboard CLI (discussion, labs, wiki).")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def body_opts(p):
        p.add_argument("--body", "-b", help="markdown text; '-' reads it from stdin (use with a heredoc)")
        p.add_argument("--body-file", help="read markdown body from a file")
        p.add_argument("--author", "-a", help="'agent:<name>' (or env DASH_AUTHOR)")

    sub.add_parser("inbox", help="threads waiting on agents (start every session with this)").set_defaults(fn=cmd_inbox)

    p = sub.add_parser("threads", help="list open threads")
    p.add_argument("--all", action="store_true", help="include resolved/closed")
    p.add_argument("--type", choices=core.THREAD_TYPES)
    p.add_argument("--waiting-on", help="agents | none | <username> | human (= the person who asked)")
    p.set_defaults(fn=cmd_threads)

    p = sub.add_parser("show", help="print a thread with all comments")
    p.add_argument("id", type=int)
    p.set_defaults(fn=cmd_show)

    p = sub.add_parser("new", help="open a new thread")
    p.add_argument("--type", "-t", required=True, choices=core.THREAD_TYPES)
    p.add_argument("--title", required=True)
    p.add_argument("--link", "-l", action="append", help="lab:3, wiki:some-concept, thread:2, ref:key (repeatable)")
    p.add_argument("--label", action="append")
    p.add_argument("--waiting-on", help="agents | none | <username> | human (= the person whose message started this run). Default for agents: human for decision/question, else none")
    body_opts(p)
    p.set_defaults(fn=cmd_new)

    p = sub.add_parser("comment", help="reply to a thread and/or change its status")
    p.add_argument("id", type=int)
    p.add_argument("--status", "-s", choices=core.THREAD_STATUSES)
    p.add_argument("--waiting-on", help="agents | none | <username> | human (= the person who asked)")
    body_opts(p)
    p.set_defaults(fn=cmd_comment)

    sub.add_parser("labs", help="list labs with lineage").set_defaults(fn=cmd_labs)

    p = sub.add_parser("lab-new", help="scaffold labs/NNN-slug/ with lab.yaml + report.md")
    p.add_argument("--title", required=True)
    p.add_argument("--parents", "-p", help="comma-separated parent lab ids, e.g. 3,5")
    p.add_argument("--hypothesis")
    p.add_argument("--tags")
    p.add_argument("--author", "-a")
    p.set_defaults(fn=cmd_lab_new)

    p = sub.add_parser("wiki-new", help="scaffold wiki/<slug>.md")
    p.add_argument("slug")
    p.add_argument("--title", required=True)
    p.add_argument("--author", "-a")
    p.set_defaults(fn=cmd_wiki_new)

    p = sub.add_parser("search", help="full-text search over wiki, labs, threads, refs, skills")
    p.add_argument("query", nargs="+")
    p.set_defaults(fn=cmd_search)

    sub.add_parser("pending", help="threads the agent watcher will pick up next").set_defaults(fn=cmd_pending)

    p = sub.add_parser("snooze", help="park a thread; the watcher relaunches an agent on it later")
    p.add_argument("id", type=int)
    p.add_argument("--hours", type=float)
    p.add_argument("--minutes", type=float)
    p.add_argument("--until", help="'YYYY-MM-DD HH:MM'")
    body_opts(p)
    p.set_defaults(fn=cmd_snooze)

    p = sub.add_parser("team", help="who you are (local.yaml) and the team (the repo's GitHub collaborators)")
    p.add_argument("--refresh", action="store_true", help="reload the collaborator list from GitHub")
    p.set_defaults(fn=cmd_team)

    p = sub.add_parser("agents", help="recent autonomous agent runs; --pause / --resume the watcher")
    p.add_argument("--pause", action="store_true")
    p.add_argument("--resume", action="store_true")
    p.add_argument("-n", type=int, default=15)
    p.set_defaults(fn=cmd_agents)

    p = sub.add_parser("notes", help="working-notes PDF: init | build (draft) | release (tagged version) | list")
    p.add_argument("action", choices=["init", "build", "release", "list"])
    p.add_argument("-m", "--message", help="release: one-line summary of this version")
    p.add_argument("-c", "--change", action="append", help="release: one item of the changelog (repeatable)")
    p.add_argument("--thread", help="release: thread id that asked for this version")
    p.add_argument("--no-git", action="store_true", help="release: don't commit/tag")
    p.add_argument("--author", "-a")
    p.set_defaults(fn=cmd_notes)

    sub.add_parser("check", help="validate conventions: broken links, bad lab parents, formats").set_defaults(fn=cmd_check)

    sub.add_parser("sync", help="pull the team's changes, push yours (also automatic)").set_defaults(fn=cmd_sync)

    p = sub.add_parser("examples", help="--remove: delete the template's example content (once, in a new project)")
    p.add_argument("--remove", action="store_true")
    p.set_defaults(fn=cmd_examples)

    p = sub.add_parser("merge-thread", help=argparse.SUPPRESS)  # git merge driver (see dashboard/merge_thread.py)
    p.add_argument("base")
    p.add_argument("ours")
    p.add_argument("theirs")
    p.set_defaults(fn=cmd_merge_thread)

    args = ap.parse_args(argv)
    try:
        args.fn(args)
    except (ValueError, KeyError) as e:
        sys.exit(f"error: {e}")


if __name__ == "__main__":
    main()
