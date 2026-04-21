#!/usr/bin/env python3
"""
normalize-names.py — one-off repair for mashed business names in HubSpot.

The old pipeline extracted names from Square subdomains like
`cafecubana.square.site`, producing "Cafecubana" when the real business is
"Café Cubana Bakery". This script walks every HubSpot company, identifies
names that look mashed (single long word, or uniform case throughout), and
re-queries Google Places (via `goplaces`) using the current name + city +
state. If Places returns a materially different canonical name, the record
is updated.

Usage:

    cd /Users/jc/Nest/digger/scripts
    # Preview all proposed changes:
    python3 normalize-names.py --dry-run

    # Commit them:
    python3 normalize-names.py

    # Speed-optimized: only check names that LOOK mashed (skips obviously
    # clean names to save Google Places API calls):
    python3 normalize-names.py --only-mashed

Requires `goplaces` CLI on PATH and GOOGLE_PLACES_API_KEY set (from env or
../bot/.env). Rate-limited to avoid burning through Places quota.

Default is "check every company" — the per-record "already canonical" check
inside the loop makes a same-name Places response a no-op anyway, so
processing every record is safe, just takes a few minutes more than
--only-mashed.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from hubspot_client import HubSpotClient  # noqa: E402


def load_env_file() -> None:
    """Populate os.environ from ../bot/.env for any keys not already set."""
    env_file = HERE.parent / "bot" / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and not os.environ.get(key):
            os.environ[key] = val


def looks_mashed(name: str) -> bool:
    """Heuristic: does this name look like a URL-slug-derived smash-up?

    Triggers when:
      • the name is a single word (no internal whitespace) AND long (>10 chars),
      • OR the name is a single word AND has no internal uppercase letter
        (other than the first), meaning common words like "Coffee" or "Roastery"
        weren't broken out of the slug.
    """
    s = (name or "").strip()
    if not s:
        return False
    if " " in s:
        return False
    if len(s) <= 8:
        # Short single words ("Kroger", "Subway") are almost always correct.
        return False
    # Long single word — very likely mashed. A few false positives like
    # "Starbucks" (9) will cost an extra Places API call but harm nothing
    # (the in-loop "already canonical" check skips no-op renames).
    return True


def goplaces_lookup(query: str) -> dict | None:
    """Return the top Google Places hit for a search query, or None."""
    try:
        r = subprocess.run(
            ["goplaces", "search", query, "--json", "--limit", "1"],
            capture_output=True, text=True, timeout=15,
        )
        if r.returncode != 0 or not r.stdout.strip():
            return None
        data = json.loads(r.stdout)
        if not data:
            return None
        return data[0]
    except Exception as e:
        print(f"    ⚠ goplaces failed: {e}", file=sys.stderr)
        return None


def iter_all_companies(hubspot: HubSpotClient):
    """Yield every company with the properties we need."""
    after: str | None = None
    props = ["name", "city", "state", "primary_website",
             "square_online_url", "domain"]
    while True:
        params: dict = {"limit": "100", "properties": props}
        if after:
            params["after"] = after
        resp = hubspot._request("GET", "/crm/v3/objects/companies", params=params)
        if not resp:
            return
        for c in resp.get("results", []):
            yield c
        paging = (resp.get("paging") or {}).get("next") or {}
        after = paging.get("after")
        if not after:
            return


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Print proposed renames without writing.")
    parser.add_argument("--only-mashed", action="store_true",
                        help="Skip names that don't look mashed (saves API calls, "
                             "but may miss edge cases where Places has a better name).")
    parser.add_argument("--limit", type=int, default=0,
                        help="Stop after N companies (0 = all). Useful for testing.")
    args = parser.parse_args()

    load_env_file()

    if not os.environ.get("GOOGLE_PLACES_API_KEY"):
        print("Error: GOOGLE_PLACES_API_KEY not set (env or ../bot/.env)",
              file=sys.stderr)
        sys.exit(2)
    token = os.environ.get("HUBSPOT_PRIVATE_APP_TOKEN", "").strip()
    if not token:
        print("Error: HUBSPOT_PRIVATE_APP_TOKEN not set", file=sys.stderr)
        sys.exit(2)

    hubspot = HubSpotClient(token)
    if not hubspot.test_connection():
        print("Error: Cannot connect to HubSpot", file=sys.stderr)
        sys.exit(1)
    print(f"HubSpot: connected  "
          f"(dry_run={args.dry_run}, only_mashed={args.only_mashed})\n")

    inspected = skipped_clean = renamed = no_match = no_location = 0

    for idx, company in enumerate(iter_all_companies(hubspot)):
        if args.limit and inspected >= args.limit:
            break
        inspected += 1
        props = company.get("properties") or {}
        cid = company["id"]
        name = (props.get("name") or "").strip()
        city = (props.get("city") or "").strip()
        state = (props.get("state") or "").strip()

        if args.only_mashed and not looks_mashed(name):
            skipped_clean += 1
            continue

        if not city and not state:
            # Without a location hint, goplaces would likely return wrong
            # matches. Skip and report — run backfill-address.py first.
            no_location += 1
            print(f"  [{inspected}] {name}  — skipping (no city/state on record)")
            continue

        # Build query. Include name + city + state for best match.
        query_parts = [name]
        if city: query_parts.append(city)
        if state: query_parts.append(state)
        query = " ".join(query_parts)

        print(f"  [{inspected}] {name}  (city={city!r}, state={state!r})")
        print(f"      query: {query}")

        place = goplaces_lookup(query)
        if not place:
            no_match += 1
            print(f"      no Google Places match — leaving as is")
            time.sleep(0.5)
            continue

        canonical = (place.get("name") or "").strip()
        if not canonical:
            no_match += 1
            print(f"      Places returned no name — leaving as is")
            time.sleep(0.5)
            continue

        # Normalized comparison — treat pure whitespace/case differences as "same".
        def _k(s: str) -> str:
            return s.lower().replace(" ", "").replace("'", "").replace("-", "")
        if _k(canonical) == _k(name):
            skipped_clean += 1
            print(f"      already canonical (matches '{canonical}')")
            time.sleep(0.3)
            continue

        # It's a real rename.
        if args.dry_run:
            renamed += 1
            print(f"      [dry] rename → {canonical!r}")
        else:
            if hubspot.update_company(cid, {"name": canonical}):
                renamed += 1
                print(f"      ✓ renamed → {canonical!r}")
            else:
                print(f"      ✗ update failed")
            time.sleep(0.3)

    print()
    print(f"  Companies inspected:        {inspected}")
    print(f"  Skipped (already clean):    {skipped_clean}")
    print(f"  Skipped (no city/state):    {no_location}")
    print(f"  Renamed:                    {renamed}")
    print(f"  No Google Places match:     {no_match}")
    if args.dry_run:
        print(f"\n  (dry run — no changes written)")


if __name__ == "__main__":
    main()
