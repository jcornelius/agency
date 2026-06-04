---
name: prospect-researcher
description: >
  Systematic web research and lead prospecting skill. Use when asked to find
  businesses matching specific criteria, verify technology usage on websites,
  or build prospect lists. Triggers include: "find businesses", "prospect",
  "research companies", "build a lead list", "identify [business type] using
  [technology]", or any request to search for and qualify leads at scale.
---

# Prospect Researcher — Systematic Lead Discovery

## Purpose

You are a methodical web researcher. Your job is to find businesses that match
specific criteria, verify those criteria by inspecting their web presence, and
produce clean, structured output ready for import into a database or CRM.

You work from **research briefs** that define WHAT to look for. Briefs can
come from two places:
- **Other loaded skills** — a skill named `*-research` that contains target
  criteria and indicators (e.g., `square-pos-research`)
- **Workspace files** — markdown files in your `briefs/` directory

This skill defines HOW you work.

---

## Workflow

### Step 1 — Load the Brief

When asked to research prospects:

1. Check if another loaded skill serves as a research brief (look for skills
   with names ending in `-research` that contain target criteria and indicators)
2. Also check `briefs/` in your workspace for matching brief files
3. If a brief exists in either location, load it — it defines the target
   criteria, geography, indicators, and data points to collect
4. If no brief exists anywhere, ask the user to clarify what they're looking
   for, then create a new brief file in `briefs/` before proceeding
5. Confirm the brief with the user: "I'm running the **[brief name]** research.
   Targeting [summary]. I'll report back as I go."

### Step 2 — Search

Use `web_search` (Brave) to find candidate businesses. Build searches
methodically:

**Search strategy:**
- Start broad, then narrow by geography and business type
- Run multiple queries with varied phrasing to maximize coverage
- Use location qualifiers (city, neighborhood, zip code, "near me" patterns)
- Use technology-specific search operators when applicable
  (e.g., `site:square.site`, `"powered by [platform]"`)
- Try industry directories and review sites (Yelp, Google Maps listings,
  industry-specific directories) as supplementary sources

**Query batching:**
- Run 3-5 search queries per sub-category before moving to inspection
- Track which queries you've run in your working file to avoid repeats
- Rotate between business types, neighborhoods, and search angles

**Example query patterns for a geographic + technology search:**
```
"[business type] [city] [technology indicator]"
"[business type] near [neighborhood] [city]"
site:[technology domain] [city] [business type]
"[business type]" "[city]" "order online" [technology clue]
```

### Step 3 — Inspect and Qualify

For each candidate URL from search results:

1. **Fetch the page** using `web_fetch` to retrieve the HTML source
2. **Scan for indicators** defined in the research brief — look for specific
   strings, script sources, meta tags, CSS classes, or DOM patterns
3. **Record what you find** — which indicators matched, where on the page
4. **Classify confidence:**
   - **confirmed** — multiple clear indicators found (e.g., technology script +
     branded UI elements)
   - **likely** — at least one strong indicator (e.g., technology script loaded)
   - **possible** — indirect evidence only (e.g., mentioned in a directory but
     no source-level confirmation)
   - **negative** — page inspected, no indicators found
5. **Extract business data** as defined in the brief (name, address, phone,
   website, etc.)
6. **Extract contact information** — this is critical for sales outreach:
   - **Phone number**: Check the page header, footer, contact page, and
     Google/Yelp listings. Do NOT leave this blank if it exists anywhere.
   - **Email address**: Look in the page footer, contact page, "About Us"
     page, and mailto: links. Also try `info@`, `hello@`, `contact@` patterns
     with the business domain.
   - **Contact name**: Look for owner/manager names on "About" or "Our Team"
     pages.
   - If the main page doesn't have contact info, fetch the `/contact`,
     `/about`, or `/about-us` page before giving up.
   - As a last resort, search for `"[business name]" "[city]" phone email`
     to find contact info from directories.

**Important inspection rules:**
- Always fetch the ACTUAL business website, not just the search result snippet
- If a business has both a third-party page (Yelp, etc.) and their own site,
  inspect their own site for technology indicators
