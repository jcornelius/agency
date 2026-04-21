#!/usr/bin/env python3
"""
Prospect Researcher — searches Brave for businesses, checks their websites
for keywords, and uses Google Places (goplaces) to get structured contact info.

Usage:
    # Legacy mode (search terms from brief):
    python3 prospect-search.py <brief.md> [--csv output.csv] [--dry-run]

    # Keyword × Area mode (generates two-pass search combos):
    python3 prospect-search.py <brief.md> --keywords "pizza,coffee" --areas "Atlanta,Roswell GA" [--csv output.csv] [--dry-run]

Reads keyword matching rules (primary/secondary/false-positive) from a research
brief markdown file. Search terms are either from the brief or generated
dynamically from --keywords × --areas.
"""

import argparse
import csv
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
import urllib.parse
import urllib.error
from datetime import date
from pathlib import Path

# Import HubSpot client for migration
try:
    from hubspot_client import HubSpotClient
except ImportError:
    HubSpotClient = None


# TwentyClient removed — migrated to HubSpot

# --- REMOVED: class TwentyClient (deprecated) ---


class _UNUSED_TwentyClient:  # noqa — kept only as dead reference; do not use
    """DEPRECATED: Twenty CRM client. Use HubSpotClient instead."""

    def __init__(self, base_url, api_key):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key

    def _request(self, method, path, body=None, params=None):
        """Authenticated request to Twenty REST API. Returns parsed JSON or None."""
        url = f'{self.base_url}{path}'
        if params:
            url += '?' + urllib.parse.urlencode(params)
        data = json.dumps(body).encode('utf-8') if body else None
        req = urllib.request.Request(url, data=data, method=method, headers={
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'User-Agent': 'OpenClaw/1.0',
        })
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            if e.code == 429:
                print(f'  Twenty rate limit, waiting 60s...', file=sys.stderr)
                time.sleep(60)
                try:
                    with urllib.request.urlopen(req, timeout=15) as resp:
                        return json.loads(resp.read())
                except Exception:
                    return None
            body_text = ''
            try:
                body_text = e.read().decode('utf-8', errors='replace')[:300]
            except Exception:
                pass
            print(f'  Twenty API error {e.code}: {body_text}', file=sys.stderr)
            return None
        except Exception as e:
            print(f'  Twenty request failed: {e}', file=sys.stderr)
            return None

    def test_connection(self):
        """Verify API connectivity. Returns True if successful."""
        resp = self._request('GET', '/rest/companies', params={'limit': '1'})
        return resp is not None

    def find_company(self, name=None, domain=None):
        """Find existing company by name (exact) or domain. Returns company dict or None."""
        if domain:
            params = {
                'filter': f'domainName[eq]:{domain}',
                'limit': '1',
            }
            resp = self._request('GET', '/rest/companies', params=params)
            companies = (resp or {}).get('data', {}).get('companies', [])
            if companies:
                return companies[0]
        if name:
            params = {
                'filter': f'name[eq]:{name}',
                'limit': '5',
            }
            resp = self._request('GET', '/rest/companies', params=params)
            companies = (resp or {}).get('data', {}).get('companies', [])
            if companies:
                return companies[0]
        return None

    def create_company(self, payload):
        """Create a company. Returns created company dict or None."""
        resp = self._request('POST', '/rest/companies', body=payload)
        if resp and resp.get('data', {}).get('createCompany'):
            return resp['data']['createCompany']
        return None

    def update_company(self, company_id, payload):
        """Update a company. Returns updated company dict or None."""
        resp = self._request('PATCH', f'/rest/companies/{company_id}', body=payload)
        if resp and resp.get('data', {}).get('updateCompany'):
            return resp['data']['updateCompany']
        return None

    def list_companies(self, limit=60, cursor=None):
        """List companies with pagination. Returns (companies, next_cursor, has_more)."""
        params = {'limit': str(limit)}
        if cursor:
            params['starting_after'] = cursor
        resp = self._request('GET', '/rest/companies', params=params)
        if not resp:
            return [], None, False
        data = resp.get('data', {})
        companies = data.get('companies', [])
        page = resp.get('pageInfo', {})
        return companies, page.get('endCursor'), page.get('hasNextPage', False)

    def get_people_for_company(self, company_id):
        """Get people linked to a company. Returns list of person dicts."""
        params = {
            'filter': f'companyId[eq]:{company_id}',
            'limit': '5',
        }
        resp = self._request('GET', '/rest/people', params=params)
        return (resp or {}).get('data', {}).get('people', [])

    def create_person(self, payload):
        """Create a person. Returns created person dict or None."""
        resp = self._request('POST', '/rest/people', body=payload)
        if resp and resp.get('data', {}).get('createPerson'):
            return resp['data']['createPerson']
        return None


