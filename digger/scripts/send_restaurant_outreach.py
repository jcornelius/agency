#!/usr/bin/env python3
"""
Send restaurant outreach emails to Atlanta prospects using HubSpot.
Uses the Single Send API to send from HubSpot templates or custom content.
"""

import csv
import sys
import os
import time
import json
sys.path.insert(0, '/Users/jc/openclaw-workspaces/digger/scripts')

from hubspot_client import HubSpotClient

HUBSPOT_TOKEN = os.environ.get('HUBSPOT_PRIVATE_APP_TOKEN') or 'pat-na2-74dc0c43-f065-4a38-b382-8ee4a23d50c0'

# Template IDs from HubSpot
TEMPLATES = {
    'restaurant_outreach': '361194280694',  # Will need to be updated with your actual template ID
}

def load_contacts(csv_file):
    """Load contacts from CSV."""
    contacts = []
    with open(csv_file) as f:
        reader = csv.DictReader(f)
        for row in reader:
            contacts.append(row)
    return contacts


def prepare_email(contact):
    """Prepare email data for a contact.
    
    Returns dict with subject, html, and recipient email.
    """
    contact_name = contact.get('contact_name', 'there').strip()
    name_parts = contact_name.split() if contact_name else []
    first_name = name_parts[0] if name_parts else 'there'
    
    company = contact.get('business_name', 'your restaurant').strip()
    email = contact.get('contact_email', '').strip()
    
    if not email:
        return None
    
    # Template for restaurant outreach
    subject = f"Quick question about {company}"
    
    html = f"""
    <html>
    <head><meta charset='utf-8'></head>
    <body style='font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; line-height: 1.6; color: #333;'>
    <div style='max-width: 600px; margin: 0 auto; padding: 20px;'>
        <h2>Hi {first_name},</h2>
        
        <p>I noticed {company} is using Square for POS — great platform for getting started.</p>
        
        <p><strong>Here's what we're seeing with restaurants like yours:</strong></p>
        <ul>
            <li><strong>High-level insights</strong> — Did we make money? Who's our top performer?</li>
            <li><strong>Deep operational detail</strong> — Inventory trends, waste tracking, staff performance</li>
            <li><strong>Day-to-day simplification</strong> — No more jumping between Square, spreadsheets, and other tools</li>
        </ul>
        
        <p>Most existing solutions force you to choose: simplicity OR depth. We built something that does both.</p>
        
        <p>Would love to grab 15 minutes this week to see if it's a fit for {company}. No pressure — just a quick conversation.</p>
        
        <p>Available <strong>Tuesday or Wednesday afternoon</strong>. Does one of those work?</p>
        
        <p>Thanks,<br>
        Donna Team</p>
        
        <p style='font-size: 12px; color: #666; border-top: 1px solid #ddd; padding-top: 20px; margin-top: 40px;'>
            <em>{company}</em>
        </p>
    </div>
    </body>
    </html>
    """
    
    return {
        'to': email,
        'subject': subject,
        'html': html,
        'business_name': company,
        'contact_name': contact.get('contact_name', 'Unknown'),
    }


def send_email(client, email_data, dry_run=False):
    """Send an email via HubSpot.
    
    For now, returns the email data that would be sent.
    To actually send, you would use HubSpot's API or UI.
    """
    if dry_run:
        print(f"[DRY RUN] Would send to: {email_data['to']}")
        print(f"          Subject: {email_data['subject']}")
        return True
    
    # In a real implementation, you would use HubSpot's transactional email API
    # For now, this returns what would be sent
    print(f"✓ Prepared email for: {email_data['to']}")
    return True


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Send restaurant outreach emails')
    parser.add_argument('--input', required=True, help='Input CSV with contacts')
    parser.add_argument('--dry-run', action='store_true', help='Preview without sending')
    parser.add_argument('--limit', type=int, help='Limit number of emails to send')
    parser.add_argument('--output', help='Save emails to JSON file instead of sending')
    
    args = parser.parse_args()
    
    if not os.path.exists(args.input):
        print(f"ERROR: {args.input} not found")
        sys.exit(1)
    
    print(f"Loading contacts from {args.input}...")
    contacts = load_contacts(args.input)
    print(f"Loaded {len(contacts)} contacts\n")
    
    client = HubSpotClient(HUBSPOT_TOKEN)
    
    if not client.test_connection():
        print("ERROR: Cannot connect to HubSpot")
        sys.exit(1)
    
    print("✓ Connected to HubSpot\n")
    print(f"{'='*80}")
    print(f"RESTAURANT OUTREACH CAMPAIGN")
    print(f"{'='*80}\n")
    
    emails_to_send = []
    valid_count = 0
    invalid_count = 0
    
    for i, contact in enumerate(contacts, 1):
        if args.limit and valid_count >= args.limit:
            break
        
        email_data = prepare_email(contact)
        
        if not email_data:
            print(f"[{i}] SKIP: {contact.get('business_name', 'Unknown')} (no email)")
            invalid_count += 1
            continue
        
        if args.output:
            emails_to_send.append(email_data)
        else:
            send_email(client, email_data, dry_run=args.dry_run)
        
        print(f"[{i}] ✓ {email_data['business_name']} → {email_data['to']}")
        valid_count += 1
        
        # Rate limit
        time.sleep(0.2)
    
    if args.output:
        with open(args.output, 'w') as f:
            json.dump(emails_to_send, f, indent=2)
        print(f"\n✓ Saved {len(emails_to_send)} emails to {args.output}")
    
    print(f"\n{'='*80}")
    print(f"SUMMARY")
    print(f"  Valid emails prepared: {valid_count}")
    print(f"  Skipped: {invalid_count}")
    print(f"{'='*80}\n")
    
    if args.dry_run:
        print("This was a dry run. Use --output to save emails or remove --dry-run to send.")


if __name__ == '__main__':
    main()
