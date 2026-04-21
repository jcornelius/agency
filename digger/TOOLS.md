# TOOLS.md - Local Notes & Tool Efficiency

Skills define _how_ tools work. This file is for _your_ specifics — the stuff that's unique to your setup.

---

## ⚠️ You Do NOT Have Write Access

You **cannot** create or modify files directly. The `write` tool is disabled.

Your job is to **run scripts** and **report results**. The scripts handle all
file creation, API calls, and CSV management.

### How to do things:

| Task | How |
|------|-----|
| Run prospect search (keywords × areas) | `exec python3 -u scripts/prospect-search.py briefs/square-pos-research.md --csv research/square-pos-{area}.csv --sync-to-hubspot --keywords "pizza,coffee" --areas "Atlanta,Roswell GA"` |
| Run prospect search (brief defaults) | `exec python3 -u scripts/prospect-search.py briefs/square-pos-research.md --csv research/square-pos-{area}.csv --sync-to-hubspot` |
| Dry run (preview without writing) | Add `--dry-run` to any command above |
| Skip first N search terms | Add `--skip-terms 10` to resume from term 11 |
| Check CSV row count | `exec wc -l research/square-pos-{area}.csv` |
| Read CSV contents | `read research/square-pos-{area}.csv` or `exec head -20 research/square-pos-{area}.csv` |
| Check a file | `read <path>` |
| Find emails (from HubSpot) | `exec python3 -u scripts/email-finder.py --from-hubspot` |
| Find emails (limited) | `exec python3 -u scripts/email-finder.py --from-hubspot --max-companies 10` |
| Find email for one domain | `exec python3 -u scripts/email-finder.py --domain example.com --name "John Smith"` |
| Enrich missing websites | `exec python3 -u scripts/prospect-search.py briefs/square-pos-research.md --csv research/square-pos-{area}.csv --enrich-websites` |
| Backfill existing CSV to HubSpot | `exec python3 -u scripts/prospect-search.py briefs/square-pos-research.md --csv research/square-pos-{area}.csv --backfill-hubspot` |
| Run any script | `exec python3 scripts/<script>.py <args>` |
| Search for text | `exec grep "pattern" file` |

### CSV file naming

Use `research/square-pos-{slug}.csv` where `{slug}` is the primary area, lowercased and hyphenated:
- "Atlanta" → `research/square-pos-atlanta.csv`
- "Blue Ridge" → `research/square-pos-blue-ridge.csv`
- "Helen" → `research/square-pos-helen.csv`
- "Dahlonega" → `research/square-pos-dahlonega.csv`

If multiple areas are searched together, use the first/primary area for the filename.

### What you CANNOT do:

- ❌ `write` to any file (tool is disabled)
- ❌ Create or modify CSV files directly
- ❌ Create new files

### When TO Use the LLM

- **Reasoning**: "Which companies should we prioritize?"
- **Analysis**: "What patterns do you see in this data?"
- **Writing**: Composing Slack messages and summaries
- **Decisions**: Anything requiring judgment
- **MSA expansion**: Generate city/neighborhood lists for metro area searches

---

## Prospect Search Flow

When a user asks to search for prospects:

1. **Infer keywords and area from the message** — don't ask if you can figure it out.
   - "search for pizzerias in Atlanta" → keywords: `pizza,pizzeria`, area: `Atlanta`
   - "find coffee shops in the Atlanta area" → keywords: `coffee,coffee shop,cafe`, area: Atlanta metro (expand MSA)
   - "search for restaurants" (no area given) → use brief defaults for area, or ask
2. **If the user says "area", "metro", or "surrounding"** — expand to MSA cities
   automatically. Use your own knowledge to generate the list. No need to confirm
   unless the user specifically asked to review the list first.
3. **Determine the CSV filename** — use the area slug convention (see above).
4. **Run the prospect search with `--sync-to-hubspot`** (always sync to HubSpot):
   ```
   exec python3 -u scripts/prospect-search.py briefs/square-pos-research.md \
     --csv research/square-pos-{area}.csv --sync-to-hubspot \
     --keywords "pizza,pizzeria,coffee" \
     --areas "Atlanta,Roswell GA,Decatur GA"
   ```
5. **Follow the Long-Running Scripts steps** (below) to wait and poll.
6. **Report search results** — how many new companies found and synced to HubSpot.
7. **Start the email finder** to enrich new companies with contact emails:
   ```
   exec python3 -u scripts/email-finder.py --from-hubspot
   ```
8. **Wait and poll again** (5 more sleeps → `process log`).
9. **Report email results** — how many contacts created, how many company emails set.

**Send exactly TWO messages:** one ack when you start (step 5), and one final
report combining both search and email results (step 9). If the email finder
hasn't finished yet, report what you have and note it's still running.

### ⚠️ Avoid Follow-Up Questions

Slack threading makes multi-turn conversations fragile. **Prefer to run
immediately** with reasonable assumptions rather than asking clarifying questions.
If you absolutely must ask, tell the user: "Reply in this thread with @Digger."

