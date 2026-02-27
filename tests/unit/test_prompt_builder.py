import json
from app.services.prompt_builder import build_prompt


def _messages_as_text(messages: list) -> str:
    """Flatten list-of-dicts prompt into a single searchable string."""
    return " ".join(m.get("content", "") for m in messages)


def test_prompt_contains_masked_data(mock_cbs_data):
    user_query = "I can't login to netbanking"
    prompt = build_prompt(user_query, mock_cbs_data)

    assert isinstance(prompt, list), "build_prompt should return a list of messages"
    text = _messages_as_text(prompt)

    # The prompt should contain the masked account number
    assert "XXXXXX1234" in text
    # It should not contain a full unmasked account number
    assert "1234567890" not in text
    # It should contain the original query
    assert user_query in text


def test_prompt_is_json_safe(mock_cbs_data):
    """Ensure the CBS context embedded in the prompt is valid JSON."""
    user_query = "Test query"
    prompt = build_prompt(user_query, mock_cbs_data)

    assert isinstance(prompt, list)
    text = _messages_as_text(prompt)

    # Locate the JSON blob that follows "Masked CBS Context"
    marker = "Masked CBS Context (non-PII JSON):"
    assert marker in text, f"Expected '{marker}' in prompt messages"

    json_part = text.split(marker)[1].strip()
    # The JSON blob is the first {...} block
    start = json_part.index("{")
    end = json_part.index("}") + 1
    parsed = json.loads(json_part[start:end])
    assert parsed["masked_account"].startswith("XXXXXX")
