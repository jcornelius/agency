#!/usr/bin/env python3
"""
Upload Atlanta restaurant contacts to HubSpot.
Reads from atlanta-all-contacts.csv and creates/updates HubSpot contacts and companies.
"""

import csv
import sys
import os
import time
sys.path.insert(0, '/Users/jc/openclaw-workspaces/digger/scripts')

from hubspot_client import HubSpotClient

# Use the token from migrate script
HUBSPOT_TOKEN = os.environ.get('HUBSPOT_PRIVATE_APP_TOKEN') or 'pat-na2-74dc0c43-f065-4a38-b382-8ee4a23d50c0'

def main():
    input_file = '/Users/jc/Desktop/tmp/atlanta-all-contacts.csv'
    
    if not os.path.exists(input_file):
        print(f"ERROR: {input_file} not found")
        sys.exit(1)
    
    client = HubSpotClient(HUBSPOT_TOKEN)
    
    # Test connection
    if not client.test_connection():
        print("ERROR: Cannot connect to HubSpot")
        sys.exit(1)
    
    print("✓ Connected to HubSpot")
    
    contacts_created = 0
    contacts_skipped = 0
    companies_updated = 0
    
    with open(input_file) as f:
        reader = csv.DictReader(f)
        
        for i, row in enumerate(reader, start=2):
            business_name = row.get('business_name', '').strip()
            contact_name = row.get('contact_name', '').strip()
            contact_email = row.get('contact_email', '').strip()
            phone = row.get('phone', '').strip()
            confidence = row.get('confidence', '').strip()
            
            if not business_name:
                continue
            
            # Skip if no contact info
            if not contact_name or not contact_email:
                print(f"[{i}] SKIP: {business_name} (no verified contact)")
                contacts_skipped += 1
                continue
            
            # Parse contact name into first/last
            name_parts = contact_name.split(' ', 1)
            firstname = name_parts[0]
            lastname = name_parts[1] if len(name_parts) > 1 else ''
            
            # Create contact in HubSpot
            contact_payload = {
                'firstname': firstname,
                'lastname': lastname,
                'email': contact_email,
                'phone': phone if phone else '',
                'company': business_name,
            }
            
            contact_result = client.create_contact(contact_payload)
            if contact_result and 'id' in contact_result:
                contact_id = contact_result['id']
                print(f"[{i}] ✓ Created contact: {contact_name} ({contact_email})")
                contacts_created += 1
                
                # Try to link to company
                company = client.find_company(name=business_name)
                if company:
                    company_id = company['id']
                    if client.associate_contact_to_company(company_id, contact_id):
                        print(f"     ✓ Linked to company: {business_name}")
                        companies_updated += 1
                else:
                    print(f"     ⚠ Company not found: {business_name}")
            else:
                print(f"[{i}] ✗ Failed to create contact: {contact_name}")
            
            # Rate limit
            time.sleep(0.3)
    
    print()
    print("=" * 60)
    print(f"UPLOAD COMPLETE")
    print(f"  Contacts created: {contacts_created}")
    print(f"  Contacts skipped: {contacts_skipped}")
    print(f"  Companies linked: {companies_updated}")
    print("=" * 60)

if __name__ == '__main__':
    main()
