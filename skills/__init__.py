"""
Skills package

Skills are compound, multi-step capabilities built on top of primitive tools.
Each Skill orchestrates several tool calls and reasoning steps into a single,
named, repeatable action.
"""

from .hn_digest import HNDigestSkill
from .dashboard import DashboardSkill

__all__ = ["HNDigestSkill", "DashboardSkill"]