class _UNUSED_OnePageClient:  # noqa — retained for reference only; do not use
    """DEPRECATED: OnePageCRM client. Use HubSpotClient instead."""

    BASE_URL = 'https://app.onepagecrm.com/api/v3'

    def __init__(self, user_id, api_key):
        import base64
        creds = f'{user_id}:{api_key}'.encode('utf-8')
        self.auth_header = 'Basic ' + base64.b64encode(creds).decode('ascii')

    def _request(self, method, path, body=None, params=None):
        """Authenticated request to OnePageCRM API. Returns parsed JSON or None."""
        url = f'{self.BASE_URL}{path}'
        if params:
            url += '?' + urllib.parse.urlencode(params)
        data = json.dumps(body).encode('utf-8') if body else None
        req = urllib.request.Request(url, data=data, method=method, headers={
            'Authorization': self.auth_header,
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'User-Agent': 'OpenClaw/1.0',
        })
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            if e.code == 429:
                print(f'  OnePage rate limit, waiting 5s...', file=sys.stderr)
                time.sleep(5)
                try:
                    with urllib.request.urlopen(req, timeout=15) as resp:
                        return json.loads(resp.read())
                except Exception:
                    return None
            body_text = ''
            try:
                body_text = e.read().decode('utf-8', errors='replace')[:300]
            except Exception:
                pass
            print(f'  OnePage API error {e.code}: {body_text}', file=sys.stderr)
            return None
        except Exception as e:
            print(f'  OnePage request failed: {e}', file=sys.stderr)
            return None

    def test_connection(self):
        """Verify API connectivity. Returns True if successful."""
        resp = self._request('GET', '/companies.json', params={'per_page': '1'})
        return resp is not None and resp.get('status') == 0

    def find_company(self, name=None, domain=None):
        """Find existing company by name or domain. Returns company dict or None."""
        queries = []
        if domain:
            queries.append(domain)
        if name:
            queries.append(name)

        for query in queries:
            resp = self._request('GET', '/companies.json', params={
                'search': query,
                'per_page': '10',
            })
            if not resp or resp.get('status') != 0:
                continue
            data = resp.get('data', {})
            items = data.get('companies', []) if isinstance(data, dict) else []
            for item in items:
                company = item.get('company', item)
                c_name = (company.get('name') or '').strip().lower()
                c_url = (company.get('url') or '').strip().lower()
                # Exact match on name or domain in URL
                if name and c_name == name.strip().lower():
                    return company
                if domain and domain.lower() in c_url:
                    return company
        return None

    def create_company(self, payload):
        """Create a company by creating a placeholder contact with company_name.

        OnePageCRM requires a Contact to create a Company. We create a minimal
        contact, which implicitly creates the company, then update the company
        with the full payload (phone, url, address).
        Returns created company dict or None.
        """
        company_name = payload.get('name', '')
        if not company_name:
            return None

        # Create placeholder contact → implicitly creates the company
        contact_payload = {
            'first_name': company_name,
            'last_name': '(Business)',
            'company_name': company_name,
        }
        resp = self._request('POST', '/contacts.json', body=contact_payload)
        if not resp or resp.get('status') != 0:
            return None

        data = resp.get('data', {})
        company = data.get('company', {})
        company_id = company.get('id', '')
        if not company_id:
            # Try getting company_id from the contact
            contact = data.get('contact', {})
            company_id = contact.get('company_id', '')

        if not company_id:
            return None

        # Update the company with full details (phone, url, address)
        update_payload = {k: v for k, v in payload.items() if k != 'name'}
        if update_payload:
            self.update_company(company_id, update_payload)

        company['id'] = company_id
        company['name'] = company_name
        return company

    def update_company(self, company_id, payload):
        """Update a company (partial). Returns updated company dict or None."""
        resp = self._request('PUT', f'/companies/{company_id}.json',
                             body=payload, params={'partial': 'true'})
        if resp and resp.get('status') == 0:
            data = resp.get('data', {})
            return data.get('company', data)
        return None

    def list_companies(self, per_page=100, page=1):
        """List companies with pagination. Returns (companies, next_page, has_more)."""
        resp = self._request('GET', '/companies.json', params={
            'per_page': str(per_page),
            'page': str(page),
        })
        if not resp or resp.get('status') != 0:
            return [], None, False
        data = resp.get('data', {})
        items = data.get('companies', []) if isinstance(data, dict) else []
        companies = [item.get('company', item) for item in items]
        max_page = data.get('max_page', 1) if isinstance(data, dict) else 1
        has_more = page < max_page
        next_page = page + 1 if has_more else None
        return companies, next_page, has_more

    def get_people_for_company(self, company_id):
        """Get contacts linked to a company. Returns list of contact dicts."""
        resp = self._request('GET', '/contacts.json', params={
            'company_id': company_id,
            'per_page': '10',
        })
        if not resp or resp.get('status') != 0:
            return []
        data = resp.get('data', {})
        items = data.get('contacts', []) if isinstance(data, dict) else []
        return [item.get('contact', item) for item in items]

    def create_person(self, payload):
        """Create a contact. Returns created contact dict or None."""
        resp = self._request('POST', '/contacts.json', body=payload)
        if resp and resp.get('status') == 0:
            data = resp.get('data', {})
            return data.get('contact', data)
        return None


def normalize_phone_e164(phone):
    """Normalize a US phone number to E.164 format (+1XXXXXXXXXX)."""
    if not phone:
        return ''
    digits = re.sub(r'[^0-9]', '', phone)
    if len(digits) == 10:
        return f'+1{digits}'
    if len(digits) == 11 and digits.startswith('1'):
        return f'+{digits}'
    return ''


def build_company_payload(row):
    """Map a prospect CSV row to a HubSpot Company API payload."""
    website = (row.get('website') or '').strip()
    square_url = (row.get('square_url') or '').strip()
    confidence = (row.get('confidence') or '').strip()
    
    domain = ''
    if website:
        try:
            parsed = urllib.parse.urlparse(website if '://' in website else f'https://{website}')
            domain = (parsed.hostname or '').lower()
            if domain.startswith('www.'):
                domain = domain[4:]
        except Exception:
            pass

    phone = normalize_phone_e164((row.get('phone') or '').strip())

    # Build address string
    address_parts = []
    if row.get('address'):
        address_parts.append(row.get('address').strip())
    if row.get('city'):
        address_parts.append(row.get('city').strip())
    if row.get('state'):
        address_parts.append(row.get('state').strip())
    if row.get('zip'):
        address_parts.append(row.get('zip').strip())
    address = ', '.join(address_parts) if address_parts else ''

    # Determine Square confidence level
    square_confidence = 'needs_review'
    if square_url and website:
        # Has both - might be multi-platform
        square_confidence = 'multi_platform'
    elif square_url and not website:
        # Only has square.site
        square_confidence = 'has_square_site'
    elif square_url:
        # Has square URL - confirm it's square
        square_confidence = 'confirmed_square'
    
    # If confidence from CSV says "confirmed", upgrade to confirmed_square
    if confidence and 'confirm' in confidence.lower():
        square_confidence = 'confirmed_square'

    payload = {
        'name': (row.get('business_name') or '').strip(),
        'domain': domain,
        'phone': phone,
        'primary_website': website,  # Renamed from 'website' for clarity
        'address': address,
        'square_online_url': square_url,  # New field: Square URL
        'square_confidence': square_confidence,  # New field: Confidence level
        'keywords_found': (row.get('keywords_found') or '').strip(),
        'date_found': (row.get('date_found') or '').strip(),
    }

    return payload


def normalize_domain(website):
    """Extract bare domain from a website URL."""
    if not website:
        return ''
    try:
        parsed = urllib.parse.urlparse(website if '://' in website else f'https://{website}')
        domain = (parsed.hostname or '').lower()
        if domain.startswith('www.'):
            domain = domain[4:]
        return domain
    except Exception:
        return ''


