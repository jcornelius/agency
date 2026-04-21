#!/usr/bin/env python3
"""
Email Finder — discovers owner/manager email addresses for businesses.

Usage:
    # Enrich a prospect CSV
    python3 -u scripts/email-finder.py research/square-pos-atlanta.csv \
        -o research/emails-atlanta.csv --skip-processed

    # Single domain lookup
    python3 -u scripts/email-finder.py --domain woodstockcoffee.com --name "John Smith"

    # Dry run (no API calls)
    python3 -u scripts/email-finder.py research/square-pos-atlanta.csv --dry-run --max-rows 5

Pipeline stages:
    1. Hunter.io domain search (find emails + contacts for a domain)
    2. Hunter.io email finder (if a contact name was found)
    3. Apollo.io people search (optional fallback, if APOLLO_API_KEY set)
    4. Pattern generation + SMTP verification (zero-cost fallback)

All API keys loaded from ~/.openclaw/openclaw.json env section.
"""

import argparse
import csv
import json
import os
import re
import smtplib
import socket
import subprocess
import sys
import time
import urllib.request
import urllib.parse
import urllib.error
from datetime import date

# Import HubSpot client for migration
try:
    from hubspot_client import HubSpotClient
except ImportError:
    HubSpotClient = None


# ---------------------------------------------------------------------------
# TwentyClient and OnePageCRMClient removed — use HubSpotClient
# ---------------------------------------------------------------------------

class _UNUSED_TwentyClient:  # noqa — DEPRECATED, do not use
    """Deprecated: Twenty CRM client. Use HubSpotClient instead."""

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

    def update_company(self, company_id, payload):
        """Update a company. Returns updated company dict or None."""
        resp = self._request('PATCH', f'/rest/companies/{company_id}', body=payload)
        if resp and resp.get('data', {}).get('updateCompany'):
            return resp['data']['updateCompany']
        return None


def twenty_company_to_row(company):
    """Convert a Twenty Company dict to the row format process_business expects."""
    name = company.get('name', '')
    domain_obj = company.get('domainName', {}) or {}
    domain_url = domain_obj.get('primaryLinkUrl', '') or ''
    addr = company.get('address', {}) or {}
    phones = company.get('phone', {}) or {}
    emails = company.get('email', {}) or {}

    return {
        'business_name': name,
        'website': domain_url,
        'square_url': '',
        'email': emails.get('primaryEmail', '') or '',
        'contact_name': '',
        'phone': phones.get('primaryPhoneNumber', '') or '',
        'address': addr.get('addressStreet1', '') or '',
        'city': addr.get('addressCity', '') or '',
        'state': addr.get('addressState', '') or '',
        'zip': addr.get('addressPostcode', '') or '',
        '_twenty_id': company['id'],
    }


def create_contact_hubspot(hubspot, company_id, result):
    """Create a Contact record in HubSpot linked to a Company."""
    first_name = ''
    last_name = ''
    contact = (result.get('contact_name') or '').strip()
    if contact and ' ' in contact:
        parts = contact.split(None, 1)
        first_name, last_name = parts[0], parts[1]
    elif contact:
        first_name = contact

    payload = {
        'firstname': first_name,
        'lastname': last_name,
        'email': result.get('email', ''),
        'jobtitle': result.get('contact_title', '') or '',
    }

    contact_obj = hubspot.create_contact(payload)
    if contact_obj and contact_obj.get('id'):
        # Associate contact with company
        hubspot.associate_contact_to_company(company_id, contact_obj['id'])
    return contact_obj


def hubspot_company_to_row(company):
    """Convert a HubSpot Company dict to the row format process_business expects."""
    props = company.get('properties', {})
    name = props.get('name', '')
    domain = props.get('domain', '') or ''
    
    # Support both old and new field names for backwards compatibility
    website = props.get('primary_website', '') or props.get('website', '') or ''
    square_url = props.get('square_online_url', '') or props.get('square_url', '') or ''
    square_confidence = props.get('square_confidence', '')
    
    phone = props.get('phone', '') or ''
    address = props.get('address', '') or ''
    
    return {
        'business_name': name,
        'website': website or domain,
        'square_url': square_url,
        'email': '',
        'contact_name': '',
        'phone': phone,
        'address': address,
        'city': '',
        'state': '',
        'zip': '',
        '_hubspot_id': company.get('id', ''),
        '_square_confidence': square_confidence,  # For reference
    }


ROLE_PREFIXES = {
    'info', 'hello', 'contact', 'contactus', 'owner', 'manager', 'admin',
    'support', 'sales', 'office', 'team', 'help', 'billing',
    'service', 'enquiries', 'inquiries', 'general', 'mail',
    'reception', 'frontdesk', 'feedback', 'orders', 'events',
    'catering', 'reservations', 'bookings', 'customercare', 'customerservice',
    'hr', 'jobs', 'careers', 'marketing', 'press', 'media', 'legal',
    'webmaster', 'postmaster', 'noreply', 'no-reply', 'donotreply',
    'subscribe', 'unsubscribe', 'newsletter', 'notifications',
    'gather', 'international',
}


def is_role_email(email):
    """Return True if the email is a generic role account, not a real person."""
    if not email or '@' not in email:
        return False
    local = email.split('@')[0].lower().strip()
    return local in ROLE_PREFIXES


# ---------------------------------------------------------------------------
# OnePageCRM client — DEPRECATED, do not use
# ---------------------------------------------------------------------------

class OnePageClient:
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

    def update_company(self, company_id, payload):
        """Update a company (partial). Returns updated company dict or None."""
        resp = self._request('PUT', f'/companies/{company_id}.json',
                             body=payload, params={'partial': 'true'})
        if resp and resp.get('status') == 0:
            data = resp.get('data', {})
            return data.get('company', data)
        return None


