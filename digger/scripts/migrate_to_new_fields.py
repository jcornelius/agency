#!/usr/bin/env python3
"""
Migrate existing HubSpot companies to use the new field structure:
- Rename 'website' → 'primary_website'
- Populate 'square_online_url' from 'square_url'
- Calculate 'square_confidence' based on available data
"""

import sys
sys.path.insert(0, '/Users/jc/openclaw-workspaces/digger/scripts')

from hubspot_client import HubSpotClient
import os
import time

token = os.environ.get('HUBSPOT_PRIVATE_APP_TOKEN', 'pat-na2-74dc0c43-f065-4a38-b382-8ee4a23d50c0')
hubspot = HubSpotClient(token)

print("=" * 80)
print("HUBSPOT COMPANY FIELD MIGRATION")
print("Migrating to new field structure: primary_website, square_online_url, square_confidence")
print("=" * 80)

# Fetch all companies
print("\nFetching all companies from HubSpot...")
all_companies = []
cursor = None
while True:
    batch, cursor, has_more = hubspot.list_companies(limit=100, after=cursor)
    all_companies.extend(batch)
    print(f"  Fetched {len(batch)} companies (total: {len(all_companies)})")
    if not has_more or not batch:
        break

print(f"\nTotal companies to migrate: {len(all_companies)}\n")

# Process each company
migrated_count = 0
skipped_count = 0
error_count = 0

for i, company in enumerate(all_companies, 1):
    company_id = company.get('id', '')
    props = company.get('properties', {})
    
    # Check if already migrated
    if 'primary_website' in props or 'square_online_url' in props:
        skipped_count += 1
        continue
    
    # Build migration payload
    update_payload = {}
    
    # Migrate website → primary_website
    if props.get('website'):
        update_payload['primary_website'] = props.get('website')
    
    # Migrate square_url → square_online_url
    if props.get('square_url'):
        update_payload['square_online_url'] = props.get('square_url')
    
    # Calculate square_confidence
    website = props.get('website', '')
    square_url = props.get('square_url', '')
    confidence = props.get('confidence', '')
    
    square_confidence = 'needs_review'
    if square_url and website:
        square_confidence = 'multi_platform'
    elif square_url and not website:
        square_confidence = 'has_square_site'
    elif square_url:
        square_confidence = 'confirmed_square'
    
    if confidence and 'confirm' in confidence.lower():
        square_confidence = 'confirmed_square'
    
    update_payload['square_confidence'] = square_confidence
    
    # Only update if there's something to migrate
    if not update_payload:
        skipped_count += 1
        continue
    
    # Update company in HubSpot
    try:
        result = hubspot.update_company(company_id, update_payload)
        if result:
            migrated_count += 1
            company_name = props.get('name', 'Unknown')
            print(f"[{i:3d}/{len(all_companies)}] ✅ {company_name[:50]:<50} | confidence: {square_confidence}")
        else:
            error_count += 1
            print(f"[{i:3d}/{len(all_companies)}] ❌ Failed to update {company_id}")
    except Exception as e:
        error_count += 1
        print(f"[{i:3d}/{len(all_companies)}] ❌ Error updating {company_id}: {str(e)[:60]}")
    
    # Rate limit
    if i % 20 == 0:
        time.sleep(1)

print("\n" + "=" * 80)
print(f"MIGRATION COMPLETE")
print(f"  ✅ Migrated: {migrated_count}")
print(f"  ⏭️  Skipped: {skipped_count}")
print(f"  ❌ Errors: {error_count}")
print("=" * 80)
