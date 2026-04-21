"""
VietnameseDashboardSkill — generates a static HTML Vietnamese vocab progress page
and pushes it to the existing GitHub Pages repo.

Page: https://stevens-j-54.github.io/vietnamese/
Updated after every save_vietnamese_session call and nightly by a scheduled task.
No Claude API calls — pure Python template engine.
"""

import html as html_lib
import json
import logging
from datetime import date, timedelta
from pathlib import Path

from config import AGENT_CORE_DIR, GITHUB_USERNAME

logger = logging.getLogger(__name__)

_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
           "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

# CSS defined as a plain string to avoid f-string brace-escaping in CSS rules.
_CSS = """
:root {
  --bg:       #1A0808;
  --surface:  #2A1010;
  --surface2: #3A1818;
  --border:   #5A2020;
  --text:     #F5E6C8;
  --muted:    #C4A882;
  --accent:   #C0392B;
  --gold:     #F39C12;
  --jade:     #2E8B57;
  --heat-0:   #2A1010;
  --heat-1:   #7A2020;
  --heat-2:   #A02828;
  --heat-3:   #C0392B;
  --heat-4:   #E05030;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  background: var(--bg);
  color: var(--text);
  font-family: 'Be Vietnam Pro', sans-serif;
  font-size: 15px;
  line-height: 1.6;
  min-height: 100vh;
}
a { color: var(--gold); text-decoration: none; }

header {
  padding: 2rem 2rem 1.5rem;
  border-bottom: 1px solid var(--border);
  display: flex;
  align-items: center;
  gap: 1.2rem;
}
.header-text h1 {
  font-size: 1.8rem;
  font-weight: 700;
  color: var(--text);
  letter-spacing: 0.02em;
}
.header-text p { color: var(--muted); font-size: 0.9rem; margin-top: 0.15rem; }
.lotus-svg { flex-shrink: 0; }

main { max-width: 860px; margin: 0 auto; padding: 2rem; }

.divider { margin: 2rem 0; opacity: 0.35; }

.stats-strip {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 1rem;
  margin-bottom: 0.5rem;
}
.stat-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 1rem 1.2rem;
}
.stat-value { font-size: 1.8rem; font-weight: 700; color: var(--gold); line-height: 1.1; }
.stat-label {
  font-size: 0.78rem;
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  margin-top: 0.3rem;
}

.section-title {
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  color: var(--gold);
  margin-bottom: 1rem;
}

.no-practice { color: var(--muted); font-style: italic; padding: 0.5rem 0; }

.session-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 1.1rem 1.3rem;
  margin-bottom: 0.8rem;
}
.session-header {
  display: flex;
  align-items: center;
  gap: 0.7rem;
  margin-bottom: 0.5rem;
  flex-wrap: wrap;
}
.badge {
  display: inline-block;
  padding: 0.18rem 0.6rem;
  border-radius: 4px;
  font-size: 0.72rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
.badge-quiz         { background: #1a3a5c; color: #6ab0f5; }
.badge-exercise     { background: #1a3a2a; color: #6ad4a0; }
.badge-conversation { background: #3a2a1a; color: #f5b86a; }
.badge-lookup       { background: #2a1a3a; color: #c08af5; }
.session-topic { color: var(--muted); font-size: 0.88rem; }
.score { margin-left: auto; font-size: 1rem; font-weight: 600; color: var(--jade); }

.vocab-section { margin-top: 0.8rem; }
.vocab-item { margin-bottom: 0.9rem; }
.vocab-tag {
  display: inline-block;
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 0.18rem 0.55rem;
  font-size: 0.85rem;
  font-weight: 500;
  margin-bottom: 0.3rem;
  color: var(--text);
}
.vocab-english { color: var(--muted); font-size: 0.8rem; }
.sample-vi { font-size: 0.88rem; color: var(--text); margin: 0.15rem 0 0 0.1rem; }
.sample-en { font-size: 0.8rem; color: var(--muted); font-style: italic; margin: 0 0 0 0.1rem; }

.heatmap-wrap { overflow-x: auto; padding-bottom: 0.5rem; }
.heatmap-months { display: flex; margin-bottom: 4px; padding-left: 1px; }
.hm-month { font-size: 0.7rem; color: var(--muted); width: 16px; text-align: left; flex-shrink: 0; }
.heatmap-grid {
  display: grid;
  grid-template-rows: repeat(7, 13px);
  grid-auto-flow: column;
  grid-auto-columns: 13px;
  gap: 3px;
}
.hm-cell { width: 13px; height: 13px; border-radius: 2px; background: var(--heat-0); }
.hm-cell.level-1 { background: var(--heat-1); }
.hm-cell.level-2 { background: var(--heat-2); }
.hm-cell.level-3 { background: var(--heat-3); }
.hm-cell.level-4 { background: var(--heat-4); }
.heatmap-legend {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-top: 0.6rem;
  font-size: 0.72rem;
  color: var(--muted);
}
.legend-cell { width: 11px; height: 11px; border-radius: 2px; }

.day-details {
  border: 1px solid var(--border);
  border-radius: 8px;
  margin-bottom: 0.6rem;
  background: var(--surface);
}
.day-summary {
  cursor: pointer;
  padding: 0.75rem 1rem;
  display: flex;
  align-items: center;
  gap: 1rem;
  list-style: none;
  user-select: none;
}
.day-summary::-webkit-details-marker { display: none; }
.day-summary::before {
  content: '›';
  color: var(--gold);
  font-size: 1rem;
  transition: transform 0.15s;
  display: inline-block;
  width: 0.8rem;
}
details[open] .day-summary::before { transform: rotate(90deg); }
.day-date { font-weight: 500; }
.day-meta { font-size: 0.82rem; color: var(--muted); margin-left: auto; }
.day-cards { padding: 0 0.8rem 0.8rem; }

footer {
  text-align: center;
  padding: 2rem;
  color: var(--muted);
  font-size: 0.78rem;
  border-top: 1px solid var(--border);
  margin-top: 3rem;
}

@media (max-width: 600px) {
  .stats-strip { grid-template-columns: repeat(2, 1fr); }
  main { padding: 1rem; }
}
"""