def onepage_company_to_row(company):
    """Convert a OnePageCRM Company dict to the row format process_business expects."""
    name = company.get('name', '')
    url = company.get('url', '') or ''
    phone = company.get('phone', '') or ''

    address = city = state = zipcode = ''
    addr_obj = company.get('address', {}) or {}
    if addr_obj:
        address = addr_obj.get('address', '') or ''
        city = addr_obj.get('city', '') or ''
        state = addr_obj.get('state', '') or ''
        zipcode = addr_obj.get('zip_code', '') or ''

    return {
        'business_name': name,
        'website': url,
        'square_url': '',
        'email': '',
        'contact_name': '',
        'phone': phone,
        'address': address,
        'city': city,
        'state': state,
        'zip': zipcode,
        '_onepage_id': company['id'],
    }


def create_onepage_contact(onepage, company_id, result):
    """Create a Contact record in OnePageCRM linked to a Company."""
    first_name = ''
    last_name = ''
    contact = (result.get('contact_name') or '').strip()
    if contact and ' ' in contact:
        parts = contact.split(None, 1)
        first_name, last_name = parts[0], parts[1]
    elif contact:
        first_name = contact
        last_name = '(Unknown)'
    else:
        first_name = '(Unknown)'
        last_name = '(Unknown)'

    payload = {
        'first_name': first_name,
        'last_name': last_name,
        'company_id': company_id,
        'job_title': result.get('contact_title', '') or '',
        'emails': [{'type': 'work', 'value': result.get('email', '')}],
    }

    return onepage.create_person(payload)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def load_config():
    """Load API keys from env vars first, then ~/.openclaw/openclaw.json for back-compat."""
    config = {
        'hunter_api_key': os.environ.get('HUNTER_API_KEY', ''),
        'apollo_api_key': os.environ.get('APOLLO_API_KEY', ''),
        'zerobounce_api_key': os.environ.get('ZEROBOUNCE_API_KEY', ''),
    }
    config_path = os.path.expanduser('~/.openclaw/openclaw.json')
    if os.path.exists(config_path):
        with open(config_path) as f:
            data = json.load(f)
        env = data.get('env', {})
        if not config['hunter_api_key']:
            config['hunter_api_key'] = env.get('HUNTER_API_KEY', '')
        if not config['apollo_api_key']:
            config['apollo_api_key'] = env.get('APOLLO_API_KEY', '')
        if not config['zerobounce_api_key']:
            config['zerobounce_api_key'] = env.get('ZEROBOUNCE_API_KEY', '')
        # twenty/onepage config keys removed — using HubSpot
    return config


# ---------------------------------------------------------------------------
# Domain helpers
# ---------------------------------------------------------------------------

def normalize_domain(raw):
    """Normalize a URL or domain to bare domain (no scheme, www, path)."""
    if not raw:
        return ''
    raw = raw.strip()
    raw = re.sub(r'^https?://', '', raw)
    raw = re.sub(r'^www\.', '', raw)
    raw = raw.split('/')[0].split('?')[0].split('#')[0]
    return raw.lower().strip()


def extract_domain(row):
    """Extract a usable domain from a prospect CSV row.

    Prefers the 'website' column. Falls back to 'square_url' only if
    it's NOT a *.square.site domain (can't email @square.site).
    Returns normalized domain or empty string.
    """
    website = (row.get('website') or '').strip()
    if website:
        domain = normalize_domain(website)
        if domain and '.square.site' not in domain:
            return domain

    square_url = (row.get('square_url') or '').strip()
    if square_url:
        domain = normalize_domain(square_url)
        if domain and '.square.site' not in domain:
            return domain

    return ''


