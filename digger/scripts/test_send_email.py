#!/usr/bin/env python3
"""
Test send an email via HubSpot using a template.
"""

import sys
import os
import json
sys.path.insert(0, '/Users/jc/openclaw-workspaces/digger/scripts')

from hubspot_client import HubSpotClient

HUBSPOT_TOKEN = os.environ.get('HUBSPOT_PRIVATE_APP_TOKEN') or 'pat-na2-74dc0c43-f065-4a38-b382-8ee4a23d50c0'

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Test send email via HubSpot')
    parser.add_argument('--template-id', required=True, help='HubSpot template ID')
    parser.add_argument('--to', required=True, help='Recipient email')
    parser.add_argument('--from-name', default='Stacey', help='Sender name')
    parser.add_argument('--subject', help='Email subject (override template)')
    parser.add_argument('--html', help='Email HTML (override template)')
    
    args = parser.parse_args()
    
    client = HubSpotClient(HUBSPOT_TOKEN)
    
    if not client.test_connection():
        print("ERROR: Cannot connect to HubSpot")
        sys.exit(1)
    
    print("✓ Connected to HubSpot\n")
    
    # Get the template
    print(f"Fetching template {args.template_id}...")
    tmpl = client.get_email_template(args.template_id)
    
    if tmpl:
        props = tmpl.get('properties', {})
        subject = props.get('hs_template_subject', 'No subject')
        html = props.get('hs_template_html', '')
        
        print(f"✓ Template found")
        print(f"  Subject: {subject}")
        print(f"  HTML length: {len(html)} chars")
    else:
        print(f"✗ Template not found: {args.template_id}")
        sys.exit(1)
    
    # Override if provided
    if args.subject:
        subject = args.subject
    if args.html:
        html = args.html
    
    print(f"\n{'='*80}")
    print(f"SENDING TEST EMAIL")
    print(f"{'='*80}\n")
    
    print(f"To: {args.to}")
    print(f"From: {args.from_name}")
    print(f"Subject: {subject}")
    print(f"Template ID: {args.template_id}")
    print()
    
    # In a real scenario, you would use HubSpot's transactional email API
    # For now, show what would be sent
    print("✓ Email prepared and ready to send via HubSpot")
    print("\nTo send via HubSpot:")
    print("1. Go to HubSpot CRM → Contacts")
    print(f"2. Find or create contact: {args.to}")
    print("3. Click 'Send email' and select the template")
    print("4. Personalize and send")
    print()
    print("Or use HubSpot's transactional email API endpoint:")
    print(f"  POST /crm/v3/objects/marketing-emails/send")
    print(f"  Body: {{'emailId': '{args.template_id}', 'to': '{args.to}', 'senderName': '{args.from_name}'}}")


if __name__ == '__main__':
    main()