def upsert_company_hubspot(hubspot, row):
    """Create or update a company in HubSpot. Returns (company_id, action) or (None, 'error')."""
    name = (row.get('business_name') or '').strip()
    domain = normalize_domain(row.get('website') or '')

    # Dedup: check domain first, then name
    existing = None
    if domain and '.square.site' not in domain:
        existing = hubspot.find_company(domain=domain)
    if not existing:
        existing = hubspot.find_company(name=name)

    payload = build_company_payload(row)

    if existing:
        company_id = existing.get('id')
        if not company_id:
            return None, 'error'
        result = hubspot.update_company(company_id, payload)
        if result:
            return company_id, 'updated'
        return None, 'error'
    else:
        result = hubspot.create_company(payload)
        if result and result.get('id'):
            return result['id'], 'created'
        return None, 'error'


def backfill_hubspot(csv_path, hubspot, dry_run=False):
    """Push all rows from an existing prospect CSV to HubSpot."""
    if not os.path.exists(csv_path):
        print(f'Error: CSV not found: {csv_path}', file=sys.stderr)
        return

    with open(csv_path, 'r') as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    total = len(rows)
    created = 0
    updated = 0
    errors = 0

    print(f'Backfilling {total} rows to HubSpot')
    print()

    for i, row in enumerate(rows):
        name = (row.get('business_name', '') or '').strip()
        print(f'--- [{i+1}/{total}] {name} ---')

        if dry_run:
            print(f'  [DRY RUN] Would upsert: {name}')
            continue

        company_id, action = upsert_company_hubspot(hubspot, row)
        if action == 'created':
            created += 1
            print(f'  HubSpot: created {company_id}')
        elif action == 'updated':
            updated += 1
            print(f'  HubSpot: updated {company_id}')
        else:
            errors += 1
            print(f'  HubSpot: failed')

        time.sleep(0.6)

        if (i + 1) % 10 == 0:
            print(f'  ... {i+1}/{total} processed, {created} created, {updated} updated ...')

    print()
    print(f'Done.')
    print(f'  Created: {created}')
    print(f'  Updated: {updated}')
    print(f'  Errors: {errors}')
    print()
    print(f'=== COMPLETE: {created} created, {updated} updated in HubSpot ===')


# --- REMOVED: OnePageCRM payload/upsert/backfill functions (use HubSpot equivalents) ---


def build_company_payload_onepage(row):  # DEPRECATED — do not call
    """Map a prospect CSV row to a OnePageCRM Company API payload."""
    payload = {
        'name': (row.get('business_name') or '').strip(),
    }

    website = (row.get('website') or '').strip()
    if website:
        if '://' not in website:
            website = f'https://{website}'
        payload['url'] = website

    phone = (row.get('phone') or '').strip()
    if phone:
        payload['phone'] = phone

    address = (row.get('address') or '').strip()
    city = (row.get('city') or '').strip()
    state = (row.get('state') or '').strip()
    zipcode = (row.get('zip') or '').strip()
    if address or city:
        payload['address'] = {
            'address': address,
            'city': city,
            'state': state,
            'zip_code': zipcode,
            'country_code': 'US',
        }

    return payload


def upsert_company_onepage(onepage, row):
    """Create or update a company in OnePageCRM. Returns (company_id, action) or (None, 'error')."""
    name = (row.get('business_name') or '').strip()
    website = (row.get('website') or '').strip()
    domain = normalize_domain(website) if website else ''

    # Dedup: check domain first, then name
    existing = None
    if domain and '.square.site' not in domain:
        existing = onepage.find_company(domain=domain)
    if not existing:
        existing = onepage.find_company(name=name)

    payload = build_company_payload_onepage(row)

    if existing:
        company_id = existing['id']
        result = onepage.update_company(company_id, payload)
        if result:
            return company_id, 'updated'
        return None, 'error'
    else:
        result = onepage.create_company(payload)
        if result and result.get('id'):
            return result['id'], 'created'
        return None, 'error'


def backfill_onepage(csv_path, onepage, dry_run=False):
    """Push all rows from an existing prospect CSV to OnePageCRM."""
    if not os.path.exists(csv_path):
        print(f'Error: CSV not found: {csv_path}', file=sys.stderr)
        return

    with open(csv_path, 'r') as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    total = len(rows)
    created = 0
    updated = 0
    errors = 0

    print(f'Backfilling {total} rows to OnePageCRM')
    print()

    for i, row in enumerate(rows):
        name = (row.get('business_name', '') or '').strip()
        print(f'--- [{i+1}/{total}] {name} ---')

        if dry_run:
            print(f'  [DRY RUN] Would upsert: {name}')
            continue

        company_id, action = upsert_company_onepage(onepage, row)
        if action == 'created':
            created += 1
            print(f'  OnePage: created {company_id}')
        elif action == 'updated':
            updated += 1
            print(f'  OnePage: updated {company_id}')
        else:
            errors += 1
            print(f'  OnePage: failed')

        time.sleep(0.1)

        if (i + 1) % 10 == 0:
            print(f'  ... {i+1}/{total} processed, {created} created, {updated} updated ...')

    print()
    print(f'Done.')
    print(f'  Created: {created}')
    print(f'  Updated: {updated}')
    print(f'  Errors: {errors}')
    print()
    print(f'=== COMPLETE: {created} created, {updated} updated in OnePage ===')


