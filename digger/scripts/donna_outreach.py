#!/usr/bin/env python3
"""
Donna Outreach - Send personalized emails using markdown templates.
Triggered via Slack slash command or direct CLI.

Usage:
  python3 donna_outreach.py --template 1st-outreach --company "Dolo's Pizza" --email "yusef@dolos.com" --first-name "Yusef" --sender "Stacey" --preview
  python3 donna_outreach.py --template 1st-outreach --company "Dolo's Pizza" --email "yusef@dolos.com" --first-name "Yusef" --sender "Stacey" --send
"""

import sys
import os
import re
import argparse
from pathlib import Path
import json

TEMPLATES_DIR = Path(os.path.expanduser('~/Library/CloudStorage/Dropbox/Agents/files/Donna Sales/templates'))


def load_template(template_name):
    """Load a template markdown file."""
    template_path = TEMPLATES_DIR / f"{template_name}.md"
    
    if not template_path.exists():
        return None, f"Template not found: {template_path}"
    
    with open(template_path) as f:
        content = f.read()
    
    return content, None


def parse_template(content):
    """Parse template markdown into subject and body."""
    lines = content.strip().split('\n')
    
    subject = None
    body_start = None
    
    # Find subject line
    for i, line in enumerate(lines):
        if line.startswith('**Subject:**'):
            subject = line.replace('**Subject:**', '').strip()
            # Find next --- separator for body start
            for j in range(i + 1, len(lines)):
                if lines[j].strip() == '---':
                    body_start = j + 1
                    break
            break
    
    if not subject or body_start is None:
        return None, None, "Invalid template format. Expected '**Subject:**' line."
    
    # Extract body (everything until final --- or end)
    body_lines = []
    for i in range(body_start, len(lines)):
        line = lines[i]
        # Stop at final --- separator
        if line.strip() == '---' and i > body_start + 2:  # Make sure it's not the first line
            break
        body_lines.append(line)
    
    body = '\n'.join(body_lines).strip()
    
    return subject, body, None


def extract_variables(text):
    """Find all {{variable}} placeholders in text."""
    return set(re.findall(r'\{\{(\w+)\}\}', text))


def render_template(subject, body, variables):
    """Render template with provided variables."""
    text = f"{subject}\n\n{body}"
    
    for key, value in variables.items():
        placeholder = f"{{{{{key}}}}}"
        text = text.replace(placeholder, str(value))
    
    # Split back into subject and body
    parts = text.split('\n\n', 1)
    rendered_subject = parts[0]
    rendered_body = parts[1] if len(parts) > 1 else ""
    
    return rendered_subject, rendered_body


def validate_variables(required_vars, provided_vars):
    """Check if all required variables are provided."""
    missing = required_vars - set(provided_vars.keys())
    return missing


def preview_email(subject, body, to_email):
    """Display email preview."""
    print("\n" + "="*80)
    print("EMAIL PREVIEW")
    print("="*80)
    print(f"To: {to_email}")
    print(f"Subject: {subject}")
    print("\n" + "-"*80)
    print(body)
    print("-"*80 + "\n")


def save_email(subject, body, to_email, template_name):
    """Save email to JSON for manual sending or logging."""
    email_data = {
        'template': template_name,
        'to': to_email,
        'subject': subject,
        'body': body,
        'html': email_to_html(subject, body),
    }
    
    # Save to parent "Donna Sales" directory
    output_file = TEMPLATES_DIR.parent / 'outreach_queue.json'
    
    queue = []
    if output_file.exists():
        with open(output_file) as f:
            queue = json.load(f)
    
    queue.append(email_data)
    
    with open(output_file, 'w') as f:
        json.dump(queue, f, indent=2)
    
    return str(output_file)


def email_to_html(subject, body):
    """Convert plain text email to HTML."""
    # Escape HTML
    body_escaped = body.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    
    # Convert markdown-ish formatting to HTML
    body_escaped = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', body_escaped)
    body_escaped = re.sub(r'\n- ', r'\n<li>', body_escaped)
    body_escaped = re.sub(r'<li>(.+?)\n', r'<li>\1</li>\n', body_escaped)
    
    html = f"""<html>
<head><meta charset='utf-8'></head>
<body style='font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; line-height: 1.6; color: #333;'>
<div style='max-width: 600px; margin: 0 auto; padding: 20px;'>
{body_escaped.replace(chr(10), '<br/>')}
</div>
</body>
</html>"""
    
    return html


def main():
    parser = argparse.ArgumentParser(description='Donna Outreach - Send templated emails')
    parser.add_argument('--template', required=True, help='Template name (without .md)')
    parser.add_argument('--company', required=True, help='Company name')
    parser.add_argument('--email', required=True, help='Recipient email address')
    parser.add_argument('--first-name', required=True, help='Contact first name')
    parser.add_argument('--city', default='', help='City')
    parser.add_argument('--state', default='', help='State')
    parser.add_argument('--sender', default='Stacey', help='Sender name (default: Stacey)')
    parser.add_argument('--preview', action='store_true', help='Preview email without saving')
    parser.add_argument('--save', action='store_true', help='Save to queue for manual sending')
    parser.add_argument('--slack-format', action='store_true', help='Output in Slack message format')
    
    args = parser.parse_args()
    
    # Load template
    content, error = load_template(args.template)
    if error:
        print(f"ERROR: {error}")
        sys.exit(1)
    
    # Parse template
    subject_template, body_template, error = parse_template(content)
    if error:
        print(f"ERROR: {error}")
        sys.exit(1)
    
    # Find required variables
    required_vars = extract_variables(f"{subject_template}\n{body_template}")
    required_vars.discard('sender_name')  # Has default
    
    # Prepare variables
    variables = {
        'company_name': args.company,
        'first_name': args.first_name,
        'sender_name': args.sender,
        'city': args.city,
        'state': args.state,
    }
    
    # Validate
    missing = validate_variables(required_vars, variables)
    if missing:
        print(f"ERROR: Missing variables: {', '.join(missing)}")
        sys.exit(1)
    
    # Render
    subject, body = render_template(subject_template, body_template, variables)
    
    # Output
    if args.preview:
        preview_email(subject, body, args.email)
        print("✓ Preview mode (not saved)")
    elif args.save:
        queue_file = save_email(subject, body, args.email, args.template)
        print(f"✓ Email saved to queue: {queue_file}")
        preview_email(subject, body, args.email)
    elif args.slack_format:
        # Output as Slack-friendly JSON
        output = {
            'to': args.email,
            'subject': subject,
            'body': body,
            'template': args.template,
        }
        print(json.dumps(output, indent=2))
    else:
        # Default: preview
        preview_email(subject, body, args.email)


if __name__ == '__main__':
    main()
