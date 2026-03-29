"""
Pure utility functions for email processing.
"""

import re
import base64


def strip_reply_prefix(subject: str) -> str:
    """Remove all leading Re:/RE:/re: prefixes from a subject line."""
    return re.sub(r'^(Re:\s*)+', '', subject, flags=re.IGNORECASE).strip()


def extract_body(payload: dict) -> str:
    """Extract plain text body from a Gmail message payload."""
    if 'body' in payload and payload['body'].get('data'):
        return base64.urlsafe_b64decode(payload['body']['data']).decode('utf-8')

    if 'parts' in payload:
        for part in payload['parts']:
            if part['mimeType'] == 'text/plain':
                if part['body'].get('data'):
                    return base64.urlsafe_b64decode(part['body']['data']).decode('utf-8')
            elif 'parts' in part:
                result = extract_body(part)
                if result:
                    return result

    return "(could not extract body)"
