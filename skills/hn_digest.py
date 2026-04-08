"""
HN Digest Skill

Fetches the Hacker News front page, filters stories for relevance to Hugh's
work (AI, agents, software engineering, startups, developer tooling), fetches
the full content of the most relevant ones, summarises each, and saves the
results to the workspace under research/hn-YYYY-MM-DD/.

Returns a markdown index string suitable for sending directly to the user.
"""

import logging
import re
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

HN_FRONT_PAGE = "https://news.ycombinator.com"

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

            # Step 1: Fetch HN front page
            logger.info("HN Digest: fetching front page")
            hn_result = self.fetch.fetch_url(url=HN_FRONT_PAGE)
            if not hn_result.get("success"):
                return {"success": False, "error": f"Could not fetch HN: {hn_result.get('error')}"}

            raw_text = hn_result.get("content", "")

            # Step 2: Parse stories
            stories = self._parse_stories(raw_text)
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
    # Parsing
    # ------------------------------------------------------------------

    def _parse_stories(self, text: str) -> list[dict]:
        """
        Extract story titles, URLs, and scores from the cleaned HN page text.

        FetchService returns the HN front page as a single continuous string.
        The structure is a numbered list:
          "1. Story Title ( domain.com ) NNN points by user X hours ago | ..."
          "2. Next Story ..."

        We split on the numbered story markers and extract title + score from
        each segment.
        """
        stories = []

        # Split on numbered story entries: "1. ", "2. ", etc.
        # We look for a digit sequence followed by ". " at a word boundary.
        segments = re.split(r'(?<!\d)(\d{1,2})\.\s+', text)

        # re.split with a capturing group gives us: [pre, num, content, num, content, ...]
        # Walk in pairs: (number, content)
        i = 1
        while i + 1 < len(segments):
            _num = segments[i]
            content = segments[i + 1]
            i += 2

            # Extract title — everything up to the first " (" domain marker or
            # up to "NNN points", whichever comes first.
            title_match = re.match(r'^(.+?)(?:\s*\([^)]*\))?\s+(\d+)\s+points?', content)
            if not title_match:
                # Try without domain — just title then points
                title_match = re.match(r'^(.+?)\s+(\d+)\s+points?', content)
            if not title_match:
                continue

            title = title_match.group(1).strip()
            score = int(title_match.group(2))

            # Skip obvious non-stories (too short, navigation text)
            if len(title) < 8:
                continue
            if re.match(r'^(hide|past|comments?|flag|from|by|submit|login|more)', title, re.I):
                continue

            # Extract domain hint from parentheses e.g. "( github.com )"
            domain_match = re.search(r'\(\s*([\w.-]+\.\w+)\s*\)', content[:200])
            domain = domain_match.group(1) if domain_match else None

            stories.append({
                "title": title,
                "url": f"https://{domain}" if domain else HN_FRONT_PAGE,
                "domain": domain,
                "score": score,
            })

        return stories

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