def load_brief(path):
    """Parse a research brief markdown file for search terms, keywords, and areas."""
    text = Path(path).read_text()

    # Extract search terms (lines inside ``` blocks under "## Search Terms")
    search_terms = []
    in_search = False
    in_code = False
    for line in text.splitlines():
        if re.match(r'^##\s+Search Terms', line, re.IGNORECASE):
            in_search = True
            continue
        if in_search and line.strip().startswith('```'):
            in_code = not in_code
            continue
        if in_search and in_code and line.strip():
            search_terms.append(line.strip())
        if in_search and not in_code and line.startswith('## ') and 'Search' not in line:
            in_search = False

    # Extract search keywords (comma-separated or bullet list under "## Search Keywords")
    search_keywords = []
    in_kw_section = False
    for line in text.splitlines():
        if re.match(r'^##\s+Search Keywords', line, re.IGNORECASE):
            in_kw_section = True
            continue
        if in_kw_section and line.startswith('## '):
            in_kw_section = False
            continue
        if in_kw_section and line.strip():
            stripped = line.strip().lstrip('- ').strip()
            if not stripped or stripped.startswith('```'):
                continue
            # Handle comma-separated on a single line
            if ',' in stripped:
                for kw in stripped.split(','):
                    kw = kw.strip()
                    if kw:
                        search_keywords.append(kw)
            else:
                search_keywords.append(stripped)

    # Extract search areas (comma-separated or bullet list under "## Search Areas")
    search_areas = []
    in_area_section = False
    for line in text.splitlines():
        if re.match(r'^##\s+Search Areas', line, re.IGNORECASE):
            in_area_section = True
            continue
        if in_area_section and line.startswith('## '):
            in_area_section = False
            continue
        if in_area_section and line.strip():
            stripped = line.strip().lstrip('- ').strip()
            if not stripped or stripped.startswith('```'):
                continue
            if ',' in stripped:
                for area in stripped.split(','):
                    area = area.strip()
                    if area:
                        search_areas.append(area)
            else:
                search_areas.append(stripped)

    # Extract primary keywords (lines starting with - under "### Primary")
    primary_keywords = []
    in_primary = False
    for line in text.splitlines():
        if re.match(r'^###\s+Primary', line, re.IGNORECASE):
            in_primary = True
            continue
        if in_primary and line.startswith('### '):
            in_primary = False
            continue
        if in_primary and line.strip().startswith('- '):
            # Extract the keyword pattern — handle backtick-wrapped and plain text
            kw = line.strip().lstrip('- ').strip()
            # Pull out backtick content if present
            backtick_matches = re.findall(r'`([^`]+)`', kw)
            if backtick_matches:
                for m in backtick_matches:
                    primary_keywords.append(m)
            else:
                # Clean up markdown formatting
                kw = re.sub(r'\*\*.*?\*\*', '', kw).strip()
                if kw:
                    primary_keywords.append(kw)

    # Extract secondary keywords
    secondary_keywords = []
    in_secondary = False
    for line in text.splitlines():
        if re.match(r'^###\s+Secondary', line, re.IGNORECASE):
            in_secondary = True
            continue
        if in_secondary and line.startswith('### '):
            in_secondary = False
            continue
        if in_secondary and line.strip().startswith('- '):
            kw = line.strip().lstrip('- ').strip()
            backtick_matches = re.findall(r'`([^`]+)`', kw)
            if backtick_matches:
                for m in backtick_matches:
                    secondary_keywords.append(m)
            else:
                kw = re.sub(r'\*\*.*?\*\*', '', kw).strip()
                if kw:
                    secondary_keywords.append(kw)

    # Extract false positives to ignore
    false_positives = []
    in_false = False
    for line in text.splitlines():
        if re.match(r'^###\s+False Positive', line, re.IGNORECASE):
            in_false = True
            continue
        if in_false and line.startswith('## '):
            in_false = False
            continue
        if in_false and line.strip().startswith('- '):
            kw = line.strip().lstrip('- ').strip()
            backtick_matches = re.findall(r'`([^`]+)`', kw)
            if backtick_matches:
                for m in backtick_matches:
                    false_positives.append(m.lower())
            else:
                bold = re.findall(r'\*\*([^*]+)\*\*', kw)
                if bold:
                    false_positives.append(bold[0].lower())

    # Extract CSV output filename
    csv_file = None
    for line in text.splitlines():
        m = re.search(r'\*\*File:\*\*\s*`([^`]+)`', line)
        if m:
            csv_file = m.group(1)
            break

    return {
        'search_terms': search_terms,
        'search_keywords': search_keywords,
        'search_areas': search_areas,
        'primary_keywords': primary_keywords,
        'secondary_keywords': secondary_keywords,
        'false_positives': false_positives,
        'csv_file': csv_file,
    }


