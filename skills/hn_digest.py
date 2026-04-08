"""
HN Digest Skill

Fetches the Hacker News front page, filters stories for relevance to Hugh's
work (AI, agents, software engineering, startups, developer tooling), fetches
the full content of the most relevant ones, summarises each, and saves the
results to the workspace under research/hn-YYYY-MM-DD/.

Returns a markdown index string suitable for sending directly to the user.
"""

import json
import logging
from datetime import datetime, timezone
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

HN_FRONT_PAGE = "https://news.ycombinator.com"
HN_API_TOP = "https://hacker-news.firebaseio.com/v0/topstories.json"
HN_API_ITEM = "https://hacker-news.firebaseio.com/v0/item/{}.json"

# How many top story IDs to fetch from the API before shortlisting
HN_FETCH_LIMIT = 30

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

# Number of top stories to fetch and summarise.
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

            # Step 1 & 2: Fetch stories with real URLs from the HN API
            stories = self._fetch_stories()
            if not stories:
                return {"success": False, "error": "No stories found on HN front page"}

            logger.info("HN Digest: found %d stories", len(stories))

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
    # Story fetching via HN Firebase API
    # ------------------------------------------------------------------

    def _fetch_stories(self) -> list[dict]:
        """
        Fetch the top HN stories with their real article URLs via the Firebase API.

        Uses:
          GET https://hacker-news.firebaseio.com/v0/topstories.json
            → [id, id, ...]
          GET https://hacker-news.firebaseio.com/v0/item/{id}.json
            → {"id": …, "title": …, "url": …, "score": …, "type": …}

        The old approach of scraping the front page only recovered the domain
        (e.g. "github.com") from parenthetical text, then constructed a bare
        homepage URL like "https://github.com" — discarding the actual article
        path entirely.
        """
        logger.info("HN Digest: fetching top story IDs from API")
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
            item_url = HN_API_ITEM.format(story_id)
            item_result = self.fetch.fetch_url(url=item_url)
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

            # External stories have a "url" field; Ask/Show HN posts do not.
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
    # Fetch + summarise
    # ------------------------------------------------------------------

    def _fetch_and_summarise(self, story: dict) -> dict:
        """Fetch a story URL and produce a tight summary."""
        url = story["url"]
        title = story["title"]
        score = story["score"]
        domain = story.get("domain")

        logger.info("HN Digest: fetching '%s'", title)

        # Don't try to fetch bare HN or domainless stories
        if not domain or url == HN_FRONT_PAGE or "news.ycombinator.com" in url:
            return {
                "title": title,
                "url": url,
                "score": score,
                "summary": "No external URL available — see HN for discussion.",
                "fetch_failed": True,
            }

        result = self.fetch.fetch_url(url=url)
        if not result.get("success"):
            return {
                "title": title,
                "url": url,
                "score": score,
                "summary": f"Could not fetch article ({result.get('error', 'unknown error')}).",
                "fetch_failed": True,
            }

        content = result.get("content", "")
        summary = self._summarise(content, title)

        return {
            "title": title,
            "url": url,
            "score": score,
            "summary": summary,
            "fetch_failed": False,
        }

    def _summarise(self, content: str, title: str) -> str:
        """
        Produce a tight summary from article content.

        Takes the first meaningful paragraphs up to ~1500 chars.
        """
        # Strip very short lines (navigation, headers, etc.)
        lines = [l.strip() for l in content.splitlines() if len(l.strip()) > 60]
        body = " ".join(lines)

        # Take first 1500 characters of meaningful content
        excerpt = body[:1500].strip()
        if len(body) > 1500:
            # Cut at last sentence boundary
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
            # One-sentence teaser from the summary
            summary = d["summary"]
            first_sentence = summary.split(". ")[0]
            if len(first_sentence) > 20:
                lines.append(f"_{first_sentence}_")
            lines.append("")

        lines.append(f"Full notes saved to `research/hn-{date_str}/` in workspace.")
        return "\n".join(lines)
