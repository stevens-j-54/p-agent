"""
Email service - handles Gmail API operations
"""

import logging
import os
import base64
from email.mime.text import MIMEText

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from config import SCOPES
from utils.email_utils import strip_reply_prefix, extract_body

logger = logging.getLogger(__name__)


class EmailService:
    """Handles Gmail API operations."""

    def __init__(self):
        self.service = None
        self.creds = None

    def authenticate(self, force_new=False):
        """Authenticate with Gmail API."""
        # Load token from environment variable if available (for production)
        if os.environ.get('GOOGLE_TOKEN_JSON'):
            with open('token.json', 'w') as f:
                f.write(os.environ['GOOGLE_TOKEN_JSON'])

        creds = None

        if os.path.exists('token.json') and not force_new:
            creds = Credentials.from_authorized_user_file('token.json', SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                logger.info("Refreshing expired Gmail credentials")
                creds.refresh(Request())
            else:
                if not os.path.exists('credentials.json'):
                    raise FileNotFoundError(
                        "credentials.json not found. Download it from Google Cloud Console."
                    )
                logger.info("Starting OAuth flow...")
                flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
                creds = flow.run_local_server(port=0)

            with open('token.json', 'w') as token:
                token.write(creds.to_json())
                logger.info("Credentials saved to token.json")

        self.creds = creds
        self.service = build('gmail', 'v1', credentials=creds)
        logger.info("Gmail API authenticated")
        return self

    def get_unread_emails(self):
        """Fetch unread emails from inbox."""
        try:
            results = self.service.users().messages().list(
                userId='me',
                q='is:unread in:inbox',
                maxResults=10
            ).execute()

            messages = results.get('messages', [])
            return messages
        except HttpError as error:
            logger.error("Failed to fetch emails: %s", error)
            return []

    def get_email_details(self, msg_id):
        """Get full details of an email."""
        try:
            message = self.service.users().messages().get(
                userId='me',
                id=msg_id,
                format='full'
            ).execute()

            headers = message['payload']['headers']

            subject = next((h['value'] for h in headers if h['name'].lower() == 'subject'), '(no subject)')
            sender = next((h['value'] for h in headers if h['name'].lower() == 'from'), 'unknown')
            message_id = next((h['value'] for h in headers if h['name'].lower() == 'message-id'), None)

            body = extract_body(message['payload'])

            return {
                'id': msg_id,
                'subject': subject,
                'sender': sender,
                'body': body,
                'thread_id': message['threadId'],
                'message_id': message_id
            }
        except HttpError as error:
            logger.error("Failed to get email details for %s: %s", msg_id, error)
            return None

    def send_reply(self, original_email, reply_text):
        """Send a reply to an email."""
        try:
            message = MIMEText(reply_text)
            message['to'] = original_email['sender']
            message['subject'] = f"Re: {strip_reply_prefix(original_email['subject'])}"
            if original_email.get('message_id'):
                message['In-Reply-To'] = original_email['message_id']
                message['References'] = original_email['message_id']

            raw = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')

            sent = self.service.users().messages().send(
                userId='me',
                body={
                    'raw': raw,
                    'threadId': original_email['thread_id']
                }
            ).execute()

            logger.info("Reply sent (ID: %s)", sent['id'])
            return sent
        except HttpError as error:
            logger.error("Failed to send reply: %s", error)
            return None

    def get_thread_context(self, thread_id, current_msg_id):
        """
        Fetch prior messages in a thread as a list of {role, content} dicts.

        Uses Gmail's SENT label to distinguish agent replies (assistant) from
        incoming emails (user). Returns at most 10 prior messages so thread
        history doesn't dominate the context window.
        """
        try:
            thread = self.service.users().threads().get(
                userId='me',
                id=thread_id,
                format='full'
            ).execute()

            history = []
            for msg in thread.get('messages', []):
                if msg['id'] == current_msg_id:
                    continue
                label_ids = msg.get('labelIds', [])
                role = 'assistant' if 'SENT' in label_ids else 'user'
                body = extract_body(msg['payload'])
                history.append({'role': role, 'content': body})

            return history[-10:]
        except HttpError as error:
            logger.error("Failed to get thread context for %s: %s", thread_id, error)
            return []

    def mark_as_read(self, msg_id):
        """Mark an email as read."""
        try:
            self.service.users().messages().modify(
                userId='me',
                id=msg_id,
                body={'removeLabelIds': ['UNREAD']}
            ).execute()
        except HttpError as error:
            logger.error("Failed to mark email as read (%s): %s", msg_id, error)
