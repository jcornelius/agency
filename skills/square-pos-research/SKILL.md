---
name: square-pos-research
description: >
  Research brief template for identifying businesses that use a specific
  vendor, platform, or technology — and one worked example targeting Square
  Online (restaurants, cafes, food service). Pair with the `prospect-researcher`
  skill for the research methodology. Triggers: any request to find businesses
  that use a particular product, payment processor, POS, CMS, hosting
  platform, or web technology; "find [vendor] customers"; "build a
  [technology] prospect list"; the literal phrase "square-pos-research".
---

# Research Brief — Template + Worked Example

This file does two things:

1. **Defines the template** every research brief should follow (this section).
2. **Provides one fully-filled-out example** targeting Square Online (further down).

To run actual research, this brief defines WHAT to look for. Follow the
**`prospect-researcher`** skill for HOW to conduct the research.

To create a new brief for a different vendor or platform, copy this file,
update each section with the new target's specifics, and save it under a
new skill directory (e.g., `skills/shopify-merchant-research/`) or under
`briefs/[name].md` in your workspace.

---

## Template — Sections Every Brief Needs

### 1. Target Profile

**Business types** — the kinds of businesses likely to use this platform.
List the categories specifically; "small businesses" is not specific enough.

**Geography** — the scope of the search. The user defines this at the start
of each session. Common scopes: a city, a metro area, a list of neighborhoods,
or a state. If no geography is given, ask before starting.

### 2. Vendor Indicators

Indicators are the web-visible fingerprints that a business uses the target
platform. Organize them by signal strength.

**Primary indicators** (any one = "confirmed"): unambiguous signals such as
the platform's hosted domain, a `<meta name="generator">` tag, a unique JS
SDK script source, or a CDN domain controlled by the vendor.

**Secondary indicators** (need 2+ for "likely", 1 = "possible"): weaker but
still meaningful — CSS class prefixes, `data-*` attributes, branded URL
patterns, footer "powered by" text, vendor-specific link patterns.

**False positives** — name-collision and look-alike traps. List the things
researchers will mistake for the real signal and explain why they don't
count. (Example: "Squarespace" is not "Square.")

### 3. Search Strategy

Provide query patterns for `web_search` (Brave). Organize them by intent:

