"""
FetchService - HTTP fetch and content extraction for agent use
"""

import logging
import re

import requests
from requests.exceptions import RequestException

logger = logging.getLogger(__name__)

# Reasonable timeout for external HTTP requests
REQUEST_TIMEOUT = 15

# Hard cap on returned content length to avoid overwhelming the context window
MAX_CONTENT_LENGTH = 50_000


class FetchService:
    """Fetches URLs and returns clean, readable text content."""

    def fetch_url(self, url: str, max_length: int = MAX_CONTENT_LENGTH) -> dict:
        """
        Fetch a URL and return its text content, stripped of HTML tags and boilerplate.

        Returns a dict with:
            success (bool)
            url (str)
            content (str)  — cleaned text, truncated to max_length
            truncated (bool) — True if content was cut off
            error (str)    — present on failure
        """
        try:
            logger.info("Fetching URL: %s", url)
            headers = {
                # Identify as a browser to avoid bot-blocking on most sites
                "User-Agent": (
                    "Mozilla/5.0 (compatible; Stevens-Agent/1.0; "
                    "+https://github.com/stevens-j-54)"
                )
            }
            response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()

            content_type = response.headers.get("content-type", "")
            if "text/html" in content_type or "text/plain" in content_type:
                raw = response.text
                cleaned = self._clean_html(raw)
            elif "application/json" in content_type:
                # JSON doesn't need HTML cleaning — return as-is
                cleaned = response.text
            else:
                # For non-text content types, return a helpful message rather than binary noise
                return {
                    "success": False,
                    "url": url,
                    "error": f"Unsupported content type: {content_type}. Only HTML and plain text are supported."
                }

            truncated = len(cleaned) > max_length

            if truncated:
                cleaned = cleaned[:max_length]

            return {
                "success": True,
                "url": url,
                "content": cleaned,
                "truncated": truncated,
            }

        except RequestException as e:
            logger.error("Failed to fetch %s: %s", url, e)
            return {"success": False, "url": url, "error": str(e)}
        except Exception as e:
            logger.error("Unexpected error fetching %s: %s", url, e)
            return {"success": False, "url": url, "error": str(e)}

    def _clean_html(self, html: str) -> str:
        """
        Strip HTML tags and reduce whitespace to produce readable plain text.
        Not a full parser — good enough for article/news content.
        """
        # Remove <script> and <style> blocks entirely
        text = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.DOTALL | re.IGNORECASE)
        # Remove all remaining HTML tags
        text = re.sub(r"<[^>]+>", " ", text)
        # Decode common HTML entities
        text = (
            text
            .replace("&amp;", "&")
            .replace("&lt;", "<")
            .replace("&gt;", ">")
            .replace("&quot;", '"')
            .replace("&#39;", "'")
            .replace("&nbsp;", " ")
        )
        # Collapse whitespace
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r" {2,}", " ", text)
        return text.strip()
