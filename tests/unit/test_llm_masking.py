import re
import pytest
from app.services.llm_stub import mask_sensitive_info

# Regex for detecting unmasked account numbers
ACCOUNT_REGEX = re.compile(r"\b\d{10,12}\b")

def test_masks_account_number():
    text = "Customer account number is 123456789012"
    masked = mask_sensitive_info(text)
    assert "XXXXXX" in masked
    assert not ACCOUNT_REGEX.search(masked)

def test_does_not_change_unrelated_text():
    text = "Hello, your appointment is confirmed."
    masked = mask_sensitive_info(text)
    assert masked == text

def test_does_not_mask_years():
    text = "The year is 2025"
    masked = mask_sensitive_info(text)
    # Should remain unchanged
    assert masked == text
    assert "2025" in masked

def test_detects_pii_leak():
    """Simulate scanning LLM output for unmasked account numbers."""
    llm_output = "The account 123456789012 is blocked."
    leak_detected = bool(ACCOUNT_REGEX.search(llm_output))
    assert leak_detected, "Unmasked account number should be detected!"