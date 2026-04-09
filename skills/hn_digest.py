"""
HN Digest Skill

Fetches the top HN stories via the Firebase API, scores them for relevance,
fetches each article's full content, and returns structured data for the agent
to synthesise into a digest.

The agent (Claude) is responsible for:
  - Writing a genuine summary of each article from the raw content
  - Identifying themes, connections, and insights across articles
  - Saving structured notes to the workspace under research/hn-YYYY-MM-DD/

This skill deliberately does NOT pre-format or pre-summarise. That work belongs
to the language model, not to a text-truncation heuristic.
"""

import json
import logging
from datetime import datetime, timezone
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

HN_FRONT_PAGE = "https://news.ycombinator.com"
HN_API_TOP = "https://hacker-news.firebaseio.com/v0/topstories.json"
HN_API_ITEM = "https://hacker-news.firebaseio.com/v0/item/{}.json"

# How many top story IDs to consider before scoring and shortlisting
HN_FETCH_LIMIT = 30

# Max characters of raw article content to return per story.
# At ~4 chars/token this is ~1500 tokens each, totalling ~9k tokens for 6 articles.
CONTENT_MAX_CHARS = 6_000

# Number of top stories to shortlist and return
TOP_N = 6

# Topics relevant to Hugh's work — used as a rubric for scoring stories.
RELEVANCE_TOPICS = [
    "artificial intelligence",
    "machine learning",
    "llm",
    "language model",
    "ai agent",
    "autonomous agent",
    "software engineering",
    "developer tools",
    "startup",
    "product",
    "programming",
    "open source",
    "api",
    "infrastructure",
    "data",
    "python",
    "web development",
    "security",
    "productivity",
    "claude",
    "anthropic",
    "openai",
    "gpt",
    "agent",
]


class HNDigestSkill:
    """
    Orchestrates the HN digest data-gathering pipeline.

    Depends on:
      - fetch_service: FetchService — for HTTP fetching
    """

    def __init__(self, fetch_service):
        self.fetch = fetch_service

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def run(self) -> dict:
        """
        Execute the digest pipeline.

        Returns a dict with:
          - success: bool
          - date: str  (YYYY-MM-DD)
          - output_folder: str  (suggested workspace path, e.g. "research/hn-YYYY-MM-DD")
          - articles: list[dict]  (structured article data for the agent to synthesise)
          - error: str  (only present on failure)

        Each article dict contains:
          - title: str
          - url: str        (the actual article URL, not just a domain)
          - score: int      (HN upvote score)
          - relevance: float (0–1 relevance score)
          - content: str | None  (raw cleaned article text, up to CONTENT_MAX_CHARS)
          - fetch_failed: bool
          - fetch_error: str | None
        """
        try:
            date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            output_folder = f"research/hn-{date_str}"

            # Step 1: Fetch top story IDs + metadata from HN API
            stories = self._fetch_stories()
            if not stories:
                return {"success": False, "error": "No stories returned by HN API"}

            logger.info("HN Digest: fetched %d stories", len(stories))

            # Step 2: Score and shortlist by relevance + score
            shortlisted = self._shortlist(stories, TOP_N)
            logger.info("HN Digest: shortlisted %d stories", len(shortlisted))

            # Step 3: Fetch article content for each shortlisted story
            articles = []
            for story in shortlisted:
                article = self._fetch_content(story)
                articles.append(article)

            return {
                "success": True,
                "date": date_str,
                "output_folder": output_folder,
                "articles": articles,
            }

        except Exception as e:
            logger.error("HN Digest skill failed: %s", e, exc_info=True)
            return {"success": False, "error": str(e)}

    # ------------------------------------------------------------------
    # Story fetching via HN Firebase API
    # ------------------------------------------------------------------

    def _fetch_stories(self) -> list[dict]:
        """
        Fetch the top HN stories with their real article URLs via the Firebase API.

        Uses:
          GET https://hacker-news.firebaseio.com/v0/topstories.json → [id, ...]
          GET https://hacker-news.firebaseio.com/v0/item/{id}.json  → item data

        The HN API item response includes a "url" field with the actual article URL.
        Ask/Show HN posts (no external URL) fall back to their HN discussion page.
        """
        logger.info("HN Digest: fetching top story IDs")
        ids_result = self.fetch.fetch_url(url=HN_API_TOP)
        if not ids_result.get("success"):
            logger.error("HN API top stories fetch failed: %s", ids_result.get("error"))
            return []

        try:
            story_ids = json.loads(ids_result["content"])[:HN_FETCH_LIMIT]
        except (json.JSONDecodeError, KeyError) as exc:
            logger.error("HN API: could not parse story IDs: %s", exc)
            return []

        stories = []
        for story_id in story_ids:
            item_result = self.fetch.fetch_url(url=HN_API_ITEM.format(story_id))
            if not item_result.get("success"):
                continue

            try:
                item = json.loads(item_result["content"])
            except json.JSONDecodeError:
                continue

            if item.get("type") != "story":
                continue

            title = item.get("title", "").strip()
            if not title:
                continue

            article_url = item.get("url") or f"{HN_FRONT_PAGE}/item?id={story_id}"
            score = item.get("score", 0)
            domain = self._extract_domain(article_url)

            stories.append({
                "title": title,
                "url": article_url,
                "domain": domain,
                "score": score,
            })

        return stories

    def _extract_domain(self, url: str) -> str | None:
        """Return the netloc of a URL, or None if unparseable."""
        try:
            return urlparse(url).netloc or None
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Scoring / shortlisting
    # ------------------------------------------------------------------

    def _shortlist(self, stories: list[dict], n: int) -> list[dict]:
        """Score stories for relevance and return the top n."""
        scored = []
        for story in stories:
            relevance = self._relevance_score(story["title"])
            combined = story["score"] * 0.4 + relevance * 60
            scored.append({**story, "relevance": relevance, "combined": combined})

        scored.sort(key=lambda s: s["combined"], reverse=True)
        return scored[:n]

    def _relevance_score(self, title: str) -> float:
        """Return a 0–1 relevance score based on topic keyword matches."""
        title_lower = title.lower()
        hits = sum(1 for topic in RELEVANCE_TOPICS if topic in title_lower)
        return min(hits / 3.0, 1.0)

    # ------------------------------------------------------------------
    # Article content fetching
    # ------------------------------------------------------------------

    def _fetch_content(self, story: dict) -> dict:
        """
        Fetch the raw text content of a story's article URL.

        Returns raw cleaned text (up to CONTENT_MAX_CHARS) for the agent to
        summarise. Does not attempt to extract or truncate "good" paragraphs —
        that heuristic was too brittle. The agent (Claude) reads the raw content
        and writes the actual summary.
        """
        url = story["url"]
        title = story["title"]
        score = story["score"]
        relevance = story.get("relevance", 0.0)
        domain = story.get("domain")

        logger.info("HN Digest: fetching content for '%s'", title)

        base = {
            "title": title,
            "url": url,
            "score": score,
            "relevance": relevance,
        }

        # Don't try to fetch HN discussion pages
        if not domain or "news.ycombinator.com" in url:
            return {**base, "content": None, "fetch_failed": True,
                    "fetch_error": "No external article URL — HN discussion only"}

        result = self.fetch.fetch_url(url=url, max_length=CONTENT_MAX_CHARS)
        if not result.get("success"):
            return {**base, "content": None, "fetch_failed": True,
                    "fetch_error": result.get("error", "unknown error")}

        return {**base, "content": result.get("content", ""), "fetch_failed": False,
                "fetch_error": None}