def brave_search(query, api_key, count=20):
    """Search Brave and return list of {url, title, description}."""
    params = urllib.parse.urlencode({'q': query, 'count': count})
    url = f'https://api.search.brave.com/res/v1/web/search?{params}'
    req = urllib.request.Request(url, headers={
        'Accept': 'application/json',
        'X-Subscription-Token': api_key,
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        results = []
        for r in data.get('web', {}).get('results', []):
            results.append({
                'url': r.get('url', ''),
                'title': r.get('title', ''),
                'description': r.get('description', ''),
            })
        return results
    except Exception as e:
        print(f'  ⚠ Brave search failed: {e}', file=sys.stderr)
        return []


def fetch_page(url, timeout=10):
    """Fetch a URL and return the HTML source as a string."""
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                       'AppleWebKit/537.36 (KHTML, like Gecko) '
                       'Chrome/120.0.0.0 Safari/537.36',
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode('utf-8', errors='replace')
    except Exception:
        return ''


def check_keywords(html, primary_keywords, secondary_keywords, false_positives):
    """Check HTML for keyword matches. Returns (matched_keywords, confidence)."""
    html_lower = html.lower()

    # Check false positives first
    for fp in false_positives:
        if fp in html_lower:
            return [], None

    matched = []
    primary_count = 0
    secondary_count = 0

    for kw in primary_keywords:
        if kw.lower() in html_lower:
            matched.append(kw)
            primary_count += 1

    for kw in secondary_keywords:
        if kw.lower() in html_lower:
            matched.append(kw)
            secondary_count += 1

    if not matched:
        return [], None

    if primary_count >= 1:
        confidence = 'confirmed'
    elif secondary_count >= 2:
        confidence = 'likely'
    else:
        confidence = 'possible'

    return matched, confidence


def check_url_keywords(url, primary_keywords):
    """Check if the URL itself matches any primary keywords (e.g. *.square.site)."""
    url_lower = url.lower()
    matched = []
    for kw in primary_keywords:
        kw_check = kw.lower()
        # Handle domain patterns like "*.square.site"
        if kw_check.startswith('*.'):
            domain = kw_check[2:]
            if domain in url_lower:
                matched.append(kw)
        elif kw_check in url_lower:
            matched.append(kw)
    return matched


def goplaces_search(business_name, city, state=''):
    """Use goplaces CLI to get structured business info from Google Places."""
    query = f'{business_name} {city}'
    if state:
        query += f' {state}'
    try:
        result = subprocess.run(
            ['goplaces', 'search', query, '--json', '--limit', '1'],
            capture_output=True, text=True, timeout=15,
            env={**os.environ, 'GOOGLE_PLACES_API_KEY': os.environ.get('GOOGLE_PLACES_API_KEY', '')},
        )
        if result.returncode != 0:
            return None
        data = json.loads(result.stdout)
        if not data:
            return None
        place = data[0]

        # Get details for phone number
        place_id = place.get('place_id')
        if place_id:
            detail_result = subprocess.run(
                ['goplaces', 'details', place_id, '--json'],
                capture_output=True, text=True, timeout=15,
                env={**os.environ, 'GOOGLE_PLACES_API_KEY': os.environ.get('GOOGLE_PLACES_API_KEY', '')},
            )
            if detail_result.returncode == 0:
                detail = json.loads(detail_result.stdout)
                place.update(detail)

        return place
    except Exception as e:
        print(f'  ⚠ goplaces failed: {e}', file=sys.stderr)
        return None


def parse_address(full_address):
    """Parse a Google Places address string into components."""
    # Typical format: "123 Main St, Atlanta, GA 30308, USA"
    parts = [p.strip() for p in full_address.split(',')]
    address = parts[0] if len(parts) > 0 else ''
    city = parts[1] if len(parts) > 1 else ''
    state_zip = parts[2] if len(parts) > 2 else ''
    state = ''
    zipcode = ''
    if state_zip:
        sz = state_zip.strip().split()
        if len(sz) >= 1:
            state = sz[0]
        if len(sz) >= 2:
            zipcode = sz[1]
    return address, city, state, zipcode


def is_duplicate(csv_path, business_name, address='', url=''):
    """Check if a business at this specific address already exists in the CSV.

    Deduplicates on name + physical address, so the same business at
    different locations will each get their own row.
    """
    if not os.path.exists(csv_path):
        return False
    try:
        with open(csv_path, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                row_name = (row.get('business_name', '') or '').lower().strip()
                row_addr = (row.get('address', '') or '').lower().strip()
                row_url = (row.get('square_url', '') or '').lower().strip()
                name_match = business_name.lower().strip() in row_name or row_name in business_name.lower().strip()
                # If name matches AND address matches (or both blank), it's a dup
                if name_match:
                    if address and row_addr:
                        if address.lower().strip() == row_addr:
                            return True
                    elif not address and not row_addr:
                        # Both blank — check URL instead
                        if url and url.lower().strip() == row_url:
                            return True
                        elif not url:
                            return True
                # Also check URL to catch same site with different page titles
                if url and row_url and url.lower().strip() == row_url:
                    return True
    except Exception:
        pass
    return False


def append_csv(csv_path, row):
    """Append a row to the CSV file. Creates with headers if needed."""
    headers = [
        'business_name', 'business_type', 'address', 'city', 'state', 'zip',
        'phone', 'email', 'contact_name', 'website', 'square_url',
        'keywords_found', 'confidence', 'search_term_used', 'date_found', 'notes'
    ]
    write_header = not os.path.exists(csv_path) or os.path.getsize(csv_path) == 0
    with open(csv_path, 'a', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=headers, quoting=csv.QUOTE_ALL)
        if write_header:
            writer.writeheader()
        writer.writerow(row)


def extract_business_name_from_url(url):
    """Try to extract a readable business name from a square.site URL."""
    # https://joespizza.square.site/ -> joespizza -> Joe's Pizza (rough)
    from urllib.parse import urlparse
    parsed = urlparse(url)
    hostname = parsed.hostname or ''
    if '.square.site' in hostname:
        name = hostname.replace('.square.site', '')
        # Convert hyphens to spaces and title-case
        name = name.replace('-', ' ').title()
        return name
    return ''


# Domains to skip when looking for a business's primary website.
# These are aggregators, social media, review sites, delivery platforms, etc.
SKIP_DOMAINS = {
    'square.site', 'squareup.com', 'squarespace.com',
    'facebook.com', 'fb.com', 'instagram.com', 'twitter.com', 'x.com',
    'tiktok.com', 'youtube.com', 'pinterest.com', 'linkedin.com',
    'yelp.com', 'tripadvisor.com', 'google.com',
    'doordash.com', 'ubereats.com', 'grubhub.com', 'postmates.com',
    'seamless.com', 'eat24.com', 'slicelife.com',
    'yellowpages.com', 'bbb.org', 'manta.com', 'chamberofcommerce.com',
    'mapquest.com', 'foursquare.com', 'zomato.com',
    'nextdoor.com', 'patch.com',
    'menuism.com', 'menupages.com', 'allmenus.com', 'zmenu.com', 'sirved.com',
    'opentable.com', 'resy.com', 'toasttab.com', 'clover.com',
    'apple.com', 'apps.apple.com', 'play.google.com',
    'wikipedia.org', 'reddit.com', 'github.com',
    'michelin.com', 'eater.com', 'timeout.com', 'thrillist.com',
    'infatuation.com', 'zagat.com', 'thedailymeal.com',
    'ajc.com', 'accessatlanta.com', 'atlantamagazine.com',
    'nytimes.com', 'washingtonpost.com', 'cnn.com',
    'restaurantji.com', 'menupix.com', 'caviar.com',
    # Generic directories and platforms
    'restaurant.com', 'order.online', 'wheree.com',
    'local.yahoo.com', 'yahoo.com', 'bing.com',
    'zip-codes.com', 'loopnet.com', 'indeed.com', 'glassdoor.com',
    'atlantacoffeeshops.com', 'atlantadowntown.com',
    'visitathensga.com', 'exploregeorgia.org',
    'chamberofcommerce.com', 'alignable.com',
    'stereogum.com', 'buzzfeed.com', 'huffpost.com',
    'grubstreet.com', 'food52.com', 'bonappetit.com',
    'findmeglutenfree.com', 'happycow.net', 'beyondmenu.com',
    'smartrecruiters.com', 'popmenu.com',
    # Ordering/blog platforms (subdomains contain business name but aren't primary sites)
    'netwaiter.com', 'res-discover.com', 'exur.com', 'substack.com',
    'wixsite.com', 'weebly.com', 'godaddysites.com',
    'roadtrippers.com', 'wanderlog.com',
    'com-fnb.com', 'chownow.com', 'online-ordering.com',
}


def _business_name_words(name):
    """Extract meaningful words (3+ chars) from a business name for matching."""
    name = name.lower()
    name = re.sub(r"['\u2019\u2018]s?\b", '', name)
    name = re.sub(r'[^a-z0-9\s]', '', name)
    # Filter out very common words that appear in unrelated domains
    stop_words = {
        'the', 'and', 'inc', 'llc', 'ltd', 'company', 'cafe', 'coffee',
        'pizza', 'restaurant', 'bakery', 'grill', 'bar', 'shop',
        'food', 'kitchen', 'house', 'place', 'truck', 'stand',
    }
    return [w for w in name.split() if len(w) >= 3 and w not in stop_words]


def find_primary_website(business_name, city, state, brave_key):
    """Search for a business's primary website using Brave.

    Does a name+location search, filters out aggregator/social/review sites,
    and returns the first result that looks like the business's own website.
    Uses a two-pass approach: first looks for domains containing words from
    the business name, then falls back to the first non-aggregator result.
    Returns URL string or empty string.
    """
    query = f'{business_name} {city} {state}'
    results = brave_search(query, brave_key, count=10)

    if not results:
        return ''

    name_words = _business_name_words(business_name)
    candidates = []  # (url, has_name_match) tuples

    for r in results:
        url = r['url']
        try:
            parsed = urllib.parse.urlparse(url)
            hostname = (parsed.hostname or '').lower()
            if hostname.startswith('www.'):
                hostname = hostname[4:]
        except Exception:
            continue

        # Skip known non-primary domains
        if any(skip_d in hostname for skip_d in SKIP_DOMAINS):
            continue

        # Check if any business name word appears in the domain
        domain_base = hostname.split('.')[0]  # e.g. "fellinisatlanta"
        has_name_match = any(w in domain_base for w in name_words)
        candidates.append((f'{parsed.scheme}://{parsed.hostname}', has_name_match))

    # Only return domains that contain words from the business name
    for url, has_match in candidates:
        if has_match:
            return url

    return ''


def enrich_websites(csv_path, brave_key, dry_run=False):
    """Backfill missing websites in an existing prospect CSV.

    Reads the CSV, searches for primary websites where the website column
    is empty or points to square.site, and rewrites the CSV with updates.
    """
    if not os.path.exists(csv_path):
        print(f'Error: CSV not found: {csv_path}', file=sys.stderr)
        return

    # Read all rows
    with open(csv_path, 'r') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    total = len(rows)
    needs_update = 0
    updated = 0

    print(f'Enriching websites in {csv_path} ({total} rows)')
    print()

    for i, row in enumerate(rows):
        name = (row.get('business_name', '') or '').strip()
        website = (row.get('website', '') or '').strip()
        city = (row.get('city', '') or '').strip()
        state = (row.get('state', '') or '').strip()

        # Skip if already has a real website
        if website and '.square.site' not in website.lower():
            continue

        needs_update += 1
        print(f'--- [{i+1}/{total}] {name} ---')

        if not city:
            print(f'  ⏭ No city, skipping')
            continue

        if dry_run:
            print(f'  [DRY RUN] Would search for primary website')
            continue

        found = find_primary_website(name, city, state, brave_key)
        time.sleep(1)  # Rate limit

        if found:
            rows[i]['website'] = found
            updated += 1
            print(f'  🌐 Found: {found}')
        else:
            print(f'  🌐 No primary website found')

        # Heartbeat every 10 rows
        if needs_update % 10 == 0:
            print(f'  ... {needs_update} checked, {updated} updated ...')

    if not dry_run and updated > 0:
        # Write back the full CSV with updates
        with open(csv_path, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames,
                                    quoting=csv.QUOTE_ALL)
            writer.writeheader()
            writer.writerows(rows)

    print()
    print(f'Done.')
    print(f'  Rows checked: {needs_update} / {total}')
    print(f'  Websites found: {updated}')
    print(f'  CSV: {csv_path}')
    print()
    print(f'=== COMPLETE: {updated} websites added, {total} total rows ===')


def parse_search_area(area_str):
    """Parse an area string into (city, state).

    Examples:
        "Atlanta" → ("Atlanta", "")
        "Roswell GA" → ("Roswell", "GA")
        "Sandy Springs, GA" → ("Sandy Springs", "GA")
        "30308" → ("30308", "")
    """
    area_str = area_str.strip()
    # Handle "City, ST" format
    if ',' in area_str:
        parts = [p.strip() for p in area_str.split(',', 1)]
        return parts[0], parts[1] if len(parts) > 1 else ''
    # Handle "City ST" format (last token is 2-letter state)
    parts = area_str.rsplit(None, 1)
    if len(parts) == 2 and len(parts[1]) == 2 and parts[1].isalpha():
        return parts[0], parts[1].upper()
    return area_str, ''


def generate_search_terms(keywords, areas):
    """Generate two-pass search terms from keywords × areas cross-product.

    Pass 1: site:square.site {keyword} {area}  — targeted, fast
    Pass 2: {keyword} {area} "square online"   — catches custom domains

    Returns list of (search_query, area_string) tuples.
    """
    terms = []

    # Pass 1 — targeted (square.site URLs)
    for area in areas:
        for kw in keywords:
            terms.append((f'site:square.site {kw} {area}', area))

    # Pass 2 — custom domain discovery
    for area in areas:
        for kw in keywords:
            terms.append((f'{kw} {area} "square online"', area))

    return terms


def main():
    parser = argparse.ArgumentParser(description='Prospect Researcher')
    parser.add_argument('brief', help='Path to research brief markdown file')
    parser.add_argument('--csv', help='Output CSV path (overrides brief)')
    parser.add_argument('--dry-run', action='store_true', help='Print matches without writing')
    parser.add_argument('--skip-terms', type=int, default=0, help='Skip first N search terms')
    parser.add_argument('--keywords', help='Comma-separated search keywords (e.g. "pizza,coffee,bakery")')
    parser.add_argument('--areas', help='Comma-separated search areas (e.g. "Atlanta,Roswell GA,Decatur GA")')
    parser.add_argument('--enrich-websites', action='store_true',
                        help='Backfill missing websites in an existing CSV (no new searches)')
    parser.add_argument('--sync-to-hubspot', action='store_true',
                        help='Sync confirmed prospects to HubSpot (in addition to CSV)')
    parser.add_argument('--backfill-hubspot', action='store_true',
                        help='Push existing CSV rows into HubSpot')
    parser.add_argument('--twenty', action='store_true', dest='sync_to_hubspot',
                        help='[DEPRECATED] Use --sync-to-hubspot. Kept for backward compat.')
    parser.add_argument('--twenty-backfill', action='store_true', dest='backfill_hubspot',
                        help='[DEPRECATED] Use --backfill-hubspot. Kept for backward compat.')
    args = parser.parse_args()

    # Load config — prefer env vars, fall back to ~/.openclaw/openclaw.json for back-compat.
    brave_key = os.environ.get('BRAVE_API_KEY') or None
    config = {}
    config_path = os.path.expanduser('~/.openclaw/openclaw.json')
    if os.path.exists(config_path):
        with open(config_path) as f:
            config = json.load(f)
        if not brave_key:
            brave_key = config.get('tools', {}).get('web', {}).get('search', {}).get('apiKey')
        if not os.environ.get('GOOGLE_PLACES_API_KEY'):
            places_key = config.get('env', {}).get('GOOGLE_PLACES_API_KEY')
            if places_key:
                os.environ['GOOGLE_PLACES_API_KEY'] = places_key

    if not brave_key:
        print('Error: No Brave API key — set BRAVE_API_KEY env var or add to ~/.openclaw/openclaw.json',
              file=sys.stderr)
        sys.exit(1)

    if not os.environ.get('GOOGLE_PLACES_API_KEY'):
        print('Error: No GOOGLE_PLACES_API_KEY found', file=sys.stderr)
        sys.exit(1)

    # Initialize HubSpot client if needed
    hubspot = None
    if args.sync_to_hubspot or args.backfill_hubspot:
        hubspot_token = os.environ.get('HUBSPOT_PRIVATE_APP_TOKEN') or \
                        config.get('env', {}).get('HUBSPOT_PRIVATE_APP_TOKEN', '')
        if not hubspot_token:
            print('Error: HUBSPOT_PRIVATE_APP_TOKEN required in environment or openclaw.json',
                  file=sys.stderr)
            sys.exit(1)
        if not HubSpotClient:
            print('Error: hubspot_client module not found',
                  file=sys.stderr)
            sys.exit(1)
        try:
            hubspot = HubSpotClient(hubspot_token)
            if not hubspot.test_connection():
                print('Error: Cannot connect to HubSpot', file=sys.stderr)
                sys.exit(1)
            print(f'  HubSpot: connected')
        except Exception as e:
            print(f'Error: HubSpot initialization failed: {e}', file=sys.stderr)
            sys.exit(1)

    onepage = None  # OnePageCRM removed — use HubSpot

    # Load brief
    brief = load_brief(args.brief)

    csv_path = args.csv or brief.get('csv_file') or 'research/output.csv'
    os.makedirs(os.path.dirname(csv_path) or '.', exist_ok=True)

    # ---- Enrich-websites mode ----
    if args.enrich_websites:
        enrich_websites(csv_path, brave_key, dry_run=args.dry_run)
        return

    # ---- HubSpot backfill mode ----
    if args.backfill_hubspot:
        backfill_hubspot(csv_path, hubspot, dry_run=args.dry_run)
        return



    # Resolve search keywords: CLI > brief > none
    keywords = None
    if args.keywords:
        keywords = [k.strip() for k in args.keywords.split(',') if k.strip()]
    elif brief.get('search_keywords'):
        keywords = brief['search_keywords']

    # Resolve search areas: CLI > brief > none
    areas = None
    if args.areas:
        areas = [a.strip() for a in args.areas.split(',') if a.strip()]
    elif brief.get('search_areas'):
        areas = brief['search_areas']

    # Generate search plan
    if keywords and areas:
        # Keyword × Area mode: two-pass cross-product
        search_plan = generate_search_terms(keywords, areas)
        mode = 'keyword × area'
        print(f'Brief loaded:')
        print(f'  Mode: {mode} (two-pass)')
        print(f'  Keywords: {", ".join(keywords)} ({len(keywords)})')
        print(f'  Areas: {", ".join(areas)} ({len(areas)})')
        print(f'  Search terms: {len(search_plan)} ({len(keywords)} × {len(areas)} × 2 passes)')
        print(f'  Primary match keywords: {len(brief["primary_keywords"])}')
        print(f'  Secondary match keywords: {len(brief["secondary_keywords"])}')
        print(f'  Output: {csv_path}')
    elif brief['search_terms']:
        # Legacy mode: use search terms from brief
        search_plan = [(term, '') for term in brief['search_terms']]
        mode = 'legacy (brief search terms)'
        print(f'Brief loaded:')
        print(f'  Mode: {mode}')
        print(f'  Search terms: {len(search_plan)}')
        print(f'  Primary match keywords: {len(brief["primary_keywords"])}')
        print(f'  Secondary match keywords: {len(brief["secondary_keywords"])}')
        print(f'  Output: {csv_path}')
    else:
        print('Error: No search terms found. Provide --keywords + --areas, or add Search Keywords/Areas sections to the brief.', file=sys.stderr)
        sys.exit(1)

    print()

    total_searched = 0
    total_inspected = 0
    total_matches = 0

    # Count existing CSV rows for baseline
    csv_baseline = 0
    if os.path.exists(csv_path):
        with open(csv_path, 'r') as f:
            csv_baseline = max(0, sum(1 for _ in f) - 1)  # minus header
    print(f'CSV baseline: {csv_baseline} rows')

    # Apply skip-terms
    search_plan = search_plan[args.skip_terms:]
    total_terms = len(search_plan)

    # Counter for heartbeat every 10 inspected entries
    inspected_since_heartbeat = 0

    for i, (term, search_area) in enumerate(search_plan):
        print(f'--- Searching "{term}" [{i+1}/{total_terms}] ---')
        results = brave_search(term, brave_key)
        total_searched += 1

        if not results:
            print(f'  No results')
            time.sleep(1)
            continue

        print(f'  {len(results)} results')

        # Parse the search area for goplaces context
        if search_area:
            area_city, area_state = parse_search_area(search_area)
        else:
            area_city, area_state = 'Atlanta', 'GA'

        for r in results:
            url = r['url']
            title = r['title']
            total_inspected += 1
            inspected_since_heartbeat += 1

            # Heartbeat every 10 inspected entries
            if inspected_since_heartbeat >= 10:
                inspected_since_heartbeat = 0
                print(f'  ... {total_inspected} entries inspected, {total_matches} new matches ...')

            # Skip known non-business URLs
            skip_domains = ['squareup.com', 'checkout.square.site']
            if any(d in url.lower() for d in skip_domains):
                continue

            # Skip sub-pages on square.site (product pages, shop sections, etc.)
            # We only want the root site for each business
            if '.square.site/' in url.lower():
                path = url.split('.square.site/', 1)[1].strip('/').lower()
                if path and path != 'home':
                    if any(p in path for p in ['s/', 'shop', 'product', 'about', 'buy']):
                        continue

            # First check URL-level keyword match
            url_matches = check_url_keywords(url, brief['primary_keywords'])
            if url_matches:
                matched_keywords = url_matches
                confidence = 'confirmed'
                # For square.site URLs, always use the subdomain as business name
                url_name = extract_business_name_from_url(url)
                business_name = url_name or title
            else:
                # Fetch and scan the page
                print(f'  Fetching: {url[:80]}...' if len(url) > 80 else f'  Fetching: {url}')
                html = fetch_page(url)
                if not html:
                    print(f'  ⚠ Empty/failed')
                    continue

                matched_keywords, confidence = check_keywords(
                    html, brief['primary_keywords'], brief['secondary_keywords'],
                    brief['false_positives']
                )
                if not matched_keywords:
                    continue
                # "possible" matches from non-square.site pages are too noisy
                if confidence == 'possible' and '.square.site' not in url.lower():
                    continue
                business_name = title

            # Clean up business name
            business_name = re.sub(r'\s*[-|–—].*$', '', business_name).strip()
            business_name = re.sub(r'\s*\|.*$', '', business_name).strip()

            # Quick URL dedup before spending API calls on goplaces
            if is_duplicate(csv_path, business_name, url=url):
                print(f'  ⏭ Duplicate: {business_name}')
                continue

            print(f'  ✓ MATCH: {business_name} ({confidence})')

            # Get contact info from Google Places (use area context from search)
            print(f'  📍 Looking up on Google Places...')
            place = goplaces_search(business_name, area_city, area_state)

            address = city = state = zipcode = phone = website = ''
            business_type = ''

            if place:
                full_addr = place.get('address', '')
                address, city, state, zipcode = parse_address(full_addr)
                phone = place.get('phone', '')
                website = place.get('website', '')
                types = place.get('types', [])
                if types:
                    # Use the first human-readable type
                    business_type = types[0].replace('_', ' ').title()
                print(f'    📞 {phone or "(no phone)"}')
                print(f'    📍 {address}, {city}, {state} {zipcode}')
                if types:
                    print(f'    🏷 Types: {", ".join(types[:4])}')

                # Find primary website if goplaces didn't return one
                if not website or '.square.site' in website.lower():
                    print(f'    🔍 Searching for primary website...')
                    found_site = find_primary_website(
                        business_name, area_city, area_state, brave_key)
                    time.sleep(1)
                    if found_site:
                        website = found_site
                        print(f'    🌐 {website}')
                    else:
                        print(f'    🌐 No primary website found')
                else:
                    print(f'    🌐 {website}')
            else:
                print(f'    ⏭ Skipping: not found on Google Places')
                continue

            # --- Data quality gates ---

            # Must be a food/drink business (filter out hair salons, etc.)
            food_types = {
                'restaurant', 'cafe', 'bakery', 'bar', 'food',
                'meal_delivery', 'meal_takeaway', 'night_club',
                'grocery_or_supermarket', 'liquor_store',
                'supermarket', 'coffee_shop', 'ice_cream_shop',
                'juice_shop', 'sandwich_shop', 'pizza_restaurant',
                'brunch_restaurant', 'breakfast_restaurant',
                'fast_food_restaurant', 'seafood_restaurant',
                'steak_house', 'sushi_restaurant', 'vegan_restaurant',
                'vegetarian_restaurant', 'american_restaurant',
                'mexican_restaurant', 'italian_restaurant',
                'chinese_restaurant', 'japanese_restaurant',
                'thai_restaurant', 'indian_restaurant',
                'korean_restaurant', 'vietnamese_restaurant',
                'greek_restaurant', 'french_restaurant',
                'spanish_restaurant', 'middle_eastern_restaurant',
                'turkish_restaurant', 'african_restaurant',
                'caribbean_restaurant', 'latin_american_restaurant',
                'mediterranean_restaurant', 'hamburger_restaurant',
                'ramen_restaurant', 'barbecue_restaurant',
                'dessert_shop', 'dessert_restaurant', 'donut_shop',
                'bagel_shop', 'deli', 'food_court',
            }
            types_lower = {t.lower() for t in types}
            if types and not types_lower & food_types:
                print(f'    ⏭ Not a food business: {business_name} ({", ".join(types[:3])})')
                continue

            # Must have a square.site URL OR a confirmed keyword match
            # (businesses on custom domains show <meta generator="Square Online">)
            square_url = url if '.square.site' in url else ''
            if not square_url and confidence != 'confirmed':
                print(f'    ⏭ Skipping: no square.site URL and not confirmed')
                continue

            # Must have a full physical address
            if not address or not city or not state or not zipcode:
                print(f'    ⏭ Skipping: incomplete address ({address}, {city}, {state} {zipcode})')
                continue

            # Must be in Atlanta metro area (zip starts with 30)
            if not zipcode.startswith('30'):
                print(f'    ⏭ Out of area: {business_name} ({city}, {state} {zipcode})')
                continue

            # Full dedup with name + address (allows multi-location businesses)
            if is_duplicate(csv_path, business_name, address=address):
                print(f'  ⏭ Duplicate (same address): {business_name} @ {address}')
                continue

            row = {
                'business_name': business_name,
                'business_type': business_type,
                'address': address,
                'city': city,
                'state': state,
                'zip': zipcode,
                'phone': phone,
                'email': '',
                'contact_name': '',
                'website': website,
                'square_url': square_url,
                'keywords_found': '; '.join(matched_keywords),
                'confidence': confidence,
                'search_term_used': term,
                'date_found': str(date.today()),
                'notes': '',
            }

            if args.dry_run:
                print(f'    [DRY RUN] Would append: {business_name} in {city}, {state}')
            else:
                append_csv(csv_path, row)
                total_matches += 1
                print(f'    ✅ Added to CSV ({total_matches} total)')

                # Sync to HubSpot
                if hubspot:
                    company_id, action = upsert_company_hubspot(hubspot, row)
                    if company_id:
                        print(f'    HubSpot: {action} {company_id}')
                    else:
                        print(f'    HubSpot: sync failed')



        # Brief pause between search terms to be polite to APIs
        time.sleep(1)

    # Count final CSV rows
    csv_final = 0
    if os.path.exists(csv_path):
        with open(csv_path, 'r') as f:
            csv_final = max(0, sum(1 for _ in f) - 1)  # minus header

    print()
    print(f'Done.')
    print(f'  Search terms run: {total_searched}')
    print(f'  Sites inspected: {total_inspected}')
    print(f'  New matches added: {total_matches}')
    print(f'  CSV rows: {csv_baseline} → {csv_final}')
    print(f'  CSV: {csv_path}')
    print()
    print(f'=== COMPLETE: {total_matches} new, {csv_final} total ===')


if __name__ == '__main__':
    main()
