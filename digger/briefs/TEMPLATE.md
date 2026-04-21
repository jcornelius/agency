# Brief: [Project Name]

## Goal

[One sentence: what are you looking for and where?]

---

## Search Terms

Run these with `web_search` (Brave). Work through them in order.

```
[search term 1]
[search term 2]
[search term 3]
```

---

## Keywords to Find

Look for these exact strings in the page HTML source.

### Primary (any one = "confirmed")

- [strong indicator 1, e.g. meta tag, domain pattern, script source]
- [strong indicator 2]

### Secondary (2+ = "likely", 1 = "possible")

- [weaker indicator 1, e.g. branded text, CSS classes, link patterns]
- [weaker indicator 2]

### False Positives — Ignore These

- [thing that looks like a match but isn't]

---

## Business Types

- [type 1]
- [type 2]

---

## Geography

[City/region and any sub-areas to cover]

---

## CSV Output

**File:** `research/[project-name].csv`

**Headers:**
```
business_name,business_type,address,city,state,zip,phone,email,contact_name,website,keywords_found,confidence,search_term_used,date_found,notes
```

Add or remove columns as needed for the project. The prospect-researcher
skill will use these headers when creating the CSV.