- **High-value queries** that surface obvious customers (e.g., `site:` searches against the vendor's hosted domain)
- **Neighborhood / geography-specific queries** that narrow by location
- **Directory and review-site queries** that piggyback on Yelp, Google Maps, industry directories
- **Supplementary approaches** — vendor case studies, marketplaces, seller directories the vendor publishes

### 4. CSV Schema

Define the exact output schema. Specify:

- **File path:** `research/[brief-name].csv`
- **Column order:** list every column in the exact order they appear
- **Per-column meaning + example value** — so the researcher writes consistent rows
- **Required vs. optional columns** — phone and email are almost always required for sales outreach; the brief should say so explicitly

### 5. Why This Brief Is Valuable

A one-paragraph "so what." Why does identifying customers of this platform
matter? Sales outreach for adjacent products? Market sizing? Competitive
intelligence? This belongs in the brief because it shapes how strictly you
classify confidence.

---

# Worked Example — Square POS Research Brief

The rest of this file fills out the template for one real target: businesses
using **Square Online** for ordering and **Square POS** in-store, primarily
in food service.

---

## Target Profile

### Business Types
- Restaurants (full service and fast casual)
- Pizzerias
- Coffee shops and cafes
- Bakeries
- Juice bars and smoothie shops
- Food trucks (if they have a web presence)
- Ice cream and dessert shops

### Geography
The user defines the target geography at the start of each research session.
Common scopes include a city, metro area, or list of neighborhoods. If no
geography is specified, ask before starting.

The user may expand or change the geography mid-session. If they do, note the
new scope and continue.

---

## Square Online Indicators

When you fetch a business website, look for these indicators in the HTML source.
They are listed from strongest to weakest signal.

### Primary Indicators (any one = "confirmed")

| Indicator | What to Look For |
|-----------|------------------|
| **Meta generator tag** | `<meta name="generator" content="Square Online">` |
| **Square Online domain** | Site hosted on `*.square.site` |
| **Square JS SDK** | Script src containing `js.squareup.com` |
| **Square CDN assets** | Resources loaded from `cdn.squareup.com` or `square-cdn.com` |

### Secondary Indicators (need 2+ for "likely", 1 = "possible")

| Indicator | What to Look For |
|-----------|------------------|
| **Square checkout links** | Links containing `checkout.square.site` or `squareup.com/pay` |
| **Square appointment booking** | Links to `squareup.com/appointments` or `book.squareup.com` |
| **sq- CSS class prefix** | CSS classes starting with `sq-` (e.g., `sq-widget`, `sq-card-form`) |
| **data-sq attributes** | HTML attributes like `data-sq-*` |
| **Square branding text** | Footer text like "Powered by Square" or "Powered by Square Online" |
| **Square Online ordering** | URLs containing `ordering.square.site` |
| **Square gift cards** | Links to `squareup.com/gift` or `gift.square.site` |
| **Square loyalty** | References to `square.com/loyalty` or Square Loyalty widgets |

### False Positives — DO NOT Count These

| Not This | Why |
|----------|-----|
| **Squarespace** | Completely different company. `squarespace.com` is NOT Square. |
| **Square Enix** | Video game company, not POS. |
| **"Square feet"** | Real estate term, not technology. |
| **Square Capital / Square Banking** | Financial products, not POS indicators. |

---

## Search Strategy

Use these query patterns with `web_search` (Brave). Rotate through business
types and neighborhoods.

### High-Value Queries
```
site:square.site restaurant [city]
site:square.site pizza [city]
site:square.site coffee [city]
site:square.site bakery [city]
"powered by Square Online" restaurant [city]
"order online" restaurant [city] square
"Square Online" menu [city]
```

### Neighborhood-Specific Queries
```
restaurant "order online" [neighborhood] [city]
pizza delivery [neighborhood] [city] "square"
coffee shop [city] "order online"
restaurant [neighborhood] "square.site"
```

### Directory and Review Site Queries
```
site:yelp.com restaurant [city] "order on square"
"[city] restaurant" "online ordering" "square"
```

### Supplementary Approaches
- If you find one Square restaurant, check if Square has a local directory
  or marketplace page that lists other nearby businesses
- Look for Square seller stories or case studies mentioning restaurants in the target area
- Check `ordering.square.site` with business names from the target area

---

## CSV Schema

Output file: `research/square-pos-[location].csv`

Headers (in this exact order):

```
business_name,business_type,address,city,state,zip,phone,email,contact_name,website,square_url,indicators_found,confidence,date_found,notes
```

| Column | Description | Example |
|--------|-------------|---------|
| `business_name` | Legal or common business name | "Joe's Pizza" |
| `business_type` | Category from target list | "pizzeria" |
| `address` | Street address if available | "123 Peachtree St NE" |
| `city` | City | "Chicago" |
| `state` | State abbreviation | "GA" |
| `zip` | ZIP code if available | "30308" |
| `phone` | Phone number — REQUIRED, search until found | "(404) 555-1234" |
| `email` | Email address — REQUIRED, search until found | "info@joespizza.com" |
| `contact_name` | Owner or manager name if available | "Joe Smith" |
| `website` | Primary business website | "https://joespizza.com" |
| `square_url` | Square-specific URL if different | "https://joespizza.square.site" |
| `indicators_found` | Which indicators matched (semicolon-separated) | "meta generator;sq- classes;cdn.squareup.com" |
| `confidence` | confirmed / likely / possible | "confirmed" |
| `date_found` | Date discovered | "2026-03-02" |
| `notes` | Anything else notable | "Also has Square gift cards" |

---

## What Makes This Brief Valuable

Businesses using Square Online for ordering almost certainly use Square POS
in-store. This brief targets the web-visible signal (Square Online) to infer
the in-store technology stack. A "confirmed" Square Online presence is a strong
indicator that the business is a Square POS customer across their operation.

This data is useful for:
- Sales outreach for POS-adjacent products and services
- Market sizing of Square's presence in a geographic area
- Competitive analysis against other POS platforms
