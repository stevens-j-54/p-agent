"""
Vietnamese Vocab Skill

Two efficient methods for Vietnamese study sessions:
  - prepare_chat(): loads vocab due for review — agent picks its own topic
  - save_session(): saves session record + updates vocab list atomically

This keeps Claude tool calls per study session to a minimum (2 total).
"""

import json
import logging
import uuid
from datetime import date, datetime, timezone

logger = logging.getLogger(__name__)

# Max review words to surface per session
MAX_REVIEW_WORDS = 3


class VietnameseVocabSkill:
    """
    Manages the Vietnamese vocab list and study session records.

    Depends on:
      - agent_core: AgentCore — for reading/writing vocab and session files
    """

    def __init__(self, agent_core):
        self.agent_core = agent_core

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def prepare_chat(self) -> dict:
        """
        Load vocab entries due for spaced-repetition review.

        The agent uses the returned words to choose a topic where they arise
        naturally — not the other way round.

        Returns
        -------
        dict with:
          - success: bool
          - vocab: dict
              - total_entries: int
              - due_for_review: list[dict]  (up to MAX_REVIEW_WORDS entries)
        """
        try:
            vocab_data = self._load_vocab()
            due = self._select_due_words(vocab_data.get("entries", []))

            return {
                "success": True,
                "vocab": {
                    "total_entries": len(vocab_data.get("entries", [])),
                    "due_for_review": due,
                },
            }
        except Exception as e:
            logger.error("prepare_chat failed: %s", e, exc_info=True)
            return {"success": False, "error": str(e)}

    def save_session(
        self,
        session_record: dict,
        words_practiced: list,
        new_entries: list,
    ) -> dict:
        """
        Atomically save a study session record and update the vocab list.

        Replaces two separate calls (create_agent_core + update_agent_core).

        Parameters
        ----------
        session_record : dict
            Full session JSON following the exercise/conversation schema.
            Must include at least: date, mode, topic.
        words_practiced : list[str]
            Vietnamese words (strings) that were reviewed. practice_count will
            be incremented and last_practiced set to today for each.
        new_entries : list[dict]
            New vocab entries to add. Each must follow the vocab entry schema
            (vietnamese, english, word_type, sample_sentences, etc.).
            Duplicates (same vietnamese + same meaning) are silently skipped.

        Returns
        -------
        dict with:
          - success: bool
          - session_path: str
          - vocab_entries_updated: int
          - vocab_entries_added: int
        """
        try:
            session_path = self._save_session_record(session_record)
            updated, added = self._update_vocab(words_practiced, new_entries)

            return {
                "success": True,
                "session_path": session_path,
                "vocab_entries_updated": updated,
                "vocab_entries_added": added,
            }
        except Exception as e:
            logger.error("save_session failed: %s", e, exc_info=True)
            return {"success": False, "error": str(e)}

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _load_vocab(self) -> dict:
        result = self.agent_core.read_file("vietnamese_vocab.json")
        if not result.get("success") or not result.get("content"):
            return {"version": 2, "last_updated": "", "entries": []}
        try:
            return json.loads(result["content"])
        except (json.JSONDecodeError, KeyError):
            return {"version": 2, "last_updated": "", "entries": []}

    def _select_due_words(self, entries: list) -> list:
        """Return up to MAX_REVIEW_WORDS entries due for spaced-repetition review."""
        today = date.today()
        due = []
        not_due = []

        for entry in entries:
            lp = entry.get("last_practiced")
            pc = entry.get("practice_count", 0)

            if lp is None:
                due.append((None, entry))
            else:
                try:
                    lp_date = date.fromisoformat(lp)
                    days_since = (today - lp_date).days
                    interval = max(3, pc * 2)
                    if days_since >= interval:
                        due.append((lp_date, entry))
                    else:
                        not_due.append(entry)
                except ValueError:
                    due.append((None, entry))

        # Sort: null last_practiced first, then oldest last_practiced
        due.sort(key=lambda x: (x[0] is not None, x[0] or date.min))
        selected = [entry for _, entry in due[:MAX_REVIEW_WORDS]]
        return selected

    def _save_session_record(self, session_record: dict) -> str:
        if "id" not in session_record:
            session_record["id"] = str(uuid.uuid4())
        if "date" not in session_record:
            session_record["date"] = date.today().isoformat()

        now = datetime.now(timezone.utc)
        file_path = f"exercises/{now.strftime('%Y-%m-%dT%H%M')}.json"

        content = json.dumps(session_record, ensure_ascii=False, indent=2)
        result = self.agent_core.upsert_file(
            file_path=file_path,
            content=content,
            commit_message=f"Add study session: {session_record.get('topic', 'unknown')} ({session_record.get('mode', 'exercise')})",
        )
        if not result.get("success"):
            raise RuntimeError(f"Failed to save session record: {result.get('error')}")
        return file_path

    def _update_vocab(self, words_practiced: list, new_entries: list) -> tuple[int, int]:
        vocab_data = self._load_vocab()
        entries = vocab_data.get("entries", [])

        # Build lookup by Vietnamese word for efficient updates
        by_word: dict[str, list[dict]] = {}
        for entry in entries:
            word = entry.get("vietnamese", "")
            by_word.setdefault(word, []).append(entry)

        today = date.today().isoformat()
        updated = 0

        for word in words_practiced:
            if not isinstance(word, str):
                continue
            for entry in by_word.get(word, []):
                entry["practice_count"] = entry.get("practice_count", 0) + 1
                entry["last_practiced"] = today
                updated += 1

        added = 0
        for new_entry in new_entries:
            if not isinstance(new_entry, dict):
                continue
            viet = new_entry.get("vietnamese", "")
            eng = new_entry.get("english", "")
            existing = by_word.get(viet, [])
            # Deduplicate by Vietnamese word + same broad meaning (English)
            duplicate = any(
                e.get("english", "").lower() == eng.lower()
                for e in existing
            )
            if duplicate:
                continue

            if "id" not in new_entry:
                new_entry["id"] = str(uuid.uuid4())
            if "date_added" not in new_entry:
                new_entry["date_added"] = today
            new_entry.setdefault("last_practiced", None)
            new_entry.setdefault("practice_count", 0)
            new_entry.setdefault("meaning_index", len(existing) + 1)

            entries.append(new_entry)
            by_word.setdefault(viet, []).append(new_entry)
            added += 1

        vocab_data["entries"] = entries
        vocab_data["last_updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        content = json.dumps(vocab_data, ensure_ascii=False, indent=2)
        result = self.agent_core.upsert_file(
            file_path="vietnamese_vocab.json",
            content=content,
            commit_message=f"Update vocab: {updated} practiced, {added} added",
        )
        if not result.get("success"):
            raise RuntimeError(f"Failed to update vocab: {result.get('error')}")

        return updated, added
