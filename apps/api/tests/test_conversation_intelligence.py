from app.api.v1.inbox import _human_request_reason
from app.domains.assistant.prompts import MAX_HISTORY_CHARS, render_history


def test_explicit_human_request_is_detected_without_matching_partial_words() -> None:
    expected = "Customer requested human support"
    assert _human_request_reason("Please connect me with a human") == expected
    assert _human_request_reason("The agent is already helping") == expected
    assert _human_request_reason("I need help understanding the policy") is None


def test_conversation_history_is_bounded_to_the_prompt_budget() -> None:
    rendered = render_history([("user", "important context " * 200) for _ in range(20)])
    assert len(rendered) <= MAX_HISTORY_CHARS + len("CONVERSATION (not evidence):\n")
