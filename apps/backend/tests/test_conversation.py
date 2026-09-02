"""Conversation history for multi-turn exchanges."""

from personae.conversation import History, Turn


def test_starts_empty() -> None:
    assert History().messages() == []


def test_records_turns_in_order() -> None:
    history = History()
    history.add(Turn(user="hello", assistant="hi there"))
    history.add(Turn(user="how are you", assistant="fine"))
    assert [m["content"] for m in history.messages()] == [
        "hello",
        "hi there",
        "how are you",
        "fine",
    ]


def test_alternates_user_and_assistant_roles() -> None:
    history = History()
    history.add(Turn(user="hello", assistant="hi"))
    assert [m["role"] for m in history.messages()] == ["user", "assistant"]


def test_drops_the_oldest_turns_beyond_the_window() -> None:
    """A live session runs indefinitely; the prompt must not grow with it."""
    history = History(max_turns=2)
    for i in range(5):
        history.add(Turn(user=f"q{i}", assistant=f"a{i}"))
    assert [m["content"] for m in history.messages()] == ["q3", "a3", "q4", "a4"]


def test_keeps_an_interrupted_reply_as_what_was_actually_said() -> None:
    """After a barge-in she must not refer to words the listener never heard."""
    history = History()
    history.add(Turn(user="tell me about it", assistant="Well, the first thing"))
    assert history.messages()[-1]["content"] == "Well, the first thing"


def test_ignores_a_turn_with_no_reply() -> None:
    """Interrupting before she speaks should leave no trace."""
    history = History()
    history.add(Turn(user="wait", assistant=""))
    assert history.messages() == []
