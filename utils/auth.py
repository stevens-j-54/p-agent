"""
Pure authorization helpers.
"""

import logging

from config import AUTHORIZED_SENDERS, TELEGRAM_AUTHORIZED_IDS

logger = logging.getLogger(__name__)


def is_authorized_email_sender(sender: str) -> bool:
    """Check if an email sender is in the authorized list."""
    if not AUTHORIZED_SENDERS:
        logger.error("No authorized senders configured — rejecting all emails")
        return False

    email = sender
    if '<' in sender:
        email = sender.split('<')[1].split('>')[0]

    return email.lower() in [s.lower() for s in AUTHORIZED_SENDERS]


def is_authorized_telegram_user(user_id: int) -> bool:
    """Check if a Telegram user ID is in the authorized list."""
    if not TELEGRAM_AUTHORIZED_IDS:
        logger.error("No authorized Telegram users configured — rejecting all messages")
        return False
    return user_id in TELEGRAM_AUTHORIZED_IDS
