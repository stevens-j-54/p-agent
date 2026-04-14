"""
Vietnamese Study Skill

Fetches recent article listings from Vietnamese news sites (VNExpress, Tuổi Trẻ,
Thanh Niên) for topic/theme inspiration. Claude then writes its own Vietnamese
paragraph at the right B1→B2 level, incorporating review vocabulary as needed.

Fetching is best-effort: individual page failures don't abort the call.
Even partial/sparse content is useful — a few article titles are enough
for Claude to know "there's travel news about Đà Lạt" or "there's a food
festival happening in Hội An".
"""

import logging

logger = logging.getLogger(__name__)

# Section pages grouped by topic.  We try each source in order and use
# the first successful fetch; remaining sources serve as fallbacks.
SOURCES: dict[str, list[tuple[str, str]]] = {
    "current_affairs": [
        ("VNExpress", "https://vnexpress.net/the-gioi"),
        ("VNExpress (xã hội)", "https://vnexpress.net/xa-hoi"),
        ("Tuổi Trẻ", "https://tuoitre.vn/tin-tuc.htm"),
        ("Thanh Niên", "https://thanhnien.vn/thoi-su.htm"),
    ],
    "nature": [
        ("VNExpress", "https://vnexpress.net/khoa-hoc"),
        ("VNExpress (môi trường)", "https://vnexpress.net/moi-truong"),
        ("Tuổi Trẻ", "https://tuoitre.vn/khoa-hoc.htm"),
    ],
    "food": [
        ("VNExpress", "https://vnexpress.net/am-thuc"),
        ("Tuổi Trẻ", "https://tuoitre.vn/am-thuc.htm"),
        ("Thanh Niên", "https://thanhnien.vn/am-thuc.htm"),
    ],
    "travel": [
        ("VNExpress", "https://vnexpress.net/du-lich"),
        ("Tuổi Trẻ", "https://tuoitre.vn/du-lich.htm"),
        ("Thanh Niên", "https://thanhnien.vn/du-lich.htm"),
    ],
}

# Fallback when no topic is given — sample across all sections
ALL_SOURCES: list[tuple[str, str]] = [
    ("VNExpress", "https://vnexpress.net/"),
    ("Tuổi Trẻ", "https://tuoitre.vn/"),
    ("Thanh Niên", "https://thanhnien.vn/"),
]

# Page content cap — enough to surface 10–20 headlines for topic inspiration.
SECTION_MAX_CHARS = 8_000

# Number of source pages to target per call (we fetch until we hit this
# many successes, or exhaust all sources).
TARGET_SUCCESSFUL_PAGES = 2


class VietnameseStudySkill:
    """
    Fetches Vietnamese news section pages for topic/theme inspiration.

    Returns raw page text (best-effort) plus metadata. Individual page
    failures are recorded but never cause the overall call to fail.

    Depends on:
      - fetch_service: FetchService — for HTTP fetching
    """

    def __init__(self, fetch_service):
        self.fetch = fetch_service

    def run(self, topic: str = None) -> dict:
        """
        Fetch inspiration pages from Vietnamese news sites.

        Parameters
        ----------
        topic : str, optional
            One of "current_affairs", "nature", "food", "travel".
            If None or unrecognised, samples from all site homepages.

        Returns
        -------
        dict with:
          - success: bool  (always True — partial results are fine)
          - topic: str
          - pages_fetched: int  (successful page fetches)
          - pages_failed: int   (failed page fetches)
          - pages: list[dict]   (one entry per attempted source)

        Each page dict:
          - source_site: str
          - section_url: str
          - content: str | None   (plain text, up to SECTION_MAX_CHARS)
          - fetch_failed: bool
          - fetch_error: str | None
        """
        try:
            sources = SOURCES.get(topic) if topic else None
            if not sources:
                sources = ALL_SOURCES

            pages = []
            successes = 0

            for site_name, url in sources:
                page = self._fetch_page(site_name, url)
                pages.append(page)
                if not page["fetch_failed"]:
                    successes += 1
                    if successes >= TARGET_SUCCESSFUL_PAGES:
                        break

            # If everything failed, try the fallback homepages
            if successes == 0 and sources is not ALL_SOURCES:
                logger.warning(
                    "All topic sources failed for '%s' — trying fallback homepages", topic
                )
                for site_name, url in ALL_SOURCES:
                    page = self._fetch_page(site_name, url)
                    pages.append(page)
                    if not page["fetch_failed"]:
                        successes += 1
                        if successes >= TARGET_SUCCESSFUL_PAGES:
                            break

            failed = sum(1 for p in pages if p["fetch_failed"])

            return {
                "success": True,
                "topic": topic or "all",
                "pages_fetched": successes,
                "pages_failed": failed,
                "pages": pages,
            }

        except Exception as e:
            logger.error("VietnameseStudySkill failed: %s", e, exc_info=True)
            return {"success": False, "error": str(e)}

    def _fetch_page(self, site_name: str, url: str) -> dict:
        """Fetch a single section page and return its plain-text content."""
        logger.info("Vietnamese study: fetching %s (%s)", site_name, url)

        base = {
            "source_site": site_name,
            "section_url": url,
        }

        result = self.fetch.fetch_url(url=url, max_length=SECTION_MAX_CHARS)
        if not result.get("success"):
            logger.warning(
                "Vietnamese study: failed to fetch %s: %s",
                url, result.get("error")
            )
            return {
                **base,
                "content": None,
                "fetch_failed": True,
                "fetch_error": result.get("error", "unknown error"),
            }

        return {
            **base,
            "content": result.get("content", ""),
            "fetch_failed": False,
            "fetch_error": None,
        }
