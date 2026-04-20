"""
Skills package

Skills are compound, multi-step capabilities built on top of primitive tools.
Each Skill orchestrates several tool calls and reasoning steps into a single,
named, repeatable action.
"""

from .hn_digest import HNDigestSkill
from .dashboard import DashboardSkill
from .vietnamese_study import VietnameseStudySkill
from .vietnamese_vocab import VietnameseVocabSkill

__all__ = ["HNDigestSkill", "DashboardSkill", "VietnameseStudySkill", "VietnameseVocabSkill"]
