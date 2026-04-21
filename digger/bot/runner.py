"""
Subprocess runner for prospect-search.py and email-finder.py.

Responsibilities:
  - Build correct CLI args from a parsed Command
  - Launch the script as a subprocess with the right env
  - Stream stdout line-by-line, emitting Heartbeat events to a callback
  - Accumulate final counts for the summary

The bot (slack_app.py) is responsible for deciding which heartbeats
actually get posted to Slack (throttling, formatting).
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from command_parser import Command

log = logging.getLogger(__name__)

# --- Resolve paths (overridable via env for flexibility) ---

_BOT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _BOT_DIR.parent  # e.g. /Users/jc/Nest/digger

SCRIPTS_DIR = Path(os.environ.get("DIGGER_SCRIPTS_DIR") or (_REPO_ROOT / "scripts"))
RESEARCH_DIR = Path(os.environ.get("DIGGER_RESEARCH_DIR") or (_REPO_ROOT / "research"))


def _find_brief(root: Path) -> Path:
    """Pick a sensible default brief file if DIGGER_BRIEF_PATH isn't set."""
    candidates = [
        root / "briefs" / "square-pos-research.md",
        root / "square_pos_prospect_research.md",
    ]
    for c in candidates:
        if c.exists():
            return c
    # Return the first candidate even if missing, so the error message is useful.
    return candidates[0]


def brief_path() -> Path:
    override = os.environ.get("DIGGER_BRIEF_PATH")
    if override:
        return Path(override)
    return _find_brief(_REPO_ROOT)


# --- Heartbeat event stream ---

@dataclass
class Heartbeat:
    """A structured progress event emitted while a script runs."""
    kind: str                           # e.g. "search_start", "search_complete", "email_complete"
    message: str                        # human-readable one-liner
    data: dict[str, Any] = field(default_factory=dict)


HeartbeatCallback = Callable[[Heartbeat], None]


# --- Script output patterns ---
# These mirror what prospect-search.py and email-finder.py print (see TOOLS.md).

_RE_SEARCH_BASELINE = re.compile(r"^CSV baseline: (\d+) rows")
_RE_SEARCH_TERM = re.compile(r'^--- Searching "([^"]+)" \[(\d+)/(\d+)\]')
_RE_SEARCH_HEARTBEAT = re.compile(r"(\d+)\s+entries inspected,\s+(\d+)\s+new matches")
_RE_SEARCH_COMPLETE = re.compile(r"=== COMPLETE: (\d+) new, (\d+) total")

_RE_EMAIL_COUNT = re.compile(r"Companies needing email enrichment:\s*(\d+)")
_RE_EMAIL_ROW = re.compile(r"---\s+\[(\d+)/(\d+)\]\s+(.+?)\s+---")
_RE_EMAIL_HEARTBEAT = re.compile(r"(\d+)/(\d+)\s+processed,\s+(\d+)\s+emails found")
_RE_EMAIL_COMPLETE = re.compile(
    r"=== COMPLETE:\s*(\d+)\s+contacts\s*\+\s*(\d+)\s+company emails"
)


# --- CLI builders ---

def _slugify_area(area: str) -> str:
    """'Blue Ridge GA' -> 'blue-ridge-ga' (but drop trailing state code for filenames)."""
    s = re.sub(r"[^A-Za-z0-9]+", "-", area).strip("-").lower()
    # Trim trailing state suffix like "-ga" for cleaner filenames.
    s = re.sub(r"-(ga|ny|ca|tx|fl|pa|oh|nc|va|tn|sc|al|ms|la|ky|wv|in|mi|il)$", "", s)
    return s or "unknown"


def build_prospect_search_args(cmd: Command) -> tuple[list[str], Path]:
    """Return (argv, csv_path) for invoking prospect-search.py."""
    if cmd.intent == "company_search":
        # Narrow keyword: just the company name itself.
        keywords = [cmd.company_name or ""] if cmd.company_name else cmd.keywords
    else:
        keywords = cmd.keywords

    primary_area = cmd.areas[0] if cmd.areas else "unknown"
    slug = _slugify_area(primary_area)
    csv_path = RESEARCH_DIR / f"square-pos-{slug}.csv"
    RESEARCH_DIR.mkdir(parents=True, exist_ok=True)

    argv = [
        sys.executable, "-u", str(SCRIPTS_DIR / "prospect-search.py"),
        str(brief_path()),
        "--csv", str(csv_path),
        "--sync-to-hubspot",
        "--keywords", ",".join(keywords),
        "--areas", ",".join(cmd.areas),
    ]
    return argv, csv_path


def build_email_finder_args() -> list[str]:
    return [
        sys.executable, "-u", str(SCRIPTS_DIR / "email-finder.py"),
        "--from-hubspot",
    ]


# --- Subprocess runner ---

def _parent_env() -> dict[str, str]:
    """Child processes inherit our env; python-dotenv will have already populated
    BRAVE_API_KEY, HUBSPOT_PRIVATE_APP_TOKEN, GOOGLE_PLACES_API_KEY, HUNTER_API_KEY
    from .env into os.environ."""
    return os.environ.copy()


def _stream(argv: list[str], log_path: Path) -> subprocess.Popen[str]:
    log.info("Launching: %s", " ".join(argv))
    log_path.parent.mkdir(parents=True, exist_ok=True)
    return subprocess.Popen(
        argv,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=1,
        text=True,
        env=_parent_env(),
        cwd=str(SCRIPTS_DIR),  # script imports sibling hubspot_client.py
    )


@dataclass
class ProspectResult:
    exit_code: int
    new_companies: int = 0
    total_companies: int = 0
    csv_path: Path | None = None


