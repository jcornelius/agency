"""
Slack bot: digger — Socket Mode app that listens for @digger mentions
and runs the prospect-search + email-finder pipeline in the background.

UX contract:
  1. First reply in thread = ack ("On it — searching for ...")
  2. Search done = pivot milestone ("Found N new companies. Now looking for emails...")
  3. Final message = summary ("Added N companies, M contacts, K company emails. Done.")

Only one pipeline runs at a time (global lock). Additional mentions queue up
and are processed FIFO. If the queue is long, the user is told so immediately.
"""

from __future__ import annotations

import logging
import os
import queue
import sys
import threading
import time
from dataclasses import dataclass
from typing import Any

from dotenv import load_dotenv
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

# Load .env BEFORE importing modules that read env (command_parser, runner).
load_dotenv()

import command_parser
import runner

log = logging.getLogger("digger")


# --- Config ---

def _csv_env(name: str) -> set[str]:
    raw = os.environ.get(name, "") or ""
    return {s.strip() for s in raw.split(",") if s.strip()}


ALLOWED_USERS = _csv_env("DIGGER_ALLOWED_USERS")
ALLOWED_CHANNELS = _csv_env("DIGGER_ALLOWED_CHANNELS")


def _is_allowed(user: str, channel: str) -> bool:
    if ALLOWED_USERS and user not in ALLOWED_USERS:
        return False
    if ALLOWED_CHANNELS and channel not in ALLOWED_CHANNELS:
        return False
    return True


# --- Work queue (single worker, FIFO) ---

@dataclass
class Job:
    channel: str
    thread_ts: str
    user: str
    text: str


_jobs: "queue.Queue[Job]" = queue.Queue()
_current_job_lock = threading.Lock()


# --- Slack app setup ---

app = App(token=os.environ["SLACK_BOT_TOKEN"])


@app.event("app_mention")
def handle_mention(event: dict[str, Any], say, client) -> None:
    """Acknowledge immediately; actual work happens in the background worker."""
    channel = event.get("channel", "")
    user = event.get("user", "")
    text = event.get("text", "")
    # Reply in the same thread as the mention; if not already in a thread, start one.
    thread_ts = event.get("thread_ts") or event.get("ts")

    if not _is_allowed(user, channel):
        log.info("Rejected mention from user=%s channel=%s", user, channel)
        say(
            thread_ts=thread_ts,
            text="Sorry, you're not authorized to use digger.",
        )
        return

    job = Job(channel=channel, thread_ts=thread_ts, user=user, text=text)
    qsize = _jobs.qsize()
    _jobs.put(job)

    if _current_job_lock.locked() or qsize > 0:
        say(
            thread_ts=thread_ts,
            text=f":hourglass_flowing_sand: Queued (position {qsize + 1}). I'll start as soon as the current run finishes.",
        )
    # else: the worker will send the first message after it parses the command.


def _post(channel: str, thread_ts: str, text: str) -> None:
    try:
        app.client.chat_postMessage(channel=channel, thread_ts=thread_ts, text=text)
    except Exception as e:
        log.exception("Slack post failed: %s", e)


# Special "admin" commands that bypass the LLM parser entirely.
# Keyed on the exact lowercase, whitespace-normalized text after the @mention.
_ADMIN_PULL    = {"pull", "update", "deploy", "git pull"}
_ADMIN_STATUS  = {"status", "ping", "health"}
_ADMIN_HELP    = {"help", "commands", "?"}


def _classify_admin(text: str) -> str | None:
    cleaned = " ".join(command_parser.strip_mention(text).strip().lower().split())
    if cleaned in _ADMIN_PULL:
        return "pull"
    if cleaned in _ADMIN_STATUS:
        return "status"
    if cleaned in _ADMIN_HELP:
        return "help"
    return None