class VietnameseDashboardSkill:
    """
    Generates a Vietnamese vocab progress page and publishes it to GitHub Pages.
    Reads data directly from the local agent-core filesystem clone.
    Shares the DashboardSkill's GitRepo instance to avoid maintaining a second clone.
    """

    def __init__(self, dashboard_skill):
        # dashboard_skill: DashboardSkill — borrowed for its GitRepo instance only
        self._dashboard_skill = dashboard_skill
        self._vocab_path = Path(AGENT_CORE_DIR) / "vietnamese_vocab.json"
        self._exercises_dir = Path(AGENT_CORE_DIR) / "exercises"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self) -> dict:
        """Called by the scheduler (instruction_type='skill')."""
        return self.update()

    def update(self) -> dict:
        """Regenerate and push vietnamese/index.html to GitHub Pages."""
        try:
            vocab_data = self._load_vocab()
            sessions = self._load_sessions()
            page_html = self.generate_html(vocab_data, sessions)
            repo = self._dashboard_skill._get_repo()
            repo.write_file("vietnamese/index.html", page_html)
            result = repo.commit_and_push("Update Vietnamese vocab dashboard")
            if result.get("success"):
                url = f"https://{GITHUB_USERNAME}.github.io/vietnamese/"
                logger.info("Vietnamese dashboard updated: %s", url)
                return {"success": True, "url": url, "action": result.get("action")}
            return result
        except Exception as e:
            logger.error("Vietnamese dashboard update failed: %s", e, exc_info=True)
            return {"success": False, "error": str(e)}

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def _load_vocab(self) -> dict:
        try:
            if self._vocab_path.exists():
                with open(self._vocab_path, encoding="utf-8") as f:
                    return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
        return {"version": 2, "entries": []}

    def _load_sessions(self) -> list:
        sessions = []
        if not self._exercises_dir.exists():
            return sessions
        for path in sorted(self._exercises_dir.glob("*.json")):
            try:
                with open(path, encoding="utf-8") as f:
                    sessions.append(json.load(f))
            except (json.JSONDecodeError, OSError):
                pass
        return sessions

    # ------------------------------------------------------------------
    # Data helpers
    # ------------------------------------------------------------------

    def _sessions_by_date(self, sessions: list) -> dict:
        by_date: dict = {}
        for s in sessions:
            raw = s.get("date", "")
            if not raw:
                continue
            try:
                day = str(raw)[:10]
                date.fromisoformat(day)
                by_date.setdefault(day, []).append(s)
            except ValueError:
                pass
        return by_date

    def _compute_streak(self, sessions_by_date: dict) -> int:
        today = date.today()
        check = today if today.isoformat() in sessions_by_date else today - timedelta(days=1)
        streak = 0
        while check.isoformat() in sessions_by_date:
            streak += 1
            check -= timedelta(days=1)
        return streak

    def _heatmap_data(self, sessions_by_date: dict) -> list:
        today = date.today()
        result = []
        for i in range(111, -1, -1):
            d = today - timedelta(days=i)
            key = d.isoformat()
            day_sessions = sessions_by_date.get(key, [])
            word_count = sum(len(s.get("vocab_reviewed", [])) for s in day_sessions)
            if word_count == 0:
                level = 0
            elif word_count < 5:
                level = 1
            elif word_count < 10:
                level = 2
            elif word_count < 20:
                level = 3
            else:
                level = 4
            result.append({"date": key, "count": word_count, "level": level})
        return result

    def _compute_stats(self, vocab_data: dict, sessions: list, sessions_by_date: dict) -> dict:
        today = date.today()
        week_ago = (today - timedelta(days=7)).isoformat()
        sessions_this_week = sum(1 for s in sessions if str(s.get("date", ""))[:10] >= week_ago)
        return {
            "total_words": len(vocab_data.get("entries", [])),
            "sessions_this_week": sessions_this_week,
            "streak": self._compute_streak(sessions_by_date),
            "total_sessions": len(sessions),
        }

    # ------------------------------------------------------------------
    # HTML generation
    # ------------------------------------------------------------------

    def generate_html(self, vocab_data: dict, sessions: list) -> str:
        sessions_by_date = self._sessions_by_date(sessions)
        stats = self._compute_stats(vocab_data, sessions, sessions_by_date)
        heatmap = self._heatmap_data(sessions_by_date)

        vocab_map: dict = {}
        for entry in vocab_data.get("entries", []):
            w = entry.get("vietnamese", "")
            if w and w not in vocab_map:
                vocab_map[w] = entry

        today_str = date.today().isoformat()
        today_sessions = sessions_by_date.get(today_str, [])

        if today_sessions:
            today_body = "\n".join(
                self._render_session_card(s, vocab_map) for s in today_sessions
            )
        else:
            today_body = '<p class="no-practice">Không luyện tập hôm nay.</p>'

        history_days = sorted(
            [d for d in sessions_by_date if d != today_str],
            reverse=True,
        )[:30]

        history_body = ""
        for day in history_days:
            day_sessions = sessions_by_date[day]
            sc = len(day_sessions)
            wc = sum(len(s.get("vocab_reviewed", [])) for s in day_sessions)
            cards = "\n".join(self._render_session_card(s, vocab_map) for s in day_sessions)
            s_label = "sessions" if sc != 1 else "session"
            history_body += (
                f'<details class="day-details">'
                f'<summary class="day-summary">'
                f'<span class="day-date">{html_lib.escape(day)}</span>'
                f'<span class="day-meta">{sc} {s_label} · {wc} words</span>'
                f'</summary>'
                f'<div class="day-cards">{cards}</div>'
                f'</details>\n'
            )

        if not history_body:
            history_body = '<p class="no-practice">Chưa có lịch sử luyện tập.</p>'

        heatmap_cells = "".join(
            f'<div class="hm-cell level-{c["level"]}" title="{html_lib.escape(self._cell_tip(c))}"></div>\n'
            for c in heatmap
        )

        month_row = self._month_labels(heatmap)

        streak = stats["streak"]
        streak_label = f"{streak} ngày" if streak != 1 else "1 ngày"

        today_display = date.today().strftime("%d %B %Y")

        return (
            "<!DOCTYPE html>\n"
            '<html lang="vi">\n'
            "<head>\n"
            '<meta charset="UTF-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
            "<title>Học Tiếng Việt</title>\n"
            '<link rel="preconnect" href="https://fonts.googleapis.com">\n'
            '<link href="https://fonts.googleapis.com/css2?family=Be+Vietnam+Pro:ital,wght@0,300;0,400;0,500;0,600;0,700;1,400&display=swap" rel="stylesheet">\n'
            f"<style>{_CSS}</style>\n"
            "</head>\n"
            "<body>\n"
            "<header>\n"
            + _LOTUS_SVG
            + "\n"
            f'<div class="header-text"><h1>Học Tiếng Việt</h1>'
            f'<p>Vietnamese vocabulary progress · {html_lib.escape(today_display)}</p></div>\n'
            "</header>\n"
            "<main>\n"
            # Stats strip
            '<div class="stats-strip">\n'
            f'  <div class="stat-card"><div class="stat-value">{stats["total_words"]}</div><div class="stat-label">Tổng từ vựng</div></div>\n'
            f'  <div class="stat-card"><div class="stat-value">{stats["sessions_this_week"]}</div><div class="stat-label">Buổi học tuần này</div></div>\n'
            f'  <div class="stat-card"><div class="stat-value">{html_lib.escape(streak_label)}</div><div class="stat-label">Chuỗi liên tiếp</div></div>\n'
            f'  <div class="stat-card"><div class="stat-value">{stats["total_sessions"]}</div><div class="stat-label">Tổng buổi học</div></div>\n'
            "</div>\n"
            + _DIVIDER
            # Today
            + '<section>\n<p class="section-title">Hôm nay</p>\n'
            + today_body + "\n</section>\n"
            + _DIVIDER
            # Heatmap
            + '<section>\n<p class="section-title">16 tuần gần đây</p>\n'
            '<div class="heatmap-wrap">\n'
            f'<div class="heatmap-months">{month_row}</div>\n'
            f'<div class="heatmap-grid">\n{heatmap_cells}</div>\n'
            "</div>\n"
            '<div class="heatmap-legend">'
            '<span>Ít hơn</span>'
            '<div class="legend-cell" style="background:var(--heat-0)"></div>'
            '<div class="legend-cell" style="background:var(--heat-1)"></div>'
            '<div class="legend-cell" style="background:var(--heat-2)"></div>'
            '<div class="legend-cell" style="background:var(--heat-3)"></div>'
            '<div class="legend-cell" style="background:var(--heat-4)"></div>'
            '<span>Nhiều hơn</span>'
            "</div>\n"
            "</section>\n"
            + _DIVIDER
            # History
            + '<section>\n<p class="section-title">Lịch sử luyện tập</p>\n'
            + history_body
            + "</section>\n"
            "</main>\n"
            "<footer>\n"
            f'Cập nhật lần cuối: {html_lib.escape(today_str)} · '
            f'<a href="https://{GITHUB_USERNAME}.github.io">← Trang chủ</a>\n'
            "</footer>\n"
            "</body>\n</html>"
        )

    # ------------------------------------------------------------------
    # Rendering helpers
    # ------------------------------------------------------------------

    def _render_session_card(self, session: dict, vocab_map: dict) -> str:
        mode = session.get("mode", "")
        topic = html_lib.escape(session.get("topic", ""))

        badge_classes = {
            "quiz": "badge-quiz",
            "exercise": "badge-exercise",
            "conversation": "badge-conversation",
            "lookup": "badge-lookup",
        }
        badge_class = badge_classes.get(mode, "badge-exercise")
        badge_label = mode.capitalize() if mode else "Session"

        score_html = ""
        if mode == "quiz":
            correct = session.get("correct_count", 0)
            total = session.get("cards_presented", 0)
            if total:
                score_html = f'<span class="score">{correct}/{total}</span>'

        vocab_reviewed = session.get("vocab_reviewed", [])
        vocab_html = ""
        for word in vocab_reviewed:
            entry = vocab_map.get(word)
            tag = html_lib.escape(word)
            english_text = html_lib.escape(entry.get("english", "")) if entry else ""
            english_span = (
                f' <span class="vocab-english">— {english_text}</span>' if english_text else ""
            )

            sentence_html = ""
            if entry:
                sents = entry.get("sample_sentences", [])
                if sents:
                    vi = html_lib.escape(sents[0].get("vi", ""))
                    en = html_lib.escape(sents[0].get("en", ""))
                    if vi:
                        sentence_html = f'<p class="sample-vi">{vi}</p>'
                        if en:
                            sentence_html += f'<p class="sample-en">{en}</p>'

            vocab_html += (
                f'<div class="vocab-item">'
                f'<span class="vocab-tag">{tag}</span>{english_span}'
                f'{sentence_html}'
                f'</div>\n'
            )

        vocab_section = f'<div class="vocab-section">{vocab_html}</div>' if vocab_html else ""

        return (
            f'<div class="session-card">'
            f'<div class="session-header">'
            f'<span class="badge {badge_class}">{html_lib.escape(badge_label)}</span>'
            f'<span class="session-topic">{topic}</span>'
            f'{score_html}'
            f'</div>'
            f'{vocab_section}'
            f'</div>\n'
        )

    def _month_labels(self, heatmap: list) -> str:
        parts = []
        seen: set = set()
        for col in range(16):
            idx = col * 7
            label = ""
            if idx < len(heatmap):
                try:
                    d = date.fromisoformat(heatmap[idx]["date"])
                    key = (d.year, d.month)
                    if key not in seen:
                        seen.add(key)
                        label = _MONTHS[d.month - 1]
                except ValueError:
                    pass
            parts.append(f'<span class="hm-month">{html_lib.escape(label)}</span>')
        return "".join(parts)

    @staticmethod
    def _cell_tip(cell: dict) -> str:
        n = cell["count"]
        if n == 0:
            return f"{cell['date']}: no practice"
        return f"{cell['date']}: {n} word{'s' if n != 1 else ''}"


