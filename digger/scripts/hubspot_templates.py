#!/usr/bin/env python3
"""
HubSpot Message Templates Manager
List, retrieve, create, update, and delete HubSpot message templates via API.
"""

import sys
import os
import json
sys.path.insert(0, '/Users/jc/openclaw-workspaces/digger/scripts')

from hubspot_client import HubSpotClient

HUBSPOT_TOKEN = os.environ.get('HUBSPOT_PRIVATE_APP_TOKEN') or 'pat-na2-74dc0c43-f065-4a38-b382-8ee4a23d50c0'


def list_templates(client):
    """List all email templates."""
    print("Fetching email templates from HubSpot...")
    templates, next_cursor, has_more = client.list_email_templates(limit=100)
    
    if not templates:
        print("No templates found.")
        return
    
    print(f"\n{'='*80}")
    print(f"EMAIL TEMPLATES ({len(templates)} found)")
    print(f"{'='*80}\n")
    
    for i, tmpl in enumerate(templates, 1):
        tmpl_id = tmpl.get('id')
        props = tmpl.get('properties', {})
        subject = props.get('hs_template_subject', 'No subject')
        created = tmpl.get('createdAt', 'N/A')
        
        print(f"{i}. [{tmpl_id}]")
        print(f"   Subject: {subject[:60]}")
        print(f"   Created: {created}")
        print()


def get_template_detail(client, template_id):
    """Get detailed info for a specific email template."""
    print(f"Fetching template {template_id}...")
    tmpl = client.get_email_template(template_id)
    
    if not tmpl:
        print(f"Template {template_id} not found.")
        return
    
    props = tmpl.get('properties', {})
    subject = props.get('hs_template_subject', 'No subject')
    html = props.get('hs_template_html', '')
    
    print(f"\n{'='*80}")
    print(f"EMAIL TEMPLATE DETAIL")
    print(f"{'='*80}\n")
    
    print(f"ID: {tmpl.get('id')}")
    print(f"Subject: {subject}")
    print(f"Created: {tmpl.get('createdAt')}")
    print(f"Updated: {tmpl.get('updatedAt')}")
    
    if html:
        print(f"\nHTML Content Preview:")
        print(html[:500] + ('...' if len(html) > 500 else ''))
    
    print()


def create_template_interactive(client):
    """Create a new email template interactively."""
    print(f"\n{'='*80}")
    print("CREATE NEW EMAIL TEMPLATE")
    print(f"{'='*80}\n")
    
    subject = input("Email subject line (can include {{variables}}): ").strip()
    if not subject:
        print("Subject required.")
        return
    
    print("Enter HTML content for email body. Type EOF on a new line to finish:")
    lines = []
    while True:
        line = input()
        if line == 'EOF':
            break
        lines.append(line)
    
    html = '\n'.join(lines)
    if not html:
        print("Email content required.")
        return
    
    print(f"\nCreating template with subject: {subject}")
    tmpl = client.create_email_template(subject, html)
    
    if tmpl and 'id' in tmpl:
        print(f"✓ Email template created successfully!")
        print(f"  ID: {tmpl.get('id')}")
        props = tmpl.get('properties', {})
        print(f"  Subject: {props.get('hs_template_subject')}")
    else:
        print(f"✗ Failed to create template")


def create_template_file(client, template_file):
    """Create email template from a JSON file.
    
    File format:
    {
        "subject": "Email Subject",
        "htmlContent": "<html>...</html>"
    }
    """
    if not os.path.exists(template_file):
        print(f"File not found: {template_file}")
        return
    
    try:
        with open(template_file) as f:
            data = json.load(f)
    except Exception as e:
        print(f"Error reading file: {e}")
        return
    
    subject = data.get('subject')
    html = data.get('htmlContent')
    
    if not all([subject, html]):
        print("File must contain: subject, htmlContent")
        return
    
    print(f"Creating email template from file")
    tmpl = client.create_email_template(subject, html)
    
    if tmpl and 'id' in tmpl:
        print(f"✓ Email template created!")
        print(f"  ID: {tmpl.get('id')}")
        props = tmpl.get('properties', {})
        print(f"  Subject: {props.get('hs_template_subject')}")
    else:
        print(f"✗ Failed to create template")


def export_template(client, template_id, output_file):
    """Export an email template to a JSON file."""
    print(f"Fetching template {template_id}...")
    tmpl = client.get_email_template(template_id)
    
    if not tmpl:
        print(f"Template not found: {template_id}")
        return
    
    props = tmpl.get('properties', {})
    export_data = {
        'id': tmpl.get('id'),
        'subject': props.get('hs_template_subject'),
        'htmlContent': props.get('hs_template_html'),
        'createdAt': tmpl.get('createdAt'),
        'updatedAt': tmpl.get('updatedAt'),
    }
    
    with open(output_file, 'w') as f:
        json.dump(export_data, f, indent=2)
    
    print(f"✓ Email template exported to: {output_file}")


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='HubSpot Message Templates Manager')
    parser.add_argument('--list', action='store_true', help='List all templates')
    parser.add_argument('--get', metavar='TEMPLATE_ID', help='Get template details')
    parser.add_argument('--create', action='store_true', help='Create new template (interactive)')
    parser.add_argument('--create-from-file', metavar='FILE', help='Create template from JSON file')
    parser.add_argument('--export', metavar='TEMPLATE_ID', help='Export template to JSON')
    parser.add_argument('--export-to', metavar='FILE', default='template_export.json', 
                       help='Export output file (default: template_export.json)')
    
    args = parser.parse_args()
    
    client = HubSpotClient(HUBSPOT_TOKEN)
    
    if not client.test_connection():
        print("ERROR: Cannot connect to HubSpot")
        sys.exit(1)
    
    print("✓ Connected to HubSpot\n")
    
    if args.list:
        list_templates(client)
    elif args.get:
        get_template_detail(client, args.get)
    elif args.create:
        create_template_interactive(client)
    elif args.create_from_file:
        create_template_file(client, args.create_from_file)
    elif args.export:
        export_template(client, args.export, args.export_to)
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
