---
name: square-pos-research
description: >
  Research brief for identifying restaurants, cafes, and food service businesses
  that use Square for online ordering and point-of-sale. This is a "what to look
  for" brief — pair with the prospect-researcher skill for methodology. Triggers:
  "find Square restaurants", "Square POS prospects", "square-pos-research", or
  any request to identify businesses using Square.
---

# Square POS Research Brief

This brief defines WHAT to look for. Follow the **prospect-researcher** skill
for HOW to conduct the research.

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
Default: **Atlanta, GA metro area**

Include surrounding areas unless told otherwise:
- Atlanta proper (Midtown, Buckhead, Downtown, West End, East Atlanta, etc.)
- Decatur, Sandy Springs, Roswell, Marietta, Alpharetta
- Smyrna, Kennesaw, Duluth, Lawrenceville, Stone Mountain

The user may change or expand the geography via Slack. If they do, note the
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
site:square.site restaurant Atlanta
site:square.site pizza Atlanta
site:square.site coffee Atlanta
site:square.site bakery Atlanta
"powered by Square Online" restaurant Atlanta
"order online" restaurant Atlanta square
"Square Online" menu Atlanta
```

### Neighborhood-Specific Queries
```
restaurant "order online" Midtown Atlanta
pizza delivery Buckhead Atlanta "square"
coffee shop Decatur GA "order online"
restaurant East Atlanta Village "square.site"
```

### Directory and Review Site Queries
```
site:yelp.com restaurant Atlanta "order on square"
"Atlanta restaurant" "online ordering" "square"
```

### Supplementary Approaches
- If you find one Square restaurant, check if Square has a local directory
  or marketplace page that lists other nearby businesses
- Look for Square seller stories or case studies mentioning Atlanta restaurants
- Check `ordering.square.site` with Atlanta-area business names

---

## CSV Schema

Output file: `research/square-pos-atlanta.csv`

Headers (in this exact order):

```
business_name,business_type,address,city,state,zip,phone,email,contact_name,website,square_url,indicators_found,confidence,date_found,notes
```

| Column | Description | Example |
|--------|-------------|---------|
| `business_name` | Legal or common business name | "Joe's Pizza" |
| `business_type` | Category from target list | "pizzeria" |
| `address` | Street address if available | "123 Peachtree St NE" |
| `city` | City | "Atlanta" |
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

## What Makes This Valuable

Businesses using Square Online for ordering almost certainly use Square POS
in-store. This brief targets the web-visible signal (Square Online) to infer
the in-store technology stack. A "confirmed" Square Online presence is a strong
indicator that the business is a Square POS customer across their operation.

This data is useful for:
- Sales outreach for POS-adjacent products and services
- Market sizing of Square's presence in a geographic area
- Competitive analysis against other POS platforms
