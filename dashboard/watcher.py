"""Always-on agent watcher: launches a headless Claude Code agent for each thread that needs one.

    ./run_agents.sh            # foreground
    ./run_agents.sh install    # systemd user service (always on)

Each person runs their own watcher, which only serves that person (`me` in local.yaml): a thread needs
my agent when it is waiting on agents AND (I wrote its latest entry OR my agent's snooze has expired).
Runs are sequential (agents commit to the same working tree). If an agent ends without touching the
thread, the watcher hands the thread back to the person who asked, so it never loops.

Model: the thread's `model` field (picked in the dashboard), else the first entry of agent_models in project.yaml.
Env knobs: AGENT_POLL_S (30), AGENT_TIMEOUT_H (6), AGENT_BUDGET_USD, AGENT_PERMISSION_MODE (auto),
           AGENT_ALLOW_MCP (set 1 to let agents use your MCP connectors), CLAUDE_BIN (claude).
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

from . import agents, core

POLL_S = int(os.environ.get("AGENT_POLL_S", "30"))
TIMEOUT_S = float(os.environ.get("AGENT_TIMEOUT_H", "6")) * 3600
AUTHOR = "agent:worker"
WATCHER = "agent:watcher"
PROMPT = Path(__file__).parent / "agent_prompt.md"


def log(msg: str) -> None:
    print(f"[{core.now()}] {msg}", flush=True)


def claude_bin() -> str:
    b = os.environ.get("CLAUDE_BIN") or shutil.which("claude") or str(Path.home() / ".local/bin/claude")
    return b


def build_cmd(prompt: str, session_id: str, tid: int, model: str) -> list[str]:
    cmd = [claude_bin(), "-p", prompt, "--model", model,
           "--permission-mode", os.environ.get("AGENT_PERMISSION_MODE", "auto"),
           "--output-format", "stream-json", "--verbose",
           "--session-id", session_id, "--name", f"thread #{tid}"]
    if os.environ.get("AGENT_ALLOW_MCP") != "1":
        cmd += ["--strict-mcp-config"]  # skip personal claude.ai connectors (Drive, etc.): not needed, cost tokens
    if os.environ.get("AGENT_BUDGET_USD"):
        cmd += ["--max-budget-usd", os.environ["AGENT_BUDGET_USD"]]
    return cmd


def agent_env(requester: str) -> dict:
    env = dict(os.environ)
    env["DASH_REQUESTER"] = requester  # `--waiting-on human` in the agent = the person who asked
    env_bin = str(Path(sys.executable).parent)  # the project's conda env
    env["PATH"] = os.pathsep.join([env_bin, str(Path.home() / ".local/bin"), env.get("PATH", "/usr/bin:/bin")])
    env["CONDA_DEFAULT_ENV"] = core.CONFIG.get("conda_env", "")
    env["DASH_AUTHOR"] = AUTHOR
    env["GIT_AUTHOR_NAME"] = f"Claude agent ({core.PROJECT_NAME})"
    env["GIT_AUTHOR_EMAIL"] = "noreply@anthropic.com"
    return env


def handle(t: dict) -> dict:
    tid = t["id"]
    rid = dt.datetime.now().strftime("%Y%m%d-%H%M%S") + f"-t{tid}"
    sid = str(uuid.uuid4())
    who = core.last_human(t) or core.ME
    core.set_meta(tid, wake_at=None, run_by=core.ME)  # this machine's agent now handles the thread
    prompt = (PROMPT.read_text().replace("{tid}", str(tid)).replace("{title}", t["title"])
              .replace("{trigger}", t.get("trigger", "")).replace("{author}", AUTHOR)
              .replace("{human}", who))
    model = core.thread_model(t)
    run = {"id": rid, "thread": tid, "title": t["title"], "trigger": t.get("trigger", ""), "model": model, "requester": who,
           "session_id": sid, "started": core.now(), "status": "running", "n_comments": len(t["comments"])}
    logf = agents.runs_dir() / f"{rid}.jsonl"
    log(f"run {rid}: thread #{tid} ({run['trigger']}, model {model})")
    with open(logf, "w") as out:
        try:
            proc = subprocess.Popen(build_cmd(prompt, sid, tid, model), cwd=core.ROOT, stdout=out,
                                    stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, env=agent_env(who))
        except OSError as e:
            run.update(status="failed", ended=core.now(), error=str(e))
            agents.save_run(run)
            core.add_comment(tid, WATCHER, f"Could not start an agent: `{e}`", waiting_on=who)
            return run
        run["pid"] = proc.pid
        agents.save_run(run)
        try:
            deadline = time.time() + TIMEOUT_S
            while True:  # keep the heartbeat fresh during long runs
                agents.heartbeat()
                try:
                    rc = proc.wait(timeout=5)
                    break
                except subprocess.TimeoutExpired:
                    if time.time() > deadline:
                        raise
        except subprocess.TimeoutExpired:
            proc.terminate()
            try:
                proc.wait(timeout=60)
            except subprocess.TimeoutExpired:
                proc.kill()
            rc = "timeout"
    res = agents.result_of(rid)
    run.update(status="done" if rc == 0 else ("timeout" if rc == "timeout" else "failed"), exit=rc,
               ended=core.now(), cost_usd=res.get("cost"), turns=res.get("turns"),
               summary=(res.get("text") or "")[:500])
    agents.save_run(run)
    log(f"run {rid}: {run['status']} (exit {rc}, cost {run['cost_usd']})")

    after = core.get_thread(tid)
    if after and len(after["comments"]) == len(t["comments"]):  # agent never wrote on the thread
        core.add_comment(tid, WATCHER,
                         f"The agent run [{rid}](/agents/{rid}) ended (**{run['status']}**) without replying "
                         f"on this thread, so I'm handing it back to you. Reply to retry.",
                         waiting_on=who)
    return run


def mark_interrupted() -> None:
    for r in agents.list_runs(50):
        if r.get("status") == "interrupted":
            r["ended"] = r.get("ended") or core.now()
            agents.save_run(r)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--once", action="store_true", help="handle at most one pending thread, then exit")
    ap.add_argument("--dry-run", action="store_true", help="only print what would be launched")
    args = ap.parse_args(argv)
    mark_interrupted()
    log(f"watcher started (root={core.ROOT}, poll={POLL_S}s, claude={claude_bin()})")
    while True:
        agents.heartbeat()
        pending = [] if agents.is_paused() else core.pending_threads()
        if args.dry_run:
            for t in pending:
                print(f"would launch: #{t['id']} {t['title']} ({t['trigger']})")
            return
        if pending:
            handle(pending[0])
            if args.once:
                return
            continue
        if args.once:
            log("nothing pending" + (" (paused)" if agents.is_paused() else ""))
            return
        time.sleep(POLL_S)


if __name__ == "__main__":
    main()