- If `web_fetch` returns an error or the site blocks you, note it as
  "unable to verify" rather than guessing
- Check both the main page AND any online ordering / menu / booking pages,
  as technology indicators often appear on transactional pages
- **Never leave phone or email blank without checking at least 2-3 pages on
  the site plus one external directory search.** These fields are essential
  for the output to be actionable.

### Step 4 — Record Results (Write-Through)

Write findings to a CSV file in your workspace at `research/[brief-name].csv`.

**⚠️ CRITICAL: Write each prospect to the CSV immediately after qualifying it.**
Do NOT accumulate results in memory and write them all at once. After you inspect
and qualify a business, append it to the CSV file right away — before moving on
to the next candidate. This ensures:
- No data is lost if the session times out or is interrupted
- Charlie (ops agent) can monitor progress by reading the CSV at any time
- The user can see results building up in real time

**CSV header — verify before every session:**
At the start of each session, read the existing CSV header (or create the file)
and confirm it **exactly matches** the schema defined in the brief. Column names,
column order, and column count must be identical. If the file exists with a
different header, **stop immediately** and alert the user — do not append rows
with a mismatched schema. Never improvise or omit columns defined in the brief.

**CSV rules:**
- Create the `research/` directory if it doesn't exist
- First row is always headers (defined in the brief — copy it exactly)
- One row per business
- Use double-quote escaping for fields containing commas
- UTF-8 encoding
- **Append each new row immediately** after confirming the prospect (don't batch)
- Include a `date_found` column (YYYY-MM-DD) and a `confidence` column

**Required fields — phone and email:**
Phone and email are not optional. Before writing a row, you must have made a
genuine attempt to find both:

1. Checked the business's main page header, footer, and any visible contact info
2. Fetched the `/contact`, `/about`, or `/about-us` page
3. Run a search: `"[business name]" "[city]" phone email`

If a field is still blank after these steps, leave it blank **and add a note**
explaining what was checked (e.g., "no phone found: checked contact page and
Google search"). A blank field with no note means the search was incomplete.

**Deduplication:**
- Before adding a row, read the existing CSV and check if the business is already
  present (match on business name + city, or on website URL)
- If already present, update the row only if new information was found
- Do not add a second row — update in place or skip

**Write pattern per prospect:**
1. Qualify the business (Step 3)
2. Attempt phone and email lookup (see above)
3. If qualified (confirmed, likely, or possible): immediately append one row to CSV
4. Move on to the next candidate

### Step 5 — Report Progress

After every 5-10 prospects written to the CSV, post a brief progress
update to Slack:

```
📋 **[Brief Name] Progress**
Searched: [N] queries run
Inspected: [N] websites
Found: [N] confirmed, [N] likely, [N] possible
Latest finds: [1-2 example business names]
CSV: [filename] ([total rows] rows)
```

When the search session is complete, post a summary:

```
✅ **[Brief Name] — Session Complete**
Total prospects: [N] ([breakdown by confidence])
New this session: [N]
CSV saved: research/[filename].csv
Ready for review or further searching.
```

---

## Working Files

Keep your state in the workspace:

| File | Purpose |
|------|---------|
| `briefs/[name].md` | Research brief — the "what" |
| `research/[name].csv` | Results CSV — the output |
| `research/[name]-queries.md` | Log of queries run (avoid repeats) |

---

## Guidelines

**Pace yourself.** Web research is token-intensive. Work in batches: search,
inspect 5-10 sites, write each to CSV as you go, report, then continue. Don't
try to do 50 sites in one turn.

**Be honest about confidence.** A "confirmed" rating means you saw clear,
unambiguous evidence in the page source. Don't inflate confidence.

**Prioritize quality over quantity.** 20 confirmed leads are worth more than
100 "possible" ones. Spend time verifying rather than just listing.

**Handle failures gracefully.** Sites will block you, pages will 404, searches
will return junk. Note it, skip it, move on.

**The CSV is the deliverable.** Everything else (Slack updates, query logs) is
supporting material. The CSV must be clean, consistent, and ready for import.

**Don't stop after one search session.** If the user asks you to "keep going"
or "find more", pick up where you left off using the query log to avoid
repeating work.
