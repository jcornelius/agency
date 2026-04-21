"""Offline smoke test — no Slack connection, no API calls, no subprocess launch.

Verifies:
  1. All modules import cleanly.
  2. Heartbeat regexes match the exact example lines from TOOLS.md.
  3. build_prospect_search_args produces a sensible argv for both intents.
  4. _slugify_area works for common inputs.
  5. command_parser.strip_mention strips Slack-style <@U...> prefixes.
  6. The patched scripts still parse as valid Python.
"""

from __future__ import annotations

import ast
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


# --- 1. Imports ---
print("[1] Importing modules...")
# Set fake env so imports that touch env don't explode.
os.environ.setdefault("ANTHROPIC_API_KEY", "fake")
os.environ.setdefault("SLACK_BOT_TOKEN", "xoxb-fake")
os.environ.setdefault("SLACK_APP_TOKEN", "xapp-fake")

import command_parser  # noqa: E402
import runner          # noqa: E402

print("    ok")


# --- 2. Heartbeat regex coverage ---
print("[2] Checking heartbeat regex patterns against TOOLS.md samples...")

# Each entry: (pattern, sample line, tuple of expected groups in order).
samples = [
    (runner._RE_SEARCH_BASELINE,  "CSV baseline: 117 rows",                            ("117",)),
    (runner._RE_SEARCH_TERM,      '--- Searching "coffee Athens GA" [3/12] ---',       ("coffee Athens GA", "3", "12")),
    (runner._RE_SEARCH_HEARTBEAT, "   ... 40 entries inspected, 7 new matches ...",    ("40", "7")),
    (runner._RE_SEARCH_COMPLETE,  "=== COMPLETE: 23 new, 147 total ===",               ("23", "147")),
    (runner._RE_EMAIL_COUNT,      "Companies needing email enrichment: 32",            ("32",)),
    (runner._RE_EMAIL_ROW,        "--- [5/32] Acme Coffee ---",                        ("5", "32", "Acme Coffee")),
    (runner._RE_EMAIL_HEARTBEAT,  "   ... 10/32 processed, 4 emails found ...",        ("10", "32", "4")),
    (runner._RE_EMAIL_COMPLETE,   "=== COMPLETE: 8 contacts + 12 company emails in HubSpot ===", ("8", "12")),
]

for rx, line, expected in samples:
    m = rx.search(line)
    assert m, f"pattern {rx.pattern!r} did not match sample: {line!r}"
    got = tuple(m.groups())
    assert got == expected, (
        f"pattern {rx.pattern!r} groups={got!r} expected {expected!r} (line: {line!r})"
    )
print(f"    ok ({len(samples)} patterns)")


# --- 3. build_prospect_search_args ---
print("[3] build_prospect_search_args...")
from command_parser import Command  # noqa: E402

area_cmd = Command(
    intent="area_search",
    keywords=["pizza", "pizzeria"],
    areas=["Athens GA", "Watkinsville GA"],
    human_summary="Searching for pizza in Athens GA and Watkinsville GA.",
)
argv, csv_path = runner.build_prospect_search_args(area_cmd)
assert sys.executable in argv[0]
assert "prospect-search.py" in argv[2]
assert "--keywords" in argv and argv[argv.index("--keywords") + 1] == "pizza,pizzeria"
assert "--areas" in argv and argv[argv.index("--areas") + 1] == "Athens GA,Watkinsville GA"
assert "--sync-to-hubspot" in argv
assert "athens" in str(csv_path).lower()  # slug derived from first area
print(f"    argv[0:5]: {argv[0:5]}")
print(f"    csv: {csv_path}")

company_cmd = Command(
    intent="company_search",
    keywords=["Acme Coffee"],
    areas=["Atlanta GA"],
    company_name="Acme Coffee",
    human_summary="Looking up Acme Coffee in Atlanta.",
)
argv2, csv2 = runner.build_prospect_search_args(company_cmd)
# For company_search we use company_name as the single keyword.
assert argv2[argv2.index("--keywords") + 1] == "Acme Coffee"
print(f"    company argv keywords: {argv2[argv2.index('--keywords') + 1]!r}")
print("    ok")


# --- 4. Slugify ---
print("[4] _slugify_area...")
cases = {
    "Atlanta": "atlanta",
    "Blue Ridge": "blue-ridge",
    "Athens GA": "athens",          # trailing state suffix stripped
    "Roswell, GA": "roswell",
    "New York, NY": "new-york",
}
for raw, expected in cases.items():
    got = runner._slugify_area(raw)
    assert got == expected, f"_slugify_area({raw!r}) = {got!r} expected {expected!r}"
print(f"    ok ({len(cases)} cases)")


# --- 5. strip_mention ---
print("[5] strip_mention...")
mention_cases = {
    "<@U08AB12CD> find pizza in Athens": "find pizza in Athens",
    "<@W099ZZZ> lookup Acme Coffee": "lookup Acme Coffee",
    "find pizza": "find pizza",
    "<@U001> <@U002> hello": "hello",  # strips all mentions (OK for this bot)
}
for raw, expected in mention_cases.items():
    got = command_parser.strip_mention(raw)
    assert got == expected, f"strip_mention({raw!r}) = {got!r} expected {expected!r}"
print(f"    ok ({len(mention_cases)} cases)")


# --- 6. Patched scripts still parse ---
print("[6] Patched scripts still parse as valid Python...")
for name in ("prospect-search.py", "email-finder.py"):
    src = (HERE.parent / "scripts" / name).read_text()
    ast.parse(src)  # raises SyntaxError on bad code
    print(f"    {name}: ok")


# --- 7. Env-var resolution priority (read the patched source) ---
print("[7] Patched scripts honor env vars first...")
ps = (HERE.parent / "scripts" / "prospect-search.py").read_text()
assert "os.environ.get('BRAVE_API_KEY')" in ps, \
    "prospect-search.py should read BRAVE_API_KEY env var"
ef = (HERE.parent / "scripts" / "email-finder.py").read_text()
assert "os.environ.get('HUNTER_API_KEY'" in ef, \
    "email-finder.py should read HUNTER_API_KEY env var"
print("    ok")


print("\nAll smoke tests passed.")