def run_prospect_search(
    cmd: Command,
    on_heartbeat: HeartbeatCallback,
    *,
    log_path: Path | None = None,
) -> ProspectResult:
    argv, csv_path = build_prospect_search_args(cmd)
    log_path = log_path or (_BOT_DIR / "logs" / "prospect-search.log")

    on_heartbeat(Heartbeat(
        kind="search_start",
        message=f"Searching {', '.join(cmd.keywords)} in {', '.join(cmd.areas)}...",
        data={"keywords": cmd.keywords, "areas": cmd.areas, "csv": str(csv_path)},
    ))

    result = ProspectResult(exit_code=-1, csv_path=csv_path)
    with _stream(argv, log_path) as proc, log_path.open("a", encoding="utf-8") as logf:
        logf.write(f"\n\n=== {argv!r} ===\n")
        assert proc.stdout is not None
        for line in proc.stdout:
            logf.write(line)
            logf.flush()
            line = line.rstrip()

            m = _RE_SEARCH_COMPLETE.search(line)
            if m:
                result.new_companies = int(m.group(1))
                result.total_companies = int(m.group(2))
                on_heartbeat(Heartbeat(
                    kind="search_complete",
                    message=f"Search done: {result.new_companies} new, {result.total_companies} total.",
                    data={"new": result.new_companies, "total": result.total_companies},
                ))
                continue

            m = _RE_SEARCH_HEARTBEAT.search(line)
            if m:
                on_heartbeat(Heartbeat(
                    kind="search_progress",
                    message=f"{m.group(2)} new matches found so far.",
                    data={"inspected": int(m.group(1)), "new": int(m.group(2))},
                ))
                continue

            m = _RE_SEARCH_TERM.search(line)
            if m:
                on_heartbeat(Heartbeat(
                    kind="search_term",
                    message=f'Searching "{m.group(1)}" [{m.group(2)}/{m.group(3)}]',
                    data={"term": m.group(1), "i": int(m.group(2)), "n": int(m.group(3))},
                ))
                continue

            m = _RE_SEARCH_BASELINE.search(line)
            if m:
                on_heartbeat(Heartbeat(
                    kind="search_baseline",
                    message=f"Starting (CSV has {m.group(1)} existing rows).",
                    data={"baseline": int(m.group(1))},
                ))
                continue

        result.exit_code = proc.wait()
    log.info("prospect-search exit=%d new=%d total=%d",
             result.exit_code, result.new_companies, result.total_companies)
    return result


@dataclass
class EmailResult:
    exit_code: int
    to_enrich: int = 0
    new_contacts: int = 0
    company_emails: int = 0


def run_email_finder(
    on_heartbeat: HeartbeatCallback,
    *,
    log_path: Path | None = None,
) -> EmailResult:
    argv = build_email_finder_args()
    log_path = log_path or (_BOT_DIR / "logs" / "email-finder.log")

    on_heartbeat(Heartbeat(
        kind="email_start",
        message="Looking for emails...",
        data={},
    ))

    result = EmailResult(exit_code=-1)
    with _stream(argv, log_path) as proc, log_path.open("a", encoding="utf-8") as logf:
        logf.write(f"\n\n=== {argv!r} ===\n")
        assert proc.stdout is not None
        for line in proc.stdout:
            logf.write(line)
            logf.flush()
            line = line.rstrip()

            m = _RE_EMAIL_COMPLETE.search(line)
            if m:
                result.new_contacts = int(m.group(1))
                result.company_emails = int(m.group(2))
                on_heartbeat(Heartbeat(
                    kind="email_complete",
                    message=f"{result.new_contacts} new contacts, {result.company_emails} company emails added.",
                    data={"contacts": result.new_contacts, "company_emails": result.company_emails},
                ))
                continue

            m = _RE_EMAIL_HEARTBEAT.search(line)
            if m:
                on_heartbeat(Heartbeat(
                    kind="email_progress",
                    message=f"{m.group(1)}/{m.group(2)} processed, {m.group(3)} emails found.",
                    data={
                        "processed": int(m.group(1)),
                        "total": int(m.group(2)),
                        "found": int(m.group(3)),
                    },
                ))
                continue

            m = _RE_EMAIL_COUNT.search(line)
            if m:
                result.to_enrich = int(m.group(1))
                on_heartbeat(Heartbeat(
                    kind="email_count",
                    message=f"{result.to_enrich} companies need email enrichment.",
                    data={"count": result.to_enrich},
                ))
                continue

        result.exit_code = proc.wait()
    log.info("email-finder exit=%d contacts=%d company_emails=%d",
             result.exit_code, result.new_contacts, result.company_emails)
    return result


def run_full_pipeline(
    cmd: Command,
    on_heartbeat: HeartbeatCallback,
) -> tuple[ProspectResult, EmailResult]:
    """Run prospect-search, then email-finder. Bubbles heartbeats to the callback."""
    prospect = run_prospect_search(cmd, on_heartbeat)
    if prospect.exit_code != 0:
        on_heartbeat(Heartbeat(
            kind="search_failed",
            message=f"Search failed (exit code {prospect.exit_code}). Check logs.",
            data={"exit_code": prospect.exit_code},
        ))
        return prospect, EmailResult(exit_code=-999)

    email = run_email_finder(on_heartbeat)
    if email.exit_code != 0:
        on_heartbeat(Heartbeat(
            kind="email_failed",
            message=f"Email finder failed (exit code {email.exit_code}). Check logs.",
            data={"exit_code": email.exit_code},
        ))
    return prospect, email
