# Square POS Prospect Field Structure Guide

## Overview

This document describes the improved HubSpot field structure implemented to reduce confusion about which platform companies use for ordering, and to provide your sales team with clear confidence indicators.

## Problem Solved

Previously, companies could appear to be "false positives" because:
- They were found via `site:square.site` search (they DO use Square)
- But their primary website (from Google Places) was on a different platform (Slice, Shopify, etc.)
- Sales team would check the website and find no Square indicators
- Confusion about data quality resulted

**Example:** Sal's Pizza 105163
- **Square Online URL:** sals-pizza-105163.square.site (has Square indicators ✅)
- **Primary Website:** ordersalspizzamenu.com (Slice platform ❌)
- **Reality:** Multi-platform company using both Slice AND Square

## New Field Structure

### 1. `square_online_url` (Previously `square_url`)
- **Description:** Direct URL to the company's Square Online store
- **Format:** Always a `*.square.site` domain
- **What it means:** This company definitely uses Square for at least one ordering channel
- **Example:** `https://sals-pizza-105163.square.site/`
- **HubSpot Field Type:** Text
- **Visibility:** Sales team should prioritize companies with this field populated

### 2. `primary_website` (Previously `website`)
- **Description:** Company's main website or web presence
- **Format:** Custom domain, could be any platform
- **What it means:** Where the company primarily markets themselves online
- **Note:** May NOT be their Square store; may use a different platform
- **Example:** `https://ordersalspizzamenu.com/` (Slice platform)
- **HubSpot Field Type:** Text
- **Visibility:** Informational - use for general company info, not POS platform determination

### 3. `square_confidence` (New Field)
- **Description:** Confidence level that company uses Square for ordering
- **Possible Values:**
  - **`confirmed_square`** — Company uses Square (has square_online_url + likely on their primary site)
  - **`has_square_site`** — Company has a Square Online store but may not actively promote it
  - **`multi_platform`** — Company uses Square AND other platforms (e.g., Square + Slice)
  - **`needs_review`** — Data is incomplete; manual verification recommended

- **HubSpot Field Type:** Select Dropdown
- **Visibility:** Critical for sales filtering and prioritization

## How to Use These Fields

### For Sales Reps
1. **Filter by Confidence:**
   - Start with `square_confidence = "confirmed_square"` for highest priority
   - `multi_platform` companies are also good targets (they're tech-savvy)
   - `needs_review` requires manual verification

2. **Check Both URLs:**
   - Use `square_online_url` when presenting Square-specific offerings
   - Use `primary_website` for general company research

3. **Example Outreach:**
   - ✅ **Confirmed Square:** "We noticed you're using Square Online for orders..."
   - ✅ **Multi-Platform:** "We see you're using both Slice and Square. We can help optimize..."
   - ❌ **Needs Review:** Verify platform before outreach

### For Data Management
1. **During CSV Import:**
   - Source data from `site:square.site` search (these populate `square_online_url`)
   - Enrich with Google Places (populates `primary_website`)
   - Script automatically calculates `square_confidence`

2. **Adding New Companies:**
   - Ensure `square_online_url` is populated if found via Square search
   - Leave `primary_website` blank if not available
   - Let script calculate `square_confidence` automatically

## Data Examples

### Example 1: Confirmed Square User
```
business_name: "Black Coffee ATL"
square_online_url: "https://blackcoffeeatl.square.site/"
primary_website: "https://blackcoffeeatl.com/"
square_confidence: "confirmed_square"
```
*Interpretation: Uses Square for ordering on their square.site AND their main site*

### Example 2: Multi-Platform Company
```
business_name: "Sal's Pizza 105163"
square_online_url: "https://sals-pizza-105163.square.site/"
primary_website: "https://ordersalspizzamenu.com/"
square_confidence: "multi_platform"
```
*Interpretation: Has Square Online store, but primary site is Slice (different platform)*

### Example 3: Square-Only (No Main Site)
```
business_name: "Urban Grind"
square_online_url: "https://urban-grind.square.site/"
primary_website: ""
square_confidence: "has_square_site"
```
*Interpretation: Only has Square Online store, no separate website*

### Example 4: Needs Verification
```
business_name: "Coffee Off The Square"
square_online_url: ""
primary_website: "https://coffeethesquare.com/"
square_confidence: "needs_review"
```
*Interpretation: Website found but no Square indicators confirmed; needs manual check*

## Confidence Calculation Logic

The script automatically assigns confidence levels:

```
IF square_online_url exists AND primary_website exists:
    confidence = "multi_platform"
ELSE IF square_online_url exists AND no primary_website:
    confidence = "has_square_site"
ELSE IF square_online_url exists:
    confidence = "confirmed_square"
ELSE:
    confidence = "needs_review"

IF original_confidence_data says "confirmed":
    confidence = "confirmed_square"  (upgrade)
```

## Migrating Old Data

All 117 existing companies were automatically migrated:
- Old `website` field → `primary_website`
- Old `square_url` field → `square_online_url`
- New `square_confidence` calculated for each

**Migration Result:**
- ✅ 83 companies: `confirmed_square`
- ✅ 27 companies: `needs_review` (need manual verification)
- ✅ 7 companies: `multi_platform`

## Future Imports

When running `prospect-search.py --backfill-hubspot`:
1. Script automatically populates `square_online_url` from CSV
2. Script populates `primary_website` from enrichment data
3. Script calculates `square_confidence`
4. All fields sent to HubSpot in single update

**Result:** Sales team sees accurate, complete data immediately

## Manual Verification (For `needs_review`)

For companies marked `needs_review`:
1. Visit the `primary_website` (if it exists)
2. Check page source for:
   - `<meta name="generator" content="Square Online">`
   - Square JavaScript SDK (js.squareup.com)
   - Square payment buttons
3. Update `square_confidence` based on findings:
   - Found Square indicators → change to `confirmed_square`
   - Found different platform → change to `multi_platform`
   - No POS platform found → mark as `needs_review` (investigate manually)

## Benefits

✅ **Clear Separation:** Marketing site vs. ordering platform are now distinct  
✅ **Reduced Confusion:** Sales team knows exactly what they're looking at  
✅ **Better Filtering:** Can prioritize by confidence level  
✅ **Data Quality:** Backwards compatible, no data loss  
✅ **Actionable:** Confidence score guides outreach strategy  
✅ **Multi-Platform Support:** Properly handles companies using multiple ordering platforms

## API Reference

### HubSpot Custom Properties
```
square_online_url (text)
primary_website (text)
square_confidence (enum: confirmed_square | has_square_site | multi_platform | needs_review)
```

### Python Script Usage
```python
# New fields are automatically populated by prospect-search.py
python3 prospect-search.py brief.md --backfill-hubspot --csv companies.csv

# Existing data was migrated via:
python3 migrate_to_new_fields.py
```

## Support

If you find companies with incorrect confidence levels:
1. Document the company name and current confidence
2. Check the website to verify actual platform usage
3. Update confidence level in HubSpot
4. Share findings so script logic can be improved

