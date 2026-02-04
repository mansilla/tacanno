"""
Gmail Agent - Pulls emails and uses AI to classify and extract expenses.
"""
import os
import json
import base64
from datetime import datetime, timezone
from typing import List, Tuple, Optional
from openai import OpenAI

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

import config
from db import save_expense, get_sync_state, set_sync_state, email_already_processed

# Gmail API scope
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

# OpenAI client
client = OpenAI(api_key=config.OPENAI_API_KEY)


def get_gmail_service():
    """Authenticate and return Gmail API service."""
    creds = None
    credentials_file = config.GMAIL_CREDENTIALS_FILE
    token_file = config.GMAIL_TOKEN_FILE

    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(credentials_file):
                raise FileNotFoundError(
                    f"Missing {credentials_file}. Download OAuth credentials from "
                    "https://console.cloud.google.com/apis/credentials"
                )
            flow = InstalledAppFlow.from_client_secrets_file(credentials_file, SCOPES)
            creds = flow.run_local_server(port=0)

        with open(token_file, 'w') as token:
            token.write(creds.to_json())

    return build('gmail', 'v1', credentials=creds)


def extract_email_body(payload) -> str:
    """Recursively extract plain text body from email payload."""
    body = ""

    if 'body' in payload and payload['body'].get('data'):
        body = base64.urlsafe_b64decode(payload['body']['data']).decode('utf-8', errors='ignore')

    if 'parts' in payload:
        for part in payload['parts']:
            mime_type = part.get('mimeType', '')
            if mime_type == 'text/plain' and part['body'].get('data'):
                body = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8', errors='ignore')
                break
            elif mime_type.startswith('multipart/'):
                body = extract_email_body(part)
                if body:
                    break

    return body


def fetch_new_emails(service, max_results: int = 50) -> List[dict]:
    """
    Fetch new emails since last sync.
    Returns list of email dicts with id, subject, sender, body, date.
    """
    sync_state = get_sync_state()
    last_timestamp = sync_state.get("last_sync_timestamp")

    # Build query - get emails from last sync or last 7 days
    if last_timestamp:
        query = f"after:{last_timestamp[:10].replace('-', '/')}"
    else:
        query = "newer_than:7d"

    results = service.users().messages().list(
        userId='me',
        q=query,
        maxResults=max_results
    ).execute()

    messages = results.get('messages', [])
    emails = []

    for msg in messages:
        try:
            # Skip if already processed
            if email_already_processed(msg['id']):
                continue

            full_msg = service.users().messages().get(
                userId='me',
                id=msg['id'],
                format='full'
            ).execute()

            headers = full_msg.get('payload', {}).get('headers', [])
            subject = ""
            sender = ""
            date = ""

            for header in headers:
                name = header.get('name', '').lower()
                if name == 'subject':
                    subject = header.get('value', '')
                elif name == 'from':
                    sender = header.get('value', '')
                elif name == 'date':
                    date = header.get('value', '')

            body = extract_email_body(full_msg.get('payload', {}))

            # Truncate body for AI processing
            if len(body) > 2000:
                body = body[:2000] + "..."

            emails.append({
                'id': msg['id'],
                'subject': subject,
                'sender': sender,
                'body': body,
                'date': date
            })

        except Exception:
            continue

    return emails


def classify_email(subject: str, sender: str, body: str) -> dict:
    """
    Use AI to classify if email is expense-related and extract expense data.

    Returns:
        {
            "is_expense": bool,
            "confidence": float,
            "expense_data": {...} or None
        }
    """
    prompt = f"""Analyze this email and determine if it contains information about an expense, purchase, payment, receipt, invoice, or subscription charge.

Email Subject: {subject}
From: {sender}
Body:
{body[:1500]}

Respond with JSON only:
{{
    "is_expense": true/false,
    "confidence": 0.0-1.0,
    "reason": "brief explanation",
    "expense_data": {{
        "date": "YYYY-MM-DD or null",
        "vendor": "company/store name",
        "amount": number or null,
        "currency": "USD/EUR/etc or null",
        "category": "Food/Transport/Shopping/Subscription/Utilities/Entertainment/Other",
        "notes": "brief description"
    }}
}}

Only set is_expense to true if there's a clear expense with an amount. Marketing emails, newsletters, and promotional content are NOT expenses."""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=500
        )
        content = response.choices[0].message.content.strip()

        # Clean up JSON
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        content = content.strip()

        result = json.loads(content)
        return result

    except Exception as e:
        return {
            "is_expense": False,
            "confidence": 0.0,
            "reason": f"Classification error: {str(e)}",
            "expense_data": None
        }


async def pull_and_process_emails(max_results: int = 50) -> dict:
    """
    Pull new emails from Gmail, classify them with AI, and save expenses.

    Returns:
        {
            "emails_checked": int,
            "expenses_found": int,
            "expenses_saved": int
        }
    """
    service = get_gmail_service()
    emails = fetch_new_emails(service, max_results)

    stats = {
        "emails_checked": len(emails),
        "expenses_found": 0,
        "expenses_saved": 0
    }

    for email in emails:
        # Classify with AI
        classification = classify_email(
            email['subject'],
            email['sender'],
            email['body']
        )

        if classification.get('is_expense') and classification.get('confidence', 0) >= 0.7:
            stats["expenses_found"] += 1

            expense_data = classification.get('expense_data')
            if expense_data and expense_data.get('amount'):
                expense_data['source'] = 'gmail'
                expense_data['email_id'] = email['id']
                expense_data['notes'] = f"{expense_data.get('notes', '')} [From: {email['sender']}]".strip()

                try:
                    save_expense(expense_data)
                    stats["expenses_saved"] += 1
                except Exception:
                    pass  # Skip duplicates or errors

    # Update sync timestamp
    set_sync_state(timestamp=datetime.now(timezone.utc).isoformat())

    return stats
