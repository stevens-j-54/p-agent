"""
HN Digest Skill

Fetches the Hacker News front page via the official HN Firebase API, filters
stories for relevance to Hugh's work (AI, agents, software engineering,
startups, developer tooling), fetches the full content of the most relevant
ones, summarises each, and saves the results to the workspace under
research/hn-YYYY-MM-DD/.

Returns a markdown index string suitable for sending directly to the user.

HN API:
  Top story IDs:  https://hacker-news.firebaseio.com/v0/topstories.json
  Story detail:   https://hacker-news.firebaseio.com/v0/item/{id}.json
"""

import json
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

HN_TOP_STORIES_URL = "https://hacker-news.firebaseio.com/v0/topstories.json"
HN_ITEM_URL = "https://hacker-news.firebaseio.com/v0/item/{id}.json"

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

# How many top story IDs to consider from HN (the API returns ~500).
CANDIDATE_POOL = 30

# Number of stories to fetch and summarise after filtering.
TOP_N = 6


class HNDigestSkill:
    """
    Orchestrates the full HN digest pipeline.

    Depends on:
      - fetch_service: FetchService — for HTTP fetching
      - workspace_fn: callable(repo_name) -> Workspace — for saving output
    """

    def __init__(self, fetch_service, workspace_fn):
        self.fetch = fetch_service
        self.get_workspace = workspace_fn

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def run(self) -> dict:
        """
        Execute the full digest pipeline.

        Returns a dict with:
          - success: bool
          - index: str  (markdown index, ready to send to the user)
          - saved_to: str  (workspace path for the output folder)
          - error: str  (only present on failure)
        """
        try:
            date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            output_folder = f"research/hn-{date_str}"

            # Step 1: Fetch top story IDs from HN API
            logger.info("HN Digest: fetching top story IDs")
            ids = self._fetch_top_story_ids()
            if not ids:
                return {"success": False, "error": "Could not fetch HN top story IDs"}

            # Step 2: Fetch story metadata for the candidate pool
            logger.info("HN Digest: fetching metadata for %d candidates", CANDIDATE_POOL)
            stories = []
            for story_id in ids[:CANDIDATE_POOL]:
                story = self._fetch_story_metadata(story_id)
                if story:
                    stories.append(story)

            if not stories:
                return {"success": False, "error": "No story metadata retrieved from HN API"}

            logger.info("HN Digest: retrieved metadata for %d stories", len(stories))

            # Step 3: Score and shortlist
            shortlisted = self._shortlist(stories, TOP_N)
            logger.info("HN Digest: shortlisted %d stories", len(shortlisted))

            # Step 4: Fetch and summarise each
            digests = []
            for story in shortlisted:
                digest = self._fetch_and_summarise(story)
                digests.append(digest)

            # Step 5: Save to workspace
            saved_to = self._save_to_workspace(output_folder, date_str, digests)

            # Step 6: Build index for the user
            index = self._build_index(date_str, digests)

            return {
                "success": True,
                "index": index,
                "saved_to": saved_to,
            }

        except Exception as e:
            logger.error("HN Digest skill failed: %s", e, exc_info=True)
            return {"success": False, "error": str(e)}

    # ------------------------------------------------------------------
    # HN API fetching
    # ------------------------------------------------------------------

    def _fetch_top_story_ids(self) -> list[int]:
        """Fetch the list of top story IDs from the HN Firebase API."""
        result = self.fetch.fetch_url(url=HN_TOP_STORIES_URL)
        if not result.get("success"):
            logger.error("Failed to fetch HN top stories: %s", result.get("error"))
            return []
        try:
            ids = json.loads(result["content"])
            return ids if isinstance(ids, list) else []
        except (json.JSONDecodeError, KeyError) as e:
            logger.error("Failed to parse HN top story IDs: %s", e)
            return []

    def _fetch_story_metadata(self, story_id: int) -> dict | None:
        """Fetch metadata for a single HN story by ID."""
        url = HN_ITEM_URL.format(id=story_id)
        result = self.fetch.fetch_url(url=url)
        if not result.get("success"):
            return None
        try:
            item = json.loads(result["content"])
            # Skip non-story types (jobs, polls, comments) and deleted items
            if item.get("type") != "story" or item.get("deleted") or item.get("dead"):
                return None
            # Skip Ask HN / Show HN with no external URL — still include them
            # but mark them so we don't attempt to fetch the content later.
            return {
                "id": item.get("id"),
                "title": item.get("title", ""),
                "url": item.get("url"),  # None for Ask HN etc.
                "score": item.get("score", 0),
                "by": item.get("by", ""),
                "hn_url": f"https://news.ycombinator.com/item?id={item.get('id')}",
            }
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning("Failed to parse story %s: %s", story_id, e)
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
    # Fetch + summarise
    # ------------------------------------------------------------------

    def _fetch_and_summarise(self, story: dict) -> dict:
        """Fetch a story URL and produce a tight summary."""
        title = story["title"]
        score = story["score"]
        url = story.get("url")
        hn_url = story["hn_url"]

        logger.info("HN Digest: fetching '%s'", title)

        # Ask HN, Show HN, or other stories without an external URL
        if not url:
            return {
                "title": title,
                "url": hn_url,
                "score": score,
                "summary": "No external URL — discussion is on HN itself.",
                "fetch_failed": False,
            }

        result = self.fetch.fetch_url(url=url)
        if not result.get("success"):
            return {
                "title": title,
                "url": url,
                "hn_url": hn_url,
                "score": score,
                "summary": f"Could not fetch article ({result.get('error', 'unknown error')}).",
                "fetch_failed": True,
            }

        content = result.get("content", "")
        summary = self._summarise(content)

        return {
            "title": title,
            "url": url,
            "hn_url": hn_url,
            "score": score,
            "summary": summary,
            "fetch_failed": False,
        }

    def _summarise(self, content: str) -> str:
        """
        Produce a tight summary from article content.

        Takes the first meaningful paragraphs up to ~1500 chars.
        """
        lines = [l.strip() for l in content.splitlines() if len(l.strip()) > 60]
        body = " ".join(lines)

        excerpt = body[:1500].strip()
        if len(body) > 1500:
            last_period = excerpt.rfind(". ")
            if last_period > 500:
                excerpt = excerpt[: last_period + 1]

        return excerpt if excerpt else "No readable content extracted."

    # ------------------------------------------------------------------
    # Output
    # ------------------------------------------------------------------

    def _save_to_workspace(self, folder: str, date_str: str, digests: list[dict]) -> str:
        """Save individual story notes and a sources index to the workspace."""
        ws = self.get_workspace("workspace")

        # sources.md — list of all fetched stories with URLs and scores
        sources_lines = [f"# HN Sources — {date_str}\n"]
        for d in digests:
            sources_lines.append(f"## {d['title']}")
            sources_lines.append(f"- **URL**: {d['url']}")
            if d.get("hn_url"):
                sources_lines.append(f"- **HN discussion**: {d['hn_url']}")
            sources_lines.append(f"- **Score**: {d['score']} points")
            sources_lines.append(f"- **Fetch failed**: {d.get('fetch_failed', False)}")
            sources_lines.append("")

        ws.save_document(
            file_path=f"{folder}/sources.md",
            content="\n".join(sources_lines),
        )

        # notes.md — summaries for each story
        notes_lines = [f"# HN Notes — {date_str}\n"]
        for d in digests:
            notes_lines.append(f"## {d['title']}")
            notes_lines.append(f"**URL**: {d['url']}  ")
            if d.get("hn_url"):
                notes_lines.append(f"**HN**: {d['hn_url']}  ")
            notes_lines.append(f"**Score**: {d['score']} points\n")
            notes_lines.append(d["summary"])
            notes_lines.append("\n---\n")

        ws.save_document(
            file_path=f"{folder}/notes.md",
            content="\n".join(notes_lines),
        )

        ws.commit_and_push(commit_message=f"HN digest — {date_str}")

        return folder

    def _build_index(self, date_str: str, digests: list[dict]) -> str:
        """Build a compact markdown index to send back to the user."""
        lines = [f"**HN Digest — {date_str}**\n"]
        for i, d in enumerate(digests, 1):
            fetch_note = " *(fetch failed)*" if d.get("fetch_failed") else ""
            lines.append(f"**{i}. {d['title']}**{fetch_note}")
            lines.append(f"↑ {d['score']} pts · {d['url']}")
            summary = d["summary"]
            first_sentence = summary.split(". ")[0]
            if len(first_sentence) > 20:
                lines.append(f"_{first_sentence}_")
            lines.append("")

        lines.append(f"Full notes saved to `research/hn-{date_str}/` in workspace.")
        return "\n".join(lines)