def _handle_pull(job: Job) -> None:
    """Run update.sh, report output in Slack, trigger a detached reload."""
    import subprocess
    from pathlib import Path

    bot_dir = Path(__file__).resolve().parent
    update_script = bot_dir / "update.sh"

    _post(job.channel, job.thread_ts, ":arrow_down: Pulling from GitHub...")

    # First: pull only (no reload). We need to see what changed before deciding
    # whether to pip-install and restart.
    result = subprocess.run(
        ["bash", str(update_script)],
        capture_output=True, text=True, cwd=str(bot_dir),
    )
    out = (result.stdout + result.stderr).strip() or "(no output)"
    # Slack code fences for readability.
    _post(job.channel, job.thread_ts, f"```\n{out[:2800]}\n```")

    if result.returncode != 0:
        _post(job.channel, job.thread_ts, f":x: Pull failed (exit {result.returncode}).")
        return
    if "up to date" in out:
        return  # Nothing to reload.

    # Something changed. Reinstall deps if needed, then schedule a detached reload.
    if "requirements.txt" in out:
        _post(job.channel, job.thread_ts, ":package: requirements.txt changed — pip installing...")
        pip = subprocess.run(
            [str(bot_dir / ".venv" / "bin" / "pip"), "install", "-r",
             str(bot_dir / "requirements.txt"), "--quiet"],
            capture_output=True, text=True,
        )
        if pip.returncode != 0:
            _post(job.channel, job.thread_ts,
                  f":x: pip install failed:\n```\n{pip.stderr[:1500]}\n```")
            return

    _post(job.channel, job.thread_ts,
          ":arrows_counterclockwise: Restarting to pick up changes. Back in a few seconds.")

    # Spawn detached reloader: waits 1 second (so this message has time to post),
    # then unload+load. The `unload` kills this bot process; `load` starts a
    # fresh one.
    plist = "$HOME/Library/LaunchAgents/com.digger.bot.plist"
    script = (
        f"sleep 1; "
        f"launchctl unload {plist} 2>/dev/null; "
        f"launchctl load -w {plist}"
    )
    subprocess.Popen(
        ["bash", "-c", script],
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _handle_status(job: Job) -> None:
    import subprocess
    from pathlib import Path

    repo = Path(__file__).resolve().parent.parent.parent
    head = "unknown"
    try:
        head = subprocess.check_output(
            ["git", "-C", str(repo), "rev-parse", "--short", "HEAD"],
            text=True,
        ).strip()
    except Exception:
        pass

    qlen = _jobs.qsize()
    busy = "running a pipeline" if _current_job_lock.locked() else "idle"
    _post(
        job.channel, job.thread_ts,
        f":green_heart: digger alive @ `{head}` — currently {busy}, {qlen} job(s) queued.",
    )


def _handle_help(job: Job) -> None:
    _post(job.channel, job.thread_ts,
          "*digger commands*\n"
          "• `@digger find all <category> in <area>` — run prospect search\n"
          "• `@digger find contact info for <company> in <area>` — single-company lookup\n"
          "• `@digger pull` — pull latest code from GitHub and restart\n"
          "• `@digger status` — heartbeat / current queue\n"
          "• `@digger help` — this list")


def _process_job(job: Job) -> None:
    """Parse, run, report. Runs inside the worker thread holding the lock."""

    # 0. Admin commands bypass the LLM parser entirely.
    admin = _classify_admin(job.text)
    if admin == "pull":
        _handle_pull(job); return
    if admin == "status":
        _handle_status(job); return
    if admin == "help":
        _handle_help(job); return

    # 1. Parse with Claude.
    try:
        cmd = command_parser.parse(job.text)
    except command_parser.CommandParseError as e:
        _post(job.channel, job.thread_ts, f":warning: {e}")
        return
    except Exception:
        log.exception("Command parse failed")
        _post(job.channel, job.thread_ts, ":x: Couldn't parse the request — check the bot logs.")
        return

    # 2. Ack so the user knows we understood.
    ack = f":mag: {cmd.human_summary}" if cmd.human_summary else ":mag: On it..."
    _post(job.channel, job.thread_ts, ack)

    # 3. Define the heartbeat filter. We only forward milestone kinds to Slack.
    SLACK_KINDS = {
        "search_complete",
        "email_complete",
        "search_failed",
        "email_failed",
    }
    # Optional liveness ping if the search is taking a while with no milestone.
    last_post = [time.monotonic()]
    LIVENESS_SECS = 180

    def on_heartbeat(hb: runner.Heartbeat) -> None:
        log.info("heartbeat: %s — %s", hb.kind, hb.message)
        now = time.monotonic()
        if hb.kind == "search_complete":
            # Pivot message: combines the result + what's next.
            new = hb.data.get("new", 0)
            total = hb.data.get("total", 0)
            _post(
                job.channel, job.thread_ts,
                f":white_check_mark: Found {new} new companies ({total} total after dedup). "
                f"Now looking for emails...",
            )
            last_post[0] = now
        elif hb.kind == "email_complete":
            contacts = hb.data.get("contacts", 0)
            company_emails = hb.data.get("company_emails", 0)
            _post(
                job.channel, job.thread_ts,
                f":tada: Done. {contacts} new decision-maker contacts, "
                f"{company_emails} company emails added to HubSpot.",
            )
            last_post[0] = now
        elif hb.kind in {"search_failed", "email_failed"}:
            _post(job.channel, job.thread_ts, f":x: {hb.message}")
            last_post[0] = now
        else:
            # Silent heartbeat — but if we've been silent for a while, drop a
            # liveness ping so the user knows digger is still alive.
            if now - last_post[0] > LIVENESS_SECS:
                _post(job.channel, job.thread_ts, f":zzz: Still working — {hb.message}")
                last_post[0] = now

    # 4. Run the full pipeline.
    try:
        runner.run_full_pipeline(cmd, on_heartbeat)
    except Exception as e:
        log.exception("Pipeline crashed")
        _post(job.channel, job.thread_ts, f":x: Pipeline crashed: `{e}`. Check the bot logs.")


def _worker_loop() -> None:
    log.info("Worker thread started.")
    while True:
        job = _jobs.get()
        log.info("Picked up job: channel=%s thread=%s user=%s text=%r",
                 job.channel, job.thread_ts, job.user, job.text)
        with _current_job_lock:
            try:
                _process_job(job)
            except Exception:
                log.exception("Unexpected worker error for job %r", job)
            finally:
                _jobs.task_done()


def main() -> None:
    level = os.environ.get("DIGGER_LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stdout,
    )

    # Sanity checks up front so we fail loudly rather than mid-conversation.
    required = [
        "SLACK_BOT_TOKEN", "SLACK_APP_TOKEN",
        "ANTHROPIC_API_KEY",
        "BRAVE_API_KEY", "GOOGLE_PLACES_API_KEY",
        "HUBSPOT_PRIVATE_APP_TOKEN", "HUNTER_API_KEY",
    ]
    missing = [k for k in required if not os.environ.get(k)]
    if missing:
        log.error("Missing required env vars: %s", ", ".join(missing))
        log.error("Copy .env.example → .env and fill in values.")
        sys.exit(2)

    log.info("Scripts dir: %s", runner.SCRIPTS_DIR)
    log.info("Research dir: %s", runner.RESEARCH_DIR)
    log.info("Brief: %s", runner.brief_path())
    if ALLOWED_USERS:
        log.info("Restricted to users: %s", ", ".join(sorted(ALLOWED_USERS)))
    if ALLOWED_CHANNELS:
        log.info("Restricted to channels: %s", ", ".join(sorted(ALLOWED_CHANNELS)))

    worker = threading.Thread(target=_worker_loop, name="digger-worker", daemon=True)
    worker.start()

    handler = SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"])
    log.info("Connecting to Slack via Socket Mode...")
    handler.start()  # blocks


if __name__ == "__main__":
    main()