The script runs a two-pass search for each keyword × area combination:
- Pass 1: `site:square.site {keyword} {area}` — fast, targeted to Square sites
- Pass 2: `{keyword} {area} "square online"` — finds businesses on custom domains

### Sending Slack Messages

To send a message to Slack, **just output text**. The gateway delivers your
text output to Slack automatically. Do NOT call the `message` tool directly.

### ⚠️ Long-Running Scripts

The prospect search takes 2–8 minutes. The email finder takes 1–15 minutes
(depends on how many companies need enrichment). Follow these steps EXACTLY:

```
Step 1: exec python3 -u scripts/prospect-search.py ... --sync-to-hubspot  ← start search
Step 2: Output text: "On it — searching and syncing to HubSpot."
Step 3: exec sleep 10                                                      ← wait
Step 4: exec sleep 10                                                      ← wait
Step 5: exec sleep 10                                                      ← wait
Step 6: exec sleep 10                                                      ← wait
Step 7: exec sleep 10                                                      ← wait
Step 8: process log <session-name>                                         ← read search output
```

**If you see `=== COMPLETE ===` in the search output** → start the email finder:

```
Step 9:  exec python3 -u scripts/email-finder.py --from-hubspot            ← start emails
Step 10: exec sleep 10                                                     ← wait
Step 11: exec sleep 10                                                     ← wait
Step 12: exec sleep 10                                                     ← wait
Step 13: exec sleep 10                                                     ← wait
Step 14: exec sleep 10                                                     ← wait
Step 15: process log <session-name>                                        ← read email output
Step 16: Report BOTH search + email results in one final message
```

**If the search is NOT complete yet** → report the latest heartbeat and note both
scripts are running in the background. The companies sync to HubSpot as they're
found, and the email finder will process them.

**The prospect search outputs:**
- `CSV baseline: N rows` — row count before the search
- `--- Searching "term" [X/Y] ---` — current search term
- `... X entries inspected, Y new matches ...` — progress every 10 entries
- `=== COMPLETE: X new, Y total ===` — final summary (only if script finished)

**The email finder outputs:**
- `Companies needing email enrichment: N`
- `--- [X/Y] Business Name ---` — current business
- `... X/Y processed, N emails found ...` — heartbeat every 10 rows
- `=== COMPLETE: X contacts + Y company emails in HubSpot ===` — final summary

**CRITICAL RULES:**
- **Use `process log`** (not `process poll`) to read the full script output.
- **Send exactly TWO messages:** one ack, one final report.
- **Never say "I'll report back later."** Your session ends after the report.
- **Never end your session without reporting results.**

---

## Email Finder Flow

When a user asks to find emails, get emails, or enrich prospects:

1. **Run the email finder against HubSpot** (default mode):
   ```
   exec python3 -u scripts/email-finder.py --from-hubspot
   ```
2. Use `--max-companies N` to limit a test run (e.g., first 10 companies)
3. The script reads companies from HubSpot, finds emails, and creates Contact records
   - Role emails (info@, contact@, etc.) → stored on the Company record
   - Personal emails → create a Contact record linked to the Company
4. Follow the **Long-Running Scripts** steps above (5 sleeps → `process log`)

**Alternative: CSV-based mode** (only if explicitly asked for CSV output):
```
exec python3 -u scripts/email-finder.py research/square-pos-atlanta.csv \
  -o research/emails-atlanta.csv --skip-processed
```

---

## HubSpot Integration

**All prospect searches sync to HubSpot** via the `--sync-to-hubspot` flag.

### How it works:

1. **Prospect Search** (`--sync-to-hubspot`): Each new company found is created
   in HubSpot as a Company record (in addition to CSV). Deduplicates by domain
   or name.

2. **Email Finder** (`--from-hubspot`): Reads Companies from HubSpot, finds email
   addresses, and writes results back:
   - Personal emails → create a **Contact** record linked to the Company
   - Role emails (info@, contact@, admin@) → set the Company's **email** field
   - Skips companies that already have Contacts or an email set

3. **Backfill** (`--backfill-hubspot`): Push an existing CSV to HubSpot in bulk.

### Typical pipeline (happens automatically):
1. Prospect search finds companies → CSV + HubSpot (Companies)
2. Email finder enriches companies → HubSpot (Contacts + Company emails)

### Deprecated flags (still work for backward compat):
- `--twenty` → maps to `--sync-to-hubspot`
- `--twenty-backfill` → maps to `--backfill-hubspot`

---

## Workspace Layout

- `scripts/` — Python scripts that do the actual work
- `scripts/prospect-search.py` — Main research script (Brave + goplaces → CSV + HubSpot)
- `scripts/email-finder.py` — Email discovery pipeline (Hunter.io + SMTP → HubSpot)
- `research/` — CSV files with prospect data (READ ONLY for you)
- `research/square-pos-*.csv` — Square POS prospect lists (one per area)
- `briefs/` — Research brief files
- `memory/` — Daily notes and session logs

---

Add whatever helps you do your job. This is your cheat sheet.
