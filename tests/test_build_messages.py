"""
Tests for _build_messages — the function that assembles the Claude messages
array from thread history and the current incoming message.
"""

from utils.messages import build_messages as _build_messages


def test_no_history():
    result = _build_messages([], "hello")
    assert result == [{"role": "user", "content": "hello"}]


def test_single_user_in_history():
    history = [{"role": "user", "content": "previous question"}]
    result = _build_messages(history, "follow up")
    assert result == [
        {"role": "user", "content": "previous question"},
        {"role": "user", "content": "follow up"},
    ]


def test_normal_alternating_history():
    history = [
        {"role": "user", "content": "question"},
        {"role": "assistant", "content": "answer"},
    ]
    result = _build_messages(history, "follow up")
    assert result == [
        {"role": "user", "content": "question"},
        {"role": "assistant", "content": "answer"},
        {"role": "user", "content": "follow up"},
    ]


def test_longer_alternating_history():
    history = [
        {"role": "user", "content": "q1"},
        {"role": "assistant", "content": "a1"},
        {"role": "user", "content": "q2"},
        {"role": "assistant", "content": "a2"},
    ]
    result = _build_messages(history, "q3")
    assert len(result) == 5
    assert result[-1] == {"role": "user", "content": "q3"}
    assert result[0]["role"] == "user"


def test_leading_assistant_is_dropped():
    history = [{"role": "assistant", "content": "orphaned reply"}]
    result = _build_messages(history, "new message")
    assert result == [{"role": "user", "content": "new message"}]


def test_leading_assistant_then_rest_kept():
    history = [
        {"role": "assistant", "content": "orphaned"},
        {"role": "user", "content": "follow up"},
        {"role": "assistant", "content": "reply"},
    ]
    result = _build_messages(history, "current")
    assert result == [
        {"role": "user", "content": "follow up"},
        {"role": "assistant", "content": "reply"},
        {"role": "user", "content": "current"},
    ]


def test_consecutive_user_messages_merged():
    history = [
        {"role": "user", "content": "first"},
        {"role": "user", "content": "second"},
    ]
    result = _build_messages(history, "third")
    assert result[0]["role"] == "user"
    assert result[0]["content"] == "first\n\n---\n\nsecond"


def test_consecutive_assistant_messages_merged():
    history = [
        {"role": "user", "content": "question"},
        {"role": "assistant", "content": "part one"},
        {"role": "assistant", "content": "part two"},
    ]
    result = _build_messages(history, "follow up")
    assert result == [
        {"role": "user", "content": "question"},
        {"role": "assistant", "content": "part one\n\n---\n\npart two"},
        {"role": "user", "content": "follow up"},
    ]


def test_all_assistant_history_dropped():
    history = [
        {"role": "assistant", "content": "reply one"},
        {"role": "assistant", "content": "reply two"},
    ]
    result = _build_messages(history, "new message")
    assert result == [{"role": "user", "content": "new message"}]


def test_current_message_always_last():
    history = [
        {"role": "user", "content": "a"},
        {"role": "assistant", "content": "b"},
    ]
    result = _build_messages(history, "current")
    assert result[-1] == {"role": "user", "content": "current"}


def test_current_message_always_user_role():
    result = _build_messages([], "message")
    assert result[-1]["role"] == "user"


def test_history_not_mutated():
    history = [
        {"role": "user", "content": "original"},
        {"role": "assistant", "content": "reply"},
    ]
    original_history = [dict(m) for m in history]
    _build_messages(history, "new")
    assert history == original_history
