#!/usr/bin/env python3
"""
backfill-address.py — one-off repair script.

Runs two passes against Hubspot:

  1. ADDRESSES: walks every Company whose `city` property is empty, parses
     the concatenated `address` string (the old payload format), and updates
     the record with separated street / city / state / zip properties.

  2. ASSOCIATIONS: walks every Contact. If a contact has no linked Company,
     it tries to match by the contact's email domain and creates the
     association via the v4 default endpoint. Fixes the orphans left by the
     deprecated v3 association 404 bug.

Usage:

    cd /Users/jc/Nest/digger/scripts
    # Dry run first — shows what would change, no writes:
    python3 backfill-address.py --dry-run

    # Real run:
    python3 backfill-address.py

    # Just one pass:
    python3 backfill-address.py --only-addresses
    python3 backfill-address.py --only-contacts

Loads HUBSPOT_PRIVATE_APP_TOKEN from the environment first, then from
../bot/.env if not present. Safe to re-run — idempotent (both passes check
current state before writing).
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import time
from pathlib import Path

# Make sure we can import the sibling module regardless of CWD.
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from hubspot_client import HubSpotClient  # noqa: E402


# "Street, City, ST, 12345" or "Street, City, ST 12345" (comma before zip optional).
# Also tolerates "Street Suite A, City Name With Spaces, GA 30301-1234".
_ADDRESS_RE = re.compile(
    r"""^
    (?P<street>.+?),\s*
    (?P<city>.+?),\s*
    (?P<state>[A-Z]{2}),?\s+
    (?P<zip>\d{5}(?:-\d{4})?)
    \s*$""",
    re.VERBOSE,
)


def parse_address(combined: str) -> tuple[str, str, str, str] | None:
    if not combined:
        return None
    m = _ADDRESS_RE.match(combined.strip())
    if not m:
        return None
    return (
        m.group("street").strip(),
        m.group("city").strip(),
        m.group("state").strip(),
        m.group("zip").strip(),
    )


def load_token() -> str:
    """Env first, then ../bot/.env."""
    token = os.environ.get("HUBSPOT_PRIVATE_APP_TOKEN", "").strip()
    if token:
        return token
    env_file = HERE.parent / "bot" / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line.startswith("HUBSPOT_PRIVATE_APP_TOKEN="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def iter_all(hubspot: HubSpotClient, path: str, properties: list[str]):
    """Yield every object from a paginated Hubspot list endpoint."""
    after: str | None = None
    while True:
        params = {"limit": "100", "properties": properties}
        if after:
            params["after"] = after
        resp = hubspot._request("GET", path, params=params)
        if not resp:
            return
        for obj in resp.get("results", []):
            yield obj
        paging = (resp.get("paging") or {}).get("next") or {}
        after = paging.get("after")
        if not after:
            return


def backfill_addresses(hubspot: HubSpotClient, *, dry_run: bool) -> None:
    print("--- Pass 1: Address components ---")
    checked = updated = unparseable = empty_address = already_has_city = 0

    for company in iter_all(
        hubspot,
        "/crm/v3/objects/companies",
        ["name", "address", "city", "state", "zip"],
    ):
        checked += 1
        company_id = company["id"]
        props = company.get("properties", {}) or {}
        name = (props.get("name") or "?").strip()

        if (props.get("city") or "").strip():
            already_has_city += 1
            continue

        combined = (props.get("address") or "").strip()
        if not combined:
            empty_address += 1
            continue

        parsed = parse_address(combined)
        if not parsed:
            unparseable += 1
            print(f"  ⚠ unparseable: {name}  [{combined!r}]")
            continue

        street, city, state, zipcd = parsed
        payload = {
            "address": street,
            "city": city,
            "state": state,
            "zip": zipcd,
        }
        if dry_run:
            print(f"  [dry] {name}  →  city={city}  state={state}  zip={zipcd}")
        else:
            if hubspot.update_company(company_id, payload):
                updated += 1
                print(f"  ✓ {name}  →  {city}, {state} {zipcd}")
            else:
                print(f"  ✗ failed: {name}")
            time.sleep(0.2)  # gentle pacing

    print()
    print(f"  Companies checked:      {checked}")
    print(f"  Already had city:       {already_has_city}")
    print(f"  Updated:                {updated}")
    print(f"  Unparseable address:    {unparseable}")
    print(f"  Empty address field:    {empty_address}")


def get_contact_company_ids(hubspot: HubSpotClient, contact_id: str) -> set[str]:
    """Return set of company IDs currently associated with a contact."""
    resp = hubspot._request(
        "GET",
        f"/crm/v4/objects/contacts/{contact_id}/associations/companies",
    )
    if not resp or "results" not in resp:
        return set()
    ids: set[str] = set()
    for a in resp["results"]:
        # v4 returns {"toObjectId": "...", "associationTypes": [...]}
        cid = a.get("toObjectId")
        if not cid and isinstance(a.get("to"), dict):
            cid = a["to"].get("id")
        if cid:
            ids.add(str(cid))
    return ids


def backfill_associations(hubspot: HubSpotClient, *, dry_run: bool) -> None:
    print("\n--- Pass 2: Contact → Company associations ---")

    # Build a domain → company_id index once, so per-contact lookups are O(1).
    print("Indexing companies by domain...")
    domain_to_company: dict[str, str] = {}
    for c in iter_all(
        hubspot,
        "/crm/v3/objects/companies",
        ["name", "domain"],
    ):
        domain = ((c.get("properties") or {}).get("domain") or "").lower().strip()
        if domain:
            domain_to_company[domain] = c["id"]
    print(f"  Indexed {len(domain_to_company)} companies by domain")

    checked = already_assoc = associated = no_matching_company = no_email = 0

    for contact in iter_all(
        hubspot,
        "/crm/v3/objects/contacts",
        ["email", "firstname", "lastname"],
    ):
        checked += 1
        contact_id = contact["id"]
        props = contact.get("properties") or {}
        email = (props.get("email") or "").strip().lower()
        name = (f"{props.get('firstname', '')} {props.get('lastname', '')}".strip()
                or email or f"contact {contact_id}")

        if "@" not in email:
            no_email += 1
            continue
        domain = email.split("@", 1)[1]
        company_id = domain_to_company.get(domain)
        if not company_id:
            no_matching_company += 1
            continue

        existing = get_contact_company_ids(hubspot, contact_id)
        if company_id in existing:
            already_assoc += 1
            continue

        if dry_run:
            print(f"  [dry] {name}  →  {domain}")
        else:
            if hubspot.associate_contact_to_company(company_id, contact_id):
                associated += 1
                print(f"  ✓ {name}  →  {domain}")
            else:
                print(f"  ✗ failed: {name}  →  {domain}")
            time.sleep(0.2)

    print()
    print(f"  Contacts checked:       {checked}")
    print(f"  Already associated:     {already_assoc}")
    print(f"  Newly associated:       {associated}")
    print(f"  No company for domain:  {no_matching_company}")
    print(f"  No email address:       {no_email}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would change; make no API writes.")
    parser.add_argument("--only-addresses", action="store_true",
                        help="Run Pass 1 only, skip association repair.")
    parser.add_argument("--only-contacts", action="store_true",
                        help="Run Pass 2 only, skip address backfill.")
    args = parser.parse_args()

    if args.only_addresses and args.only_contacts:
        print("Error: --only-addresses and --only-contacts are mutually exclusive",
              file=sys.stderr)
        sys.exit(2)

    token = load_token()
    if not token:
        print("Error: HUBSPOT_PRIVATE_APP_TOKEN not found.\n"
              "  Set it in the environment or in /Users/jc/Nest/digger/bot/.env",
              file=sys.stderr)
        sys.exit(2)

    hubspot = HubSpotClient(token)
    if not hubspot.test_connection():
        print("Error: Cannot connect to Hubspot with the supplied token",
              file=sys.stderr)
        sys.exit(1)
    print(f"HubSpot: connected  (dry_run={args.dry_run})\n")

    if not args.only_contacts:
        backfill_addresses(hubspot, dry_run=args.dry_run)

    if not args.only_addresses:
        backfill_associations(hubspot, dry_run=args.dry_run)

    print("\nDone.")


if __name__ == "__main__":
    main()
