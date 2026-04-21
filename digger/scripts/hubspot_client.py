#!/usr/bin/env python3
"""
HubSpotClient — minimal HubSpot REST API client (stdlib-only).

Uses HubSpot's standard REST API endpoints:
- /crm/v3/objects/companies
- /crm/v3/objects/contacts
- /crm/v3/objects/companies/{id}/associations/contacts

All API keys loaded from environment variable HUBSPOT_PRIVATE_APP_TOKEN.
"""

import json
import os
import sys
import time
import urllib.request
import urllib.parse
import urllib.error


class HubSpotClient:
    """Minimal HubSpot REST API client (stdlib-only)."""

    BASE_URL = 'https://api.hubapi.com'

    def __init__(self, api_token):
        """Initialize with HubSpot private app token."""
        self.api_token = api_token.strip()
        if not self.api_token:
            raise ValueError('HUBSPOT_PRIVATE_APP_TOKEN is empty')

    def _request(self, method, path, body=None, params=None):
        """Authenticated request to HubSpot API. Returns parsed JSON or None."""
        url = f'{self.BASE_URL}{path}'
        if params:
            # Handle repeated params (e.g., properties=name&properties=domain)
            query_parts = []
            for key, val in params.items():
                if isinstance(val, list):
                    for item in val:
                        query_parts.append(f"{key}={urllib.parse.quote(str(item))}")
                else:
                    query_parts.append(f"{key}={urllib.parse.quote(str(val))}")
            url += '?' + '&'.join(query_parts)

        data = json.dumps(body).encode('utf-8') if body else None
        req = urllib.request.Request(url, data=data, method=method, headers={
            'Authorization': f'Bearer {self.api_token}',
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'User-Agent': 'OpenClaw/1.0',
        })

        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            if e.code == 429:
                print(f'  HubSpot rate limit, waiting 60s...', file=sys.stderr)
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
            print(f'  HubSpot API error {e.code}: {body_text}', file=sys.stderr)
            return None
        except Exception as e:
            print(f'  HubSpot request failed: {e}', file=sys.stderr)
            return None

    def test_connection(self):
        """Verify API connectivity. Returns True if successful."""
        resp = self._request('GET', '/crm/v3/objects/companies',
                            params={'limit': '1'})
        if resp is not None:
            # Ensure custom properties exist on first connection
            self._ensure_custom_properties()
            return True
        return False

    def _ensure_custom_properties(self):
        """Ensure custom properties exist on the Company object."""
        required_props = [
            {'name': 'square_url', 'label': 'Square URL'},
            {'name': 'keywords_found', 'label': 'Keywords Found'},
            {'name': 'confidence', 'label': 'Confidence'},
            {'name': 'date_found', 'label': 'Date Found'},
        ]

        for prop_def in required_props:
            prop_name = prop_def['name']
            # Check if property exists
            resp = self._request('GET',
                                f'/crm/v3/properties/companies/{prop_name}')
            if resp and 'error' not in resp:
                continue

            # Create property if it doesn't exist
            payload = {
                'name': prop_name,
                'label': prop_def['label'],
                'type': 'string',
                'fieldType': 'text',
                'groupName': 'companyinformation',
                'displayOrder': -1,
                'hasUniqueValue': False,
                'hidden': False,
                'modificationMetadata': {
                    'archivable': True,
                    'mandatory': False,
                },
                'formField': True,
            }
            result = self._request('POST', '/crm/v3/properties/companies',
                                  body=payload)
            if result and 'name' in result:
                print(f'  ✓ Created custom property: {prop_name}',
                      file=sys.stderr)
            elif result and 'error' in result:
                err_msg = result.get('message', 'Unknown error')
                print(f'  ✗ Failed to create {prop_name}: {err_msg}',
                      file=sys.stderr)
            time.sleep(0.5)

    def find_company(self, name=None, domain=None):
        """Find existing company by name or domain using search endpoint.
        
        Returns company dict or None.
        """
        if not name and not domain:
            return None

        # Try domain search first (most reliable)
        if domain:
            body = {
                'filterGroups': [
                    {
                        'filters': [
                            {
                                'propertyName': 'domain',
                                'operator': 'EQ',
                                'value': domain,
                            }
                        ]
                    }
                ],
                'sorts': [{'propertyName': 'hs_lastmodifieddate', 'direction': 'DESCENDING'}],
                'limit': 10,
                'properties': ['name', 'domain', 'website'],
            }
            resp = self._request('POST', '/crm/v3/objects/companies/search',
                                body=body)
            if resp and 'results' in resp and resp['results']:
                return resp['results'][0]  # Return first (most recent) match

        # Try name search
        if name:
            body = {
                'filterGroups': [
                    {
                        'filters': [
                            {
                                'propertyName': 'name',
                                'operator': 'EQ',
                                'value': name,
                            }
                        ]
                    }
                ],
                'sorts': [{'propertyName': 'hs_lastmodifieddate', 'direction': 'DESCENDING'}],
                'limit': 10,
                'properties': ['name', 'domain', 'website'],
            }
            resp = self._request('POST', '/crm/v3/objects/companies/search',
                                body=body)
            if resp and 'results' in resp and resp['results']:
                return resp['results'][0]  # Return first (most recent) match

        return None

    def create_company(self, payload):
        """Create a company. Returns created company dict or None.
        
        Payload should have 'properties' key with field dict.
        """
        body = {
            'properties': payload,
        }
        resp = self._request('POST', '/crm/v3/objects/companies', body=body)
        if resp and 'id' in resp:
            return resp
        return None

    def update_company(self, company_id, payload):
        """Update a company. Returns updated company dict or None.
        
        Payload should be field dict (not wrapped in 'properties').
        """
        body = {
            'properties': payload,
        }
        resp = self._request('PATCH',
                            f'/crm/v3/objects/companies/{company_id}',
                            body=body)
        if resp and 'id' in resp:
            return resp
        return None

    def get_company(self, company_id):
        """Get company by ID. Returns company dict or None."""
        params = {
            'properties': [
                'name', 'domain', 'phone', 'website',
                'hs_lead_status', 'square_url', 'keywords_found',
                'confidence', 'date_found',
            ],
        }
        resp = self._request('GET', f'/crm/v3/objects/companies/{company_id}',
                            params=params)
        if resp and 'id' in resp:
            return resp
        return None

    def list_companies(self, limit=100, after=None):
        """List companies with pagination.
        
        Returns (companies, next_cursor, has_more).
        """
        params = {
            'limit': str(limit),
            'properties': [
                'name', 'domain', 'phone', 'website', 'primary_website',
                'hs_lead_status', 'square_online_url', 'square_url',
                'keywords_found', 'confidence', 'date_found', 'square_confidence',
            ],
        }
        if after:
            params['after'] = after

        resp = self._request('GET', '/crm/v3/objects/companies',
                            params=params)
        if not resp or 'results' not in resp:
            return [], None, False

        results = resp['results']
        paging = resp.get('paging', {})
        next_cursor = paging.get('next', {}).get('after')
        has_more = bool(next_cursor)

        return results, next_cursor, has_more

    def get_contacts_for_company(self, company_id):
        """Get contacts linked to a company.
        
        Returns list of contact dicts.
        """
        params = {
            'limit': '100',
        }
        resp = self._request('GET',
                            f'/crm/v3/objects/companies/{company_id}/associations/contacts',
                            params=params)
        if not resp or 'results' not in resp:
            return []

        # Association results are just IDs; fetch full contact data
        contact_ids = [r.get('id') for r in resp['results'] if r.get('id')]
        contacts = []
        for cid in contact_ids:
            contact = self.get_contact(cid)
            if contact:
                contacts.append(contact)
            time.sleep(0.1)
        return contacts

    def create_contact(self, payload):
        """Create a contact. Returns created contact dict or None.
        
        Payload should have field dict.
        """
        body = {
            'properties': payload,
        }
        resp = self._request('POST', '/crm/v3/objects/contacts', body=body)
        if resp and 'id' in resp:
            return resp
        return None

    def get_contact(self, contact_id):
        """Get contact by ID. Returns contact dict or None."""
        params = {
            'properties': [
                'firstname', 'lastname', 'email', 'jobtitle',
                'phone', 'company',
            ],
        }
        resp = self._request('GET', f'/crm/v3/objects/contacts/{contact_id}',
                            params=params)
        if resp and 'id' in resp:
            return resp
        return None

    def associate_contact_to_company(self, company_id, contact_id):
        """Create an association between a company and contact.

        Uses the v4 default-association endpoint which doesn't require a
        types body and doesn't 404 the way the deprecated v3 variant does.

        Returns True if successful.
        """
        resp = self._request(
            'PUT',
            f'/crm/v4/objects/companies/{company_id}/associations/default/contacts/{contact_id}',
        )
        return resp is not None and 'error' not in resp

    def update_company_email(self, company_id, email):
        """Update a company's email field.
        
        Returns True if successful.
        """
        resp = self.update_company(company_id, {
            'hs_lead_status': email,  # Store in generic field
        })
        return resp is not None

    # ============================================================================
    # EMAIL TEMPLATES (CRM Email Objects)
    # ============================================================================

    def list_email_templates(self, limit=100, after=None):
        """List all email templates in CRM.
        
        Returns (templates, next_cursor, has_more).
        """
        params = {
            'limit': str(limit),
            'properties': [
                'hs_template_subject',
                'hs_template_html',
                'hs_createdate',
                'hs_lastmodifieddate',
            ],
        }
        if after:
            params['after'] = after
        
        resp = self._request('GET', '/crm/v3/objects/emails', params=params)
        if not resp or 'results' not in resp:
            return [], None, False
        
        results = resp['results']
        paging = resp.get('paging', {})
        next_cursor = paging.get('next', {}).get('after')
        has_more = bool(next_cursor)
        
        return results, next_cursor, has_more

    def get_email_template(self, template_id):
        """Get a specific email template by ID.
        
        Returns template dict or None.
        """
        params = {
            'properties': [
                'hs_template_subject',
                'hs_template_html',
                'hs_createdate',
                'hs_lastmodifieddate',
            ],
        }
        resp = self._request('GET', f'/crm/v3/objects/emails/{template_id}',
                            params=params)
        if resp and 'id' in resp:
            return resp
        return None

    def create_email_template(self, subject, html_content):
        """Create a new email template.
        
        Args:
            subject: Email subject line (can include template variables)
            html_content: HTML body of the email
        
        Returns created template dict or None.
        """
        import time
        
        body = {
            'properties': {
                'hs_template_subject': subject,
                'hs_template_html': html_content,
                'hs_email_direction': 'INBOUND',  # Required field
                'hs_timestamp': str(int(time.time() * 1000)),  # Required field (epoch ms)
            },
        }
        resp = self._request('POST', '/crm/v3/objects/emails', body=body)
        if resp and 'id' in resp:
            return resp
        return None

    def update_email_template(self, template_id, subject=None, html_content=None):
        """Update an existing email template.
        
        Returns updated template dict or None.
        """
        properties = {}
        
        if subject:
            properties['hs_template_subject'] = subject
        if html_content:
            properties['hs_template_html'] = html_content
        
        if not properties:
            return None
        
        body = {'properties': properties}
        resp = self._request('PATCH', f'/crm/v3/objects/emails/{template_id}',
                            body=body)
        if resp and 'id' in resp:
            return resp
        return None

    def delete_email_template(self, template_id):
        """Delete an email template.
        
        Returns True if successful.
        """
        resp = self._request('DELETE', f'/crm/v3/objects/emails/{template_id}')
        return resp is not None and 'error' not in resp

    def send_email_from_template(self, template_id, contact_id):
        """Send an email to a contact using a template.
        
        NOTE: This would require the marketing single-send endpoint.
        For now, returns the template ID and contact ID for manual sending.
        
        Returns dict with template_id and contact_id.
        """
        return {
            'template_id': template_id,
            'contact_id': contact_id,
            'method': 'Use HubSpot Marketing -> Email -> Single Send',
        }