# ------------------------------------------------------------------
# Module-level HTML fragments (defined here to keep generate_html clean)
# ------------------------------------------------------------------

_LOTUS_SVG = (
    '<svg class="lotus-svg" width="52" height="52" viewBox="0 0 52 52" '
    'fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">'
    '<ellipse cx="26" cy="26" rx="4.5" ry="11" fill="#F39C12" opacity="0.85"/>'
    '<ellipse cx="26" cy="26" rx="4.5" ry="11" fill="#F39C12" opacity="0.85" transform="rotate(45 26 26)"/>'
    '<ellipse cx="26" cy="26" rx="4.5" ry="11" fill="#F39C12" opacity="0.85" transform="rotate(90 26 26)"/>'
    '<ellipse cx="26" cy="26" rx="4.5" ry="11" fill="#F39C12" opacity="0.85" transform="rotate(135 26 26)"/>'
    '<circle cx="26" cy="26" r="4.5" fill="#F39C12"/>'
    '</svg>'
)

_DIVIDER = (
    '<div class="divider">'
    '<svg viewBox="0 0 600 12" width="100%" xmlns="http://www.w3.org/2000/svg">'
    '<path d="M0,6 Q150,1 300,6 Q450,11 600,6" stroke="#F39C12" fill="none" stroke-width="1.5"/>'
    '</svg>'
    '</div>\n'
)
