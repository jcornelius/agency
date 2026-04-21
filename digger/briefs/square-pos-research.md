---
name: square-pos-research
description: >
  Research brief: find restaurants and food businesses using Square POS/Online
  in Atlanta, GA. Triggers: "find Square restaurants", "Square POS prospects",
  "square-pos-research".
---

# Brief: Square POS — Atlanta Restaurants

## Goal

Find restaurants and food service businesses in the Atlanta metro area that
use Square for online ordering or point-of-sale.

---

## Search Keywords

pizza, pizzeria, coffee, coffee shop, bakery, cafe, restaurant, brunch, juice bar, food truck, dessert, ice cream

## Search Areas

Atlanta, Decatur, Sandy Springs, Roswell, Marietta, Alpharetta, Smyrna, Kennesaw, Duluth, Lawrenceville, Stone Mountain

---

## Search Terms (Legacy)

These are used if `--keywords` and `--areas` are not provided.

```
site:square.site restaurant Atlanta
site:square.site pizza Atlanta
site:square.site coffee Atlanta
site:square.site bakery Atlanta
"powered by Square Online" restaurant Atlanta
"powered by Square Online" pizza Atlanta
"powered by Square Online" coffee Atlanta
"order online" restaurant Atlanta square
restaurant "order online" Midtown Atlanta
pizza delivery Buckhead Atlanta "square"
coffee shop Decatur GA "square.site"
restaurant East Atlanta Village "square.site"
restaurant Sandy Springs GA "square.site"
restaurant Roswell GA "square.site"
restaurant Marietta GA "square.site"
```

---

## Keywords to Find

Look for these exact strings in the page HTML source. Listed strongest first.

**Note:** Many businesses use a custom domain (e.g. `joespizza.com`) instead of a
`*.square.site` URL. These can be detected by checking the `<head>` section for
`<meta name="generator" content="Square Online">`. If that meta tag is present,
the business is using Square Online regardless of their URL.

### Primary (any one = "confirmed")

- `<meta name="generator" content="Square Online">` — works on custom domains too
- URL hosted on `*.square.site`
- Script src containing `js.squareup.com`
- Resources from `cdn.squareup.com` or `square-cdn.com`

### Secondary (2+ = "likely", 1 = "possible")

- `checkout.square.site` or `squareup.com/pay`
- `squareup.com/appointments` or `book.squareup.com`
- CSS classes starting with `sq-` (e.g. `sq-widget`, `sq-card-form`)
- HTML attributes like `data-sq-*`
- Text: "Powered by Square" or "Powered by Square Online"
- URL containing `ordering.square.site`
- Links to `squareup.com/gift` or `gift.square.site`

### False Positives — Ignore These

- **Squarespace** (`squarespace.com`) — different company entirely
- **Square Enix** — video game company
- **"Square feet"** — real estate term
- **Square Capital / Banking** — financial products, not POS

---

## Business Types

- Restaurants (full service and fast casual)
- Pizzerias
- Coffee shops and cafes
- Bakeries
- Juice bars and smoothie shops
- Food trucks (with web presence)
- Ice cream and dessert shops

---

## Geography

Atlanta, GA metro area including:
- Atlanta proper (Midtown, Buckhead, Downtown, West End, East Atlanta)
- Decatur, Sandy Springs, Roswell, Marietta, Alpharetta
- Smyrna, Kennesaw, Duluth, Lawrenceville, Stone Mountain

---

## Website Discovery

After a business is confirmed as a Square user and looked up on Google Places,
the script searches for the business's primary website (custom domain) if one
wasn't returned by Google Places.

**How it works:**
1. If the `website` field is empty or points to `*.square.site`, the script
   runs a Brave search for `"{business_name}" {city} {state}`
2. Results are filtered to exclude aggregator sites (Yelp, DoorDash, Facebook,
   etc.) and Square's own domains
3. The first remaining result is used as the primary website URL

**Backfill existing CSV:** To retroactively find websites for businesses already
in the CSV, run:

```bash
exec python3 -u scripts/prospect-search.py briefs/square-pos-research.md \
  --csv research/square-pos-atlanta.csv --enrich-websites
```

Add `--dry-run` to preview without modifying the CSV.

---

## CSV Output

**File:** `research/square-pos-atlanta.csv`

**Headers:**
```
business_name,business_type,address,city,state,zip,phone,email,contact_name,website,square_url,keywords_found,confidence,search_term_used,date_found,notes
```

| Column | Example |
|--------|---------|
| `business_name` | Joe's Pizza |
| `business_type` | pizzeria |
| `address` | 123 Peachtree St NE |
| `city` | Atlanta |
| `state` | GA |
| `zip` | 30308 |
| `phone` | (404) 555-1234 |
| `email` | info@joespizza.com |
| `contact_name` | Joe Smith |
| `website` | https://joespizza.com |
| `square_url` | https://joespizza.square.site |
| `keywords_found` | meta generator; cdn.squareup.com |
| `confidence` | confirmed |
| `search_term_used` | site:square.site pizza Atlanta |
| `date_found` | 2026-03-05 |
| `notes` | Also has Square gift cards |
