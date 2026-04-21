# Twenty → HubSpot Migration Summary

## Overview
Successfully migrated prospect management from Twenty CRM to HubSpot, including deduplication and workflow automation.

## Timeline
- **Initial Sync:** 134 companies from square-pos-atlanta.csv
- **Test Run:** 20-record subset + full file (created duplicates)
- **Final State:** 117 clean company records in HubSpot

## What Happened

### Phase 1: Initial Sync
✅ Created `HubSpotClient` (stdlib-only, no dependencies)
✅ Updated `prospect-search.py` to sync companies to HubSpot
✅ Added custom field support (square_url, keywords_found, confidence, date_found)
✅ Synced 134 companies successfully

### Phase 2: Discovered Duplicates
❌ HubSpot showed 248 companies (not 134!)
- Root cause: `find_company()` used limited pagination (first 100 records only)
- Companies created in test runs weren't detected in full runs
- Each sync created new copies instead of updating existing ones

### Phase 3: Fixed Deduplication
✅ Rewrote `find_company()` to use HubSpot's `/search` endpoint
✅ Fixed query parameter handling for repeated properties
✅ Cleaned up 131 duplicate records
✅ Final count: 117 unique companies

### Phase 4: Email Enrichment
✅ Ran `email-finder.py --from-hubspot`
✅ Found 7 role emails from Hunter.io (info@, contact@, etc.)
✅ 0 individual contact records created (Hunter didn't find specific people)
- This is expected for local small businesses

## Final State

| Metric | Count |
|--------|-------|
| Companies in HubSpot | 117 |
| Custom fields enabled | 4 |
| Email addresses found | 7 |
| Contact records created | 0 |
| Errors | 0 |

## Scripts

### prospect-search.py
- Finds companies via web search (Digger integration)
- Backfills CSV to HubSpot
- **Flags:** `--sync-to-hubspot`, `--backfill-hubspot`, `--dry-run`

### email-finder.py
- Reads companies from HubSpot
- Enriches with Hunter.io emails
- Creates Contact records for individuals
- **Flags:** `--from-hubspot`, `--max-companies`, `--dry-run`

### hubspot_client.py
- Minimal HubSpot REST API client
- Methods: find_company, create_company, update_company, create_contact, list_companies
- Uses proper search endpoint for deduplication

## Custom Fields
All synced to HubSpot company records:
- `square_url` - Square Online store link
- `keywords_found` - Search keywords that matched
- `confidence` - Data confidence level (confirmed/needs_validation)
- `date_found` - Date company was discovered

## Future Syncs
✅ Deduplication now working correctly
✅ Running the full dataset again will:
1. Detect existing companies by domain
2. Update (not create duplicates)
3. Add new companies only if not found

## Usage

**Sync new companies to HubSpot:**
```bash
export HUBSPOT_PRIVATE_APP_TOKEN='pat-na2-...'
python3 scripts/prospect-search.py brief.md --backfill-hubspot --csv companies.csv
```

**Enrich with emails and create contacts:**
```bash
export HUBSPOT_PRIVATE_APP_TOKEN='pat-na2-...'
python3 scripts/email-finder.py --from-hubspot --max-companies 50
```

## Notes
- All code uses Python stdlib (no external dependencies beyond Hunter/Apollo APIs)
- Deduplication by domain first, then name
- Rate limiting: 60s retry on HubSpot 429 errors
- Athens CSV not yet processed (196 more companies available)
