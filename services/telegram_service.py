"""
Telegram service — handles Telegram Bot API operations via long-polling.
"""

import logging
import requests

logger = logging.getLogger(__name__)

TELEGRAM_API_BASE = "https://api.telegram.org/bot{token}/{method}"


class TelegramService:
    """Polls for Telegram updates and sends messages via the Bot API."""

    def __init__(self, token: str):
        self.token = token
        self._offset = 0

    def _url(self, method: str) -> str:
        return TELEGRAM_API_BASE.format(token=self.token, method=method)

    def skip_pending(self):
        """
        Advance the offset past any messages that arrived before startup.
        This prevents the agent from processing a backlog of old messages
        when it restarts. Messages sent during downtime are silently skipped.
        """
        updates = self._fetch_updates()
        if updates:
            logger.info("Skipped %d pending Telegram message(s) from before startup", len(updates))

    def get_updates(self) -> list:
        """Return new updates since the last call."""
        return self._fetch_updates()

    def _fetch_updates(self) -> list:
        try:
            resp = requests.get(
                self._url("getUpdates"),
                params={
                    "offset": self._offset,
                    "timeout": 0,
                    "allowed_updates": ["message"],
                },
                timeout=10,
            )
            resp.raise_for_status()
            updates = resp.json().get("result", [])
            if updates:
                self._offset = updates[-1]["update_id"] + 1
            return updates
        except Exception as e:
            logger.error("Failed to get Telegram updates: %s", e)
            return []

    def send_message(self, chat_id: int, text: str) -> dict:
        """Send a text message to a chat."""
        try:
            resp = requests.post(
                self._url("sendMessage"),
                json={"chat_id": chat_id, "text": text},
                timeout=10,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error("Failed to send Telegram message to %s: %s", chat_id, e)
            return None
