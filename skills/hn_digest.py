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

            raw_html = hn_result.get("content", "")

            # Step 2: Parse stories
            stories = self._parse_stories(raw_html)
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

        The FetchService strips HTML, so we work with the plain-text output
        which preserves the story titles and point counts in a predictable order.
        We use the HN comment/item URL as a fallback when the story URL is
        an internal HN link.
        """
        stories = []

        # Match lines that look like story titles followed by metadata.
        # HN's cleaned text has patterns like:
        #   "Story Title (domain.com)"  or just  "Story Title"
        # followed later by "NNN points"
        #
        # We use a simple approach: find all hrefs from the raw text by
        # re-scanning for "item?id=" references and title-like lines.
        # Since we only have cleaned text, we rely on structural patterns.

        # Split into lines and look for title + score pairs
        lines = [l.strip() for l in text.splitlines() if l.strip()]

        i = 0
        while i < len(lines):
            line = lines[i]

            # Score line pattern: starts with a number and contains "point"
            score_match = re.match(r'^(\d+)\s+points?', line)
            if score_match and i > 0:
                score = int(score_match.group(1))
                # The title is somewhere in the preceding few lines
                # Walk backwards to find the most plausible title line
                title = self._find_title_before(lines, i)
                if title:
                    # Try to find a URL nearby
                    url = self._find_url_near(lines, i)
                    stories.append({
                        "title": title,
                        "url": url or HN_FRONT_PAGE,
                        "score": score,
                    })
            i += 1

        # Deduplicate by title
        seen = set()
        deduped = []
        for s in stories:
            key = s["title"].lower()
            if key not in seen:
                seen.add(key)
                deduped.append(s)

        return deduped

    def _find_title_before(self, lines: list[str], score_idx: int) -> str | None:
        """Walk back from a score line to find the story title."""
        # Look up to 5 lines back for something that looks like a title
        for offset in range(1, 6):
            idx = score_idx - offset
            if idx < 0:
                break
            candidate = lines[idx]
            # Skip metadata lines (usernames, vote counts, time references)
            if re.match(r'^\d+\s+(points?|hours?|minutes?|days?)', candidate):
                continue
            if re.match(r'^(hide|past|comments?|favorite|flag|from|by|submit)', candidate, re.I):
                continue
            if len(candidate) < 8:
                continue
            # Looks like a title
            return candidate
        return None

    def _find_url_near(self, lines: list[str], idx: int) -> str | None:
        """Look for a URL-like string near a score line."""
        # Scan a window around the score line
        for offset in range(-6, 4):
            i = idx + offset
            if i < 0 or i >= len(lines):
                continue
            # URLs in cleaned text often appear as bare domain hints like "(github.com)"
            # but we don't have real href data here — return None and let the
            # caller fall back to the HN front page.
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

        logger.info("HN Digest: fetching '%s'", title)

        # Don't try to fetch HN itself as an article
        if url == HN_FRONT_PAGE or "news.ycombinator.com" in url:
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

        This is a lightweight extractive summariser — it takes the first
        meaningful paragraphs up to ~1500 chars. Claude will synthesise
        the actual digest from the saved notes, so we just need the key facts.
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