def get_mx_records(domain):
    """Look up MX records for a domain using /usr/bin/dig."""
    try:
        result = subprocess.run(
            ['/usr/bin/dig', '+short', 'MX', domain],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return []
        records = []
        for line in result.stdout.strip().splitlines():
            parts = line.strip().split()
            if len(parts) >= 2:
                try:
                    priority = int(parts[0])
                except ValueError:
                    continue
                host = parts[1].rstrip('.')
                records.append((priority, host))
        records.sort(key=lambda x: x[0])
        return records
    except Exception:
        return []


def guess_domain_from_name(business_name):
    """Attempt to guess a business domain from its name and verify via MX.

    Tries common patterns like businessname.com, thebusinessname.com.
    Returns domain if MX records exist, else empty string.
    """
    if not business_name:
        return ''

    name = business_name.lower().strip()
    name = re.sub(r"['\u2019\u2018]s?\b", '', name)  # possessives
    name = re.sub(r'[^a-z0-9\s]', '', name)
    words = name.split()
    if not words:
        return ''

    joined = ''.join(words)
    hyphenated = '-'.join(words)
    candidates = [
        f'{joined}.com',
        f'the{joined}.com',
        f'{hyphenated}.com',
    ]

    for domain in candidates:
        mx = get_mx_records(domain)
        if mx:
            return domain

    return ''


# ---------------------------------------------------------------------------
# Hunter.io API
# ---------------------------------------------------------------------------

def hunter_api_request(endpoint, params, api_key):
    """Make a GET request to Hunter.io API. Returns parsed JSON or None."""
    params['api_key'] = api_key
    qs = urllib.parse.urlencode(params)
    url = f'https://api.hunter.io/v2/{endpoint}?{qs}'
    req = urllib.request.Request(url, headers={
        'Accept': 'application/json',
        'User-Agent': 'EmailFinder/1.0',
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        if e.code == 429:
            print(f'    \u26a0 Hunter rate limit hit, waiting 60s...')
            time.sleep(60)
            try:
                with urllib.request.urlopen(req, timeout=15) as resp:
                    return json.loads(resp.read())
            except Exception:
                return None
        elif e.code == 401:
            print(f'    \u26a0 Hunter API key invalid', file=sys.stderr)
            return None
        else:
            body = ''
            try:
                body = e.read().decode('utf-8', errors='replace')[:200]
            except Exception:
                pass
            print(f'    \u26a0 Hunter API error {e.code}: {body}', file=sys.stderr)
            return None
    except Exception as e:
        print(f'    \u26a0 Hunter request failed: {e}', file=sys.stderr)
        return None


# Title relevance scoring
OWNER_TITLES = {
    'owner': 100, 'co-owner': 100, 'founder': 100, 'co-founder': 95,
    'ceo': 95, 'president': 90, 'principal': 85, 'proprietor': 100,
    'director': 70, 'managing director': 80, 'general manager': 75,
    'manager': 60, 'vp': 65, 'vice president': 65,
    'head': 55, 'chief': 70,
}


def score_contact_relevance(title):
    """Score a contact's title for owner/manager relevance. Higher = better."""
    if not title:
        return 0
    title_lower = title.lower().strip()
    for pattern, score in OWNER_TITLES.items():
        if pattern in title_lower:
            return score
    return 10


def hunter_domain_search(domain, api_key):
    """Search Hunter.io for all emails at a domain.

    Returns list of {email, first_name, last_name, position, confidence, type}
    sorted by owner/manager relevance.
    """
    data = hunter_api_request('domain-search', {
        'domain': domain,
        'limit': 10,
    }, api_key)

    if not data or 'data' not in data:
        return []

    emails = data['data'].get('emails', [])
    if not emails:
        return []

    results = []
    for e in emails:
        email = e.get('value', '')
        if not email:
            continue
        results.append({
            'email': email,
            'first_name': e.get('first_name', '') or '',
            'last_name': e.get('last_name', '') or '',
            'position': e.get('position', '') or '',
            'confidence': e.get('confidence', 0) or 0,
            'type': e.get('type', '') or '',
        })

    # Sort: owner/manager titles first, then personal emails, then confidence
    results.sort(key=lambda r: (
        -score_contact_relevance(r['position']),
        -(1 if r['type'] == 'personal' else 0),
        -r['confidence'],
    ))

    return results


def hunter_email_finder(domain, first_name, last_name, api_key):
    """Use Hunter.io to find a specific person's email at a domain.

    Returns {email, confidence} or None.
    """
    if not first_name or not last_name:
        return None

    data = hunter_api_request('email-finder', {
        'domain': domain,
        'first_name': first_name,
        'last_name': last_name,
    }, api_key)

    if not data or 'data' not in data:
        return None

    email = data['data'].get('email', '')
    confidence = data['data'].get('confidence', 0) or 0

    if email:
        return {'email': email, 'confidence': confidence}
    return None


def hunter_verify_email(email, api_key):
    """Verify an email using Hunter.io email verifier.

    Returns 'valid', 'invalid', 'accept_all', or 'unknown'.
    """
    data = hunter_api_request('email-verifier', {
        'email': email,
    }, api_key)

    if not data or 'data' not in data:
        return 'unknown'

    result = data['data'].get('result', 'unknown')

    if result == 'deliverable':
        return 'valid'
    elif result == 'undeliverable':
        return 'invalid'
    elif result == 'risky':
        return 'accept_all'
    return 'unknown'


# ---------------------------------------------------------------------------
# Apollo.io API (optional)
# ---------------------------------------------------------------------------

def apollo_people_search(domain, api_key):
    """Search Apollo.io for people at a domain with owner/manager titles.

    Returns list of {email, first_name, last_name, title}.
    """
    url = 'https://api.apollo.io/api/v1/mixed_people/search'
    payload = json.dumps({
        'api_key': api_key,
        'q_organization_domains': domain,
        'person_titles': [
            'owner', 'founder', 'ceo', 'president',
            'general manager', 'manager',
        ],
        'page': 1,
        'per_page': 5,
    }).encode('utf-8')

    req = urllib.request.Request(url, data=payload, headers={
        'Content-Type': 'application/json',
        'Accept': 'application/json',
    })

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        if e.code == 429:
            print(f'    \u26a0 Apollo rate limit hit, waiting 60s...')
            time.sleep(60)
            try:
                with urllib.request.urlopen(req, timeout=15) as resp:
                    data = json.loads(resp.read())
            except Exception:
                return []
        else:
            print(f'    \u26a0 Apollo API error: {e.code}', file=sys.stderr)
            return []
    except Exception as e:
        print(f'    \u26a0 Apollo request failed: {e}', file=sys.stderr)
        return []

    people = data.get('people', [])
    results = []
    for p in people:
        email = p.get('email', '')
        if not email or '***' in email:  # skip masked emails
            continue
        results.append({
            'email': email,
            'first_name': p.get('first_name', '') or '',
            'last_name': p.get('last_name', '') or '',
            'title': p.get('title', '') or '',
        })

    return results


# ---------------------------------------------------------------------------
# Pattern generation
# ---------------------------------------------------------------------------

def generate_email_patterns(domain, first_name='', last_name=''):
    """Generate candidate email addresses based on common patterns."""
    patterns = [
        f'info@{domain}',
        f'hello@{domain}',
        f'contact@{domain}',
        f'owner@{domain}',
        f'manager@{domain}',
    ]

    if first_name:
        f = first_name.lower().strip()
        patterns.append(f'{f}@{domain}')
        if last_name:
            l = last_name.lower().strip()
            patterns.extend([
                f'{f}.{l}@{domain}',
                f'{f}{l}@{domain}',
                f'{f[0]}{l}@{domain}',
                f'{f}_{l}@{domain}',
                f'{l}@{domain}',
                f'{f[0]}.{l}@{domain}',
            ])

    seen = set()
    unique = []
    for p in patterns:
        if p not in seen:
            seen.add(p)
            unique.append(p)

    return unique


# ---------------------------------------------------------------------------
# SMTP verification (zero-cost fallback)
# ---------------------------------------------------------------------------

CATCH_ALL_MX_PATTERNS = [
    'google.com', 'googlemail.com', 'gmail.com',
    'outlook.com', 'hotmail.com', 'live.com',
    'protection.outlook.com',  # Office 365
    'pphosted.com',  # Proofpoint
    'mimecast.com',
]


def is_catch_all_mx(mx_host):
    """Check if the MX host is a known catch-all provider."""
    mx_lower = mx_host.lower()
    for provider in CATCH_ALL_MX_PATTERNS:
        if provider in mx_lower:
            return True
    return False


def verify_email_smtp(email, timeout=10):
    """Verify an email using SMTP RCPT TO check.

    Returns 'valid', 'invalid', 'catch_all', or 'unknown'.
    """
    domain = email.split('@')[-1]

    mx_records = get_mx_records(domain)
    if not mx_records:
        return 'unknown'

    mx_host = mx_records[0][1]
    if is_catch_all_mx(mx_host):
        return 'catch_all'

    try:
        smtp = smtplib.SMTP(timeout=timeout)
        smtp.connect(mx_host, 25)
        smtp.helo('verify.local')
        smtp.mail('verify@verify.local')
        code, message = smtp.rcpt(email)
        smtp.quit()

        if code == 250:
            return 'valid'
        elif code == 550 or code == 551 or code == 553:
            return 'invalid'
        else:
            return 'unknown'
    except smtplib.SMTPServerDisconnected:
        return 'unknown'
    except smtplib.SMTPConnectError:
        return 'unknown'
    except socket.timeout:
        return 'unknown'
    except OSError:
        return 'unknown'
    except Exception:
        return 'unknown'


# ---------------------------------------------------------------------------
# ZeroBounce API (optional)
# ---------------------------------------------------------------------------

def verify_email_zerobounce(email, api_key):
    """Verify an email using ZeroBounce API.

    Returns 'valid', 'invalid', 'catch_all', or 'unknown'.
    """
    params = urllib.parse.urlencode({
        'api_key': api_key,
        'email': email,
    })
    url = f'https://api.zerobounce.net/v2/validate?{params}'
    req = urllib.request.Request(url, headers={'Accept': 'application/json'})

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
    except Exception as e:
        print(f'    \u26a0 ZeroBounce request failed: {e}', file=sys.stderr)
        return 'unknown'

    status = data.get('status', '').lower()
    if status == 'valid':
        return 'valid'
    elif status == 'invalid':
        return 'invalid'
    elif status == 'catch-all':
        return 'catch_all'
    return 'unknown'


# ---------------------------------------------------------------------------
# Confidence scoring
# ---------------------------------------------------------------------------

def compute_confidence(source, hunter_score=0, verified_status='unknown'):
    """Compute a unified 0-100 confidence score."""
    if source.startswith('hunter'):
        base = min(hunter_score, 100) if hunter_score else 50
    elif source == 'apollo':
        base = 60
    elif source == 'pattern_verified':
        base = 40
    elif source == 'pattern_unverified':
        base = 10
    elif source == 'input_csv':
        base = 30
    else:
        base = 0

    if verified_status == 'valid':
        base = max(base, 70)
        base = min(base + 15, 100)
    elif verified_status == 'invalid':
        base = max(base - 50, 5)
    elif verified_status == 'catch_all' or verified_status == 'accept_all':
        base = max(base - 10, 20)

    return base


# ---------------------------------------------------------------------------
# Verification cascade
# ---------------------------------------------------------------------------

def verify_email(email, config):
    """Run verification cascade: ZeroBounce -> Hunter -> SMTP fallback.

    Returns 'valid', 'invalid', 'catch_all', or 'unknown'.
    """
    # ZeroBounce (if key available)
    if config.get('zerobounce_api_key'):
        result = verify_email_zerobounce(email, config['zerobounce_api_key'])
        time.sleep(0.25)
        if result in ('valid', 'invalid'):
            return result

    # Hunter verify (if key available)
    if config.get('hunter_api_key'):
        result = hunter_verify_email(email, config['hunter_api_key'])
        time.sleep(0.1)
        if result in ('valid', 'invalid'):
            return result
        if result in ('accept_all', 'catch_all'):
            return 'catch_all'

    # SMTP fallback (always available)
    result = verify_email_smtp(email)
    time.sleep(2)
    return result


# ---------------------------------------------------------------------------
# Pipeline orchestrator
# ---------------------------------------------------------------------------

def process_business(row, config, dry_run=False, hunter_only=False, no_verify=False):
    """Process a single business through the email discovery pipeline.

    Returns dict with: email, email_confidence, email_source,
    email_verified, contact_name, contact_title, error
    """
    business_name = (row.get('business_name') or '').strip()
    domain = extract_domain(row)

    # Try to guess domain if none found
    if not domain:
        print(f'  Domain: (none \u2014 guessing from name...)')
        domain = guess_domain_from_name(business_name)
        if domain:
            print(f'  Domain: {domain} (guessed, MX verified)')
        else:
            print(f'  \u26a0 No domain found')
            return {
                'email': '', 'email_confidence': 0, 'email_source': 'none',
                'email_verified': '', 'contact_name': '', 'contact_title': '',
                'error': 'no_domain', 'domain': '',
            }
    else:
        print(f'  Domain: {domain}')

    # Check if input CSV already has an email
    existing_email = (row.get('email') or '').strip()
    if existing_email:
        print(f'  Input CSV has email: {existing_email}')
        if not no_verify:
            verified = verify_email(existing_email, config)
            print(f'  Verified: {verified}')
        else:
            verified = 'unknown'
        confidence = compute_confidence('input_csv', verified_status=verified)
        return {
            'email': existing_email, 'email_confidence': confidence,
            'email_source': 'input_csv', 'email_verified': verified,
            'contact_name': row.get('contact_name', ''),
            'contact_title': '', 'error': '', 'domain': domain,
        }

    if dry_run:
        patterns = generate_email_patterns(domain)
        print(f'  [DRY RUN] Would try: Hunter \u2192 Apollo \u2192 {len(patterns)} patterns')
        return {
            'email': patterns[0] if patterns else '', 'email_confidence': 0,
            'email_source': 'dry_run', 'email_verified': '',
            'contact_name': '', 'contact_title': '',
            'error': 'dry_run', 'domain': domain,
        }

    best_result = None
    contact_name = ''
    contact_title = ''

    # ---- Stage 1: Hunter.io domain search ----
    if config.get('hunter_api_key'):
        print(f'  Hunter domain search...')
        contacts = hunter_domain_search(domain, config['hunter_api_key'])
        time.sleep(0.1)

        if contacts:
            best = contacts[0]
            print(f'  Hunter: {len(contacts)} emails, best: {best["email"]} '
                  f'(confidence: {best["confidence"]}, '
                  f'title: {best["position"] or "unknown"})')

            contact_name = f'{best["first_name"]} {best["last_name"]}'.strip()
            contact_title = best['position']

            if best['confidence'] >= 70:
                if not no_verify:
                    verified = verify_email(best['email'], config)
                    print(f'  Verified: {verified}')
                else:
                    verified = 'unknown'
                confidence = compute_confidence(
                    'hunter_domain', best['confidence'], verified)
                if verified != 'invalid':
                    return {
                        'email': best['email'],
                        'email_confidence': confidence,
                        'email_source': 'hunter_domain',
                        'email_verified': verified,
                        'contact_name': contact_name,
                        'contact_title': contact_title,
                        'error': '', 'domain': domain,
                    }

            # Save as fallback
            best_result = {
                'email': best['email'], 'confidence': best['confidence'],
                'source': 'hunter_domain', 'name': contact_name,
                'title': contact_title,
            }

            # ---- Stage 2: Hunter.io email finder (if name found) ----
            if contact_name and ' ' in contact_name:
                parts = contact_name.split(None, 1)
                first, last = parts[0], parts[1]
                print(f'  Hunter email finder ({first} {last})...')
                found = hunter_email_finder(domain, first, last,
                                            config['hunter_api_key'])
                time.sleep(0.1)

                if found and found['confidence'] >= 50:
                    print(f'  Hunter finder: {found["email"]} '
                          f'(confidence: {found["confidence"]})')
                    if not no_verify:
                        verified = verify_email(found['email'], config)
                        print(f'  Verified: {verified}')
                    else:
                        verified = 'unknown'
                    confidence = compute_confidence(
                        'hunter_finder', found['confidence'], verified)
                    if verified != 'invalid':
                        return {
                            'email': found['email'],
                            'email_confidence': confidence,
                            'email_source': 'hunter_finder',
                            'email_verified': verified,
                            'contact_name': contact_name,
                            'contact_title': contact_title,
                            'error': '', 'domain': domain,
                        }
        else:
            print(f'  Hunter: no results')

    if hunter_only:
        if best_result:
            return {
                'email': best_result['email'],
                'email_confidence': compute_confidence(
                    best_result['source'], best_result['confidence']),
                'email_source': best_result['source'],
                'email_verified': 'unknown',
                'contact_name': best_result.get('name', ''),
                'contact_title': best_result.get('title', ''),
                'error': '', 'domain': domain,
            }
        return {
            'email': '', 'email_confidence': 0, 'email_source': 'none',
            'email_verified': '', 'contact_name': '', 'contact_title': '',
            'error': 'not_found', 'domain': domain,
        }

    # ---- Stage 3: Apollo.io (optional) ----
    if config.get('apollo_api_key'):
        print(f'  Apollo people search...')
        people = apollo_people_search(domain, config['apollo_api_key'])
        time.sleep(12)  # Apollo free tier: 5 req/min

        if people:
            person = people[0]
            print(f'  Apollo: {person["email"]} ({person["title"]})')
            a_name = f'{person["first_name"]} {person["last_name"]}'.strip()
            if not no_verify:
                verified = verify_email(person['email'], config)
                print(f'  Verified: {verified}')
            else:
                verified = 'unknown'
            confidence = compute_confidence('apollo', verified_status=verified)
            if verified != 'invalid':
                return {
                    'email': person['email'],
                    'email_confidence': confidence,
                    'email_source': 'apollo',
                    'email_verified': verified,
                    'contact_name': a_name or contact_name,
                    'contact_title': person['title'] or contact_title,
                    'error': '', 'domain': domain,
                }
        else:
            print(f'  Apollo: no results')

    # ---- Stage 4 (removed): Pattern generation + SMTP verification ----
    # Previously we fell back to generating info@/hello@/contact@/owner@/manager@
    # addresses and SMTP-verifying them. This produced low-quality role-account
    # emails that violated the "decision-makers only" bar, so we no longer do it.
    # If Hunter and Apollo both miss, we return no email — sales team can
    # reach out manually if the lead is worth it.

    # ---- Fallback: return best available from Hunter/Apollo ----
    if best_result:
        confidence = compute_confidence(
            best_result['source'], best_result['confidence'])
        return {
            'email': best_result['email'],
            'email_confidence': confidence,
            'email_source': best_result['source'],
            'email_verified': 'unknown',
            'contact_name': best_result.get('name', ''),
            'contact_title': best_result.get('title', ''),
            'error': '', 'domain': domain,
        }

    return {
        'email': '', 'email_confidence': 0, 'email_source': 'none',
        'email_verified': '', 'contact_name': '', 'contact_title': '',
        'error': 'not_found', 'domain': domain,
    }


# ---------------------------------------------------------------------------
# Output CSV
# ---------------------------------------------------------------------------

OUTPUT_HEADERS = [
    'business_name', 'domain', 'email', 'email_confidence', 'email_source',
    'email_verified', 'contact_name', 'contact_title', 'phone', 'address',
    'city', 'state', 'zip', 'error', 'date_found',
]


def is_already_processed(csv_path, business_name, domain):
    """Check if a business is already in the output CSV."""
    if not os.path.exists(csv_path):
        return False
    try:
        with open(csv_path, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                row_name = (row.get('business_name', '') or '').lower().strip()
                row_domain = (row.get('domain', '') or '').lower().strip()
                if (business_name.lower().strip() == row_name
                        and domain.lower().strip() == row_domain):
                    return True
    except Exception:
        pass
    return False


def append_output_csv(csv_path, row_data):
    """Append a result row to the output CSV."""
    write_header = (not os.path.exists(csv_path)
                    or os.path.getsize(csv_path) == 0)
    with open(csv_path, 'a', newline='') as f:
        writer = csv.DictWriter(
            f, fieldnames=OUTPUT_HEADERS, quoting=csv.QUOTE_ALL)
        if write_header:
            writer.writeheader()
        writer.writerow(row_data)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description='Email Finder \u2014 discover owner/manager emails')
    parser.add_argument('input', nargs='?',
                        help='Input prospect CSV file')
    parser.add_argument('-o', '--output',
                        help='Output CSV path')
    parser.add_argument('--skip-processed', action='store_true',
                        help='Skip rows already in the output CSV')
    parser.add_argument('--dry-run', action='store_true',
                        help='Print plan without making API calls')
    parser.add_argument('--max-rows', type=int, default=0,
                        help='Process at most N rows (0 = all)')
    parser.add_argument('--start-row', type=int, default=0,
                        help='Start from row N (0-indexed, after header)')
    parser.add_argument('--hunter-only', action='store_true',
                        help='Only use Hunter.io (skip Apollo/patterns)')
    parser.add_argument('--no-verify', action='store_true',
                        help='Skip email verification')
    parser.add_argument('--domain',
                        help='Single domain lookup (no CSV needed)')
    parser.add_argument('--name',
                        help='Owner/contact name for single lookup')
    parser.add_argument('--from-hubspot', action='store_true',
                        help='Read companies from HubSpot and write Contacts back')
    parser.add_argument('--max-companies', type=int, default=0,
                        help='Max companies to process (0 = all)')
    parser.add_argument('--twenty', action='store_true', dest='from_hubspot',
                        help='[DEPRECATED] Use --from-hubspot')
    args = parser.parse_args()

    config = load_config()

    # Print API status
    apis = []
    apis.append('Hunter \u2713' if config['hunter_api_key'] else 'Hunter \u2717')
    apis.append('Apollo \u2713' if config['apollo_api_key'] else 'Apollo \u2717')
    apis.append('ZeroBounce \u2713' if config['zerobounce_api_key']
                else 'ZeroBounce \u2717')

    print(f'Email Finder starting...')
    print(f'  APIs: {", ".join(apis)}')

    if not config['hunter_api_key'] and not args.dry_run:
        print(f'  \u26a0 No HUNTER_API_KEY \u2014 only patterns + SMTP available')

    # ---- Single domain lookup ----
    if args.domain:
        domain = normalize_domain(args.domain)
        print(f'  Mode: single lookup')
        print(f'  Domain: {domain}')
        if args.name:
            print(f'  Name: {args.name}')
        print()

        row = {
            'business_name': args.name or domain,
            'website': args.domain,
            'email': '', 'contact_name': args.name or '',
        }

        result = process_business(
            row, config, dry_run=args.dry_run,
            hunter_only=args.hunter_only, no_verify=args.no_verify)

        print()
        print(f'Result:')
        print(f'  Email:      {result["email"] or "(none)"}')
        print(f'  Confidence: {result["email_confidence"]}')
        print(f'  Source:     {result["email_source"]}')
        print(f'  Verified:   {result["email_verified"] or "n/a"}')
        print(f'  Contact:    {result["contact_name"] or "(unknown)"}')
        print(f'  Title:      {result["contact_title"] or "(unknown)"}')
        if result['error']:
            print(f'  Error:      {result["error"]}')
        print()
        print(f'=== COMPLETE: {"1 email found" if result["email"] else "0 emails found"} ===')
        return

    # ---- HubSpot mode ----
    if args.from_hubspot:
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
        except Exception as e:
            print(f'Error: HubSpot initialization failed: {e}', file=sys.stderr)
            sys.exit(1)

        print(f'  Mode: HubSpot (read companies → write contacts)')
        if args.max_companies:
            print(f'  Limit: {args.max_companies} companies')
        print()

        # Fetch all companies, filter to those without email contacts
        print(f'Fetching companies from HubSpot...')
        all_companies = []
        cursor = None
        while True:
            batch, cursor, has_more = hubspot.list_companies(limit=100, after=cursor)
            all_companies.extend(batch)
            if not has_more or not batch:
                break
            time.sleep(0.5)
        print(f'  Total companies: {len(all_companies)}')

        # Filter to companies without email enrichment
        companies = []
        for c in all_companies:
            # Skip if company already has an email in the email property
            props = c.get('properties', {})
            if props.get('email', '') or props.get('hs_lead_status', ''):
                continue
            contacts = hubspot.get_contacts_for_company(c.get('id', ''))
            if not contacts:
                companies.append(c)
            time.sleep(0.3)
            if args.max_companies and len(companies) >= args.max_companies:
                break
        print(f'  Companies needing email enrichment: {len(companies)}')
        print()

        people_created = 0
        roles_stored = 0
        errors = 0
        total = len(companies)

        for i, company in enumerate(companies):
            row = hubspot_company_to_row(company)
            company_id = company['id']
            business_name = row['business_name']

            print(f'--- [{i+1}/{total}] {business_name} ---')

            result = process_business(
                row, config, dry_run=args.dry_run,
                hunter_only=args.hunter_only, no_verify=args.no_verify)

            if result['email'] and result['email_source'] not in ('none', 'dry_run'):
                email = result['email']

                if is_role_email(email):
                    # Role account → skip (don't try to store on company, no email property)
                    roles_stored += 1
                    print(f'  📧 {email} (role account)')
                else:
                    # Real person → create a Contact record
                    people_created += 1
                    print(f'  ✅ {email} '
                          f'({result.get("contact_name", "")}) → contact')
                    if not args.dry_run:
                        person = create_contact_hubspot(hubspot, company_id, result)
                        if person and person.get('id'):
                            print(f'  HubSpot: created contact {person["id"][:8]}...')
                        else:
                            print(f'  HubSpot: failed to create contact')
            else:
                errors += 1
                err = result.get('error', 'not_found')
                print(f'  ⏭ {err}')

            if (i + 1) % 10 == 0:
                found = people_created + roles_stored
                print(f'  ... {i+1}/{total} processed, {found} emails found ...')

            if not args.dry_run:
                time.sleep(1)

        print()
        print(f'Done.')
        print(f'  Companies processed: {total}')
        print(f'  People created: {people_created}')
        print(f'  Company emails set: {roles_stored}')
        print(f'  Errors/no email: {errors}')
        print()
        print(f'=== COMPLETE: {people_created} contacts + {roles_stored} company emails in HubSpot ===')
        return

    # ---- OnePageCRM mode REMOVED — use --from-hubspot ----
    if False and getattr(args, 'onepage', False):  # disabled
        onepage_uid = config.get('onepage_user_id', '')
        onepage_key = config.get('onepage_api_key', '')
        if not onepage_uid or not onepage_key:
            print('Error: ONEPAGE_USER_ID and ONEPAGE_API_KEY required in openclaw.json',
                  file=sys.stderr)
            sys.exit(1)
        onepage = OnePageClient(onepage_uid, onepage_key)
        if not onepage.test_connection():
            print('Error: Cannot connect to OnePageCRM', file=sys.stderr)
            sys.exit(1)

        print(f'  Mode: OnePageCRM (read companies → write contacts)')
        if args.onepage_limit:
            print(f'  Limit: {args.onepage_limit} companies')
        print()

        # Fetch all companies, filter to those without contacts
        print(f'Fetching companies from OnePageCRM...')
        all_companies = []
        page = 1
        while True:
            batch, next_page, has_more = onepage.list_companies(per_page=100, page=page)
            all_companies.extend(batch)
            if not has_more or not batch:
                break
            page = next_page
            time.sleep(0.1)
        print(f'  Total companies: {len(all_companies)}')

        # Filter to companies that don't yet have a contact with a real email.
        # Note: prospect-search creates a placeholder contact (no email) to
        # create the company, so we can't just check contacts_count == 0.
        companies = []
        for c in all_companies:
            contacts_count = c.get('contacts_count', 0)
            if contacts_count > 0:
                contacts = onepage.get_people_for_company(c['id'])
                has_real_email = False
                for ct in contacts:
                    emails = ct.get('emails', []) or []
                    for em in emails:
                        if (em.get('value') or '').strip():
                            has_real_email = True
                            break
                    if has_real_email:
                        break
                if has_real_email:
                    continue  # Already enriched — skip
                time.sleep(0.1)
            companies.append(c)
            if args.onepage_limit and len(companies) >= args.onepage_limit:
                break
        print(f'  Companies needing email enrichment: {len(companies)}')
        print()

        people_created = 0
        roles_stored = 0
        errors = 0
        total = len(companies)

        for i, company in enumerate(companies):
            row = onepage_company_to_row(company)
            company_id = company['id']
            business_name = row['business_name']

            print(f'--- [{i+1}/{total}] {business_name} ---')

            result = process_business(
                row, config, dry_run=args.dry_run,
                hunter_only=args.hunter_only, no_verify=args.no_verify)

            if result['email'] and result['email_source'] not in ('none', 'dry_run'):
                email = result['email']
                is_role = is_role_email(email)

                # OnePage has no company-level email field, so all emails
                # become contacts. Role emails get a generic name.
                if is_role:
                    roles_stored += 1
                    label = email.split('@')[0].title()
                    print(f'  📧 {email} (role → contact as "{label}")')
                    if not args.dry_run:
                        role_result = dict(result)
                        role_result['contact_name'] = label
                        role_result['contact_title'] = 'General'
                        contact = create_onepage_contact(
                            onepage, company_id, role_result)
                        if contact and contact.get('id'):
                            print(f'  OnePage: created contact {contact["id"][:8]}...')
                        else:
                            print(f'  OnePage: failed to create contact')
                else:
                    people_created += 1
                    print(f'  ✅ {email} '
                          f'({result.get("contact_name", "")}) → contact')
                    if not args.dry_run:
                        contact = create_onepage_contact(
                            onepage, company_id, result)
                        if contact and contact.get('id'):
                            print(f'  OnePage: created contact {contact["id"][:8]}...')
                        else:
                            print(f'  OnePage: failed to create contact')
            else:
                errors += 1
                err = result.get('error', 'not_found')
                print(f'  ⏭ {err}')

            if (i + 1) % 10 == 0:
                found = people_created + roles_stored
                print(f'  ... {i+1}/{total} processed, {found} emails found ...')

            if not args.dry_run:
                time.sleep(0.5)

        print()
        print(f'Done.')
        print(f'  Companies processed: {total}')
        print(f'  Contacts created: {people_created}')
        print(f'  Company emails set: {roles_stored}')
        print(f'  Errors/no email: {errors}')
        print()
        print(f'=== COMPLETE: {people_created} contacts + {roles_stored} company emails in OnePage ===')
        return

    # ---- Batch mode ----
    if not args.input:
        parser.error('Input CSV required (or use --domain for single lookup)')

    input_path = args.input
    if not os.path.exists(input_path):
        print(f'Error: Input file not found: {input_path}', file=sys.stderr)
        sys.exit(1)

    # Read input
    with open(input_path, 'r') as f:
        reader = csv.DictReader(f)
        input_rows = list(reader)
    total_input = len(input_rows)

    # Output path
    if args.output:
        output_path = args.output
    else:
        stem = os.path.splitext(os.path.basename(input_path))[0]
        output_dir = os.path.dirname(input_path) or 'research'
        output_path = os.path.join(output_dir, f'emails-{stem}.csv')

    os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)

    print(f'  Input: {input_path} ({total_input} rows)')
    print(f'  Output: {output_path}')
    if args.dry_run:
        print(f'  Mode: DRY RUN (no API calls)')
    if args.max_rows:
        print(f'  Max rows: {args.max_rows}')
    if args.start_row:
        print(f'  Start row: {args.start_row}')
    print()

    # Baseline count
    csv_baseline = 0
    if os.path.exists(output_path):
        with open(output_path, 'r') as f:
            csv_baseline = max(0, sum(1 for _ in f) - 1)
    print(f'CSV baseline: {csv_baseline} rows')
    print()

    # Slice rows
    rows = input_rows[args.start_row:]
    if args.max_rows:
        rows = rows[:args.max_rows]

    total_to_process = len(rows)
    emails_found = 0
    skipped = 0
    errors = 0

    for i, row in enumerate(rows):
        business_name = (row.get('business_name') or '').strip()
        domain = extract_domain(row)

        print(f'--- [{i+1}/{total_to_process}] {business_name} ---')

        # Skip if already processed
        if args.skip_processed and domain:
            if is_already_processed(output_path, business_name, domain):
                print(f'  \u23ed Already processed')
                skipped += 1
                continue

        result = process_business(
            row, config, dry_run=args.dry_run,
            hunter_only=args.hunter_only, no_verify=args.no_verify)

        # Use domain from result if process_business resolved it
        resolved_domain = result.get('domain', domain) or domain

        out_row = {
            'business_name': business_name,
            'domain': resolved_domain,
            'email': result['email'],
            'email_confidence': result['email_confidence'],
            'email_source': result['email_source'],
            'email_verified': result['email_verified'],
            'contact_name': result['contact_name'],
            'contact_title': result['contact_title'],
            'phone': row.get('phone', ''),
            'address': row.get('address', ''),
            'city': row.get('city', ''),
            'state': row.get('state', ''),
            'zip': row.get('zip', ''),
            'error': result['error'],
            'date_found': str(date.today()),
        }

        if not args.dry_run:
            append_output_csv(output_path, out_row)

        if result['email'] and result['email_source'] not in ('none', 'dry_run'):
            emails_found += 1
            print(f'  \u2705 {result["email"]} '
                  f'(confidence: {result["email_confidence"]}, '
                  f'source: {result["email_source"]})')
        elif result['error'] and result['error'] != 'dry_run':
            errors += 1
            print(f'  \u23ed {result["error"]}')
        else:
            print(f'  \u23ed No email found')

        # Heartbeat every 10 rows
        if (i + 1) % 10 == 0:
            print(f'  ... {i+1}/{total_to_process} processed, '
                  f'{emails_found} emails found, {skipped} skipped ...')

        # Pause between businesses (respect rate limits)
        if not args.dry_run:
            time.sleep(1)

    # Final counts
    csv_final = 0
    if os.path.exists(output_path):
        with open(output_path, 'r') as f:
            csv_final = max(0, sum(1 for _ in f) - 1)

    print()
    print(f'Done.')
    print(f'  Rows processed: {total_to_process}')
    print(f'  Emails found: {emails_found}')
    print(f'  Skipped: {skipped}')
    print(f'  Errors/no domain: {errors}')
    print(f'  Output CSV: {csv_baseline} \u2192 {csv_final} rows')
    print(f'  File: {output_path}')
    print()
    print(f'=== COMPLETE: {emails_found} emails found, {csv_final} total ===')


if __name__ == '__main__':
    main()
