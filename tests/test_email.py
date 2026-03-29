"""
Tests for email utility functions.
"""

from utils.email_utils import strip_reply_prefix as _strip_reply_prefix


def test_plain_subject_unchanged():
    assert _strip_reply_prefix("Meeting tomorrow") == "Meeting tomorrow"


def test_single_re_stripped():
    assert _strip_reply_prefix("Re: Meeting tomorrow") == "Meeting tomorrow"


def test_double_re_stripped():
    assert _strip_reply_prefix("Re: Re: Meeting tomorrow") == "Meeting tomorrow"


def test_many_re_stripped():
    assert _strip_reply_prefix("Re: Re: Re: Re: Meeting tomorrow") == "Meeting tomorrow"


def test_uppercase_RE_stripped():
    assert _strip_reply_prefix("RE: Meeting tomorrow") == "Meeting tomorrow"


def test_lowercase_re_stripped():
    assert _strip_reply_prefix("re: Meeting tomorrow") == "Meeting tomorrow"


def test_mixed_case_stripped():
    assert _strip_reply_prefix("Re: RE: re: Meeting tomorrow") == "Meeting tomorrow"


def test_re_without_space_stripped():
    assert _strip_reply_prefix("Re:Meeting tomorrow") == "Meeting tomorrow"


def test_re_with_extra_spaces_stripped():
    assert _strip_reply_prefix("Re:   Meeting tomorrow") == "Meeting tomorrow"


def test_re_in_middle_preserved():
    assert _strip_reply_prefix("Notes Re: the meeting") == "Notes Re: the meeting"


def test_empty_subject():
    assert _strip_reply_prefix("") == ""


def test_only_re_prefix():
    assert _strip_reply_prefix("Re:") == ""


def test_subject_with_colons():
    assert _strip_reply_prefix("Re: Question: what time?") == "Question: what time?"
