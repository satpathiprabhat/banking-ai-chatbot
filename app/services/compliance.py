# app/services/compliance.py
import re
from typing import Dict, Tuple

# Phrases we want to block unless evidence exists in context
_LOCK_PHRASES = re.compile(
    r"\b(account\s+is\s+)?(locked|blocked|suspended|disabled)\b", re.IGNORECASE
)
_CRED_PHRASES = re.compile(
    r"\b(wrong|invalid|incorrect)\s+(password|credentials|otp)\b", re.IGNORECASE
)

def _has_lock_evidence(masked_ctx: Dict) -> bool:
    status = (masked_ctx or {}).get("netbanking_status", "")
    reason = (masked_ctx or {}).get("reason_code", "")
    # Treat explicit lock signals as evidence
    return str(status).upper() in {"LOCKED", "BLOCKED"} or str(reason).upper().startswith("FAILED_")

def _should_block_claims(intent: str, masked_ctx: Dict) -> bool:
    """
    Block lock/credential claims when:
      - sub-intent is 'transactional:feature' (post-login) OR
      - there's no explicit evidence in context
    """
    if (intent or "").startswith("transactional:feature"):
        return True
    return not _has_lock_evidence(masked_ctx)

def enforce_output_policies(answer: str, intent: str, masked_ctx: Dict) -> Tuple[str, Dict]:
    """
    If assistant asserts lock/blocked/credential-failure without evidence,
    rewrite those sentences into a safe clarification.
    Returns (possibly_rewritten_answer, diagnostics).
    """
    if not isinstance(answer, str) or not answer.strip():
        return answer, {"changed": False, "reason": "empty_or_non_string"}

    must_block = _should_block_claims(intent, masked_ctx)
    changed = False
    notes = []

    rewritten = answer

    if must_block and _LOCK_PHRASES.search(rewritten):
        rewritten = _LOCK_PHRASES.sub(
            "we can't confirm your account status from the available information",
            rewritten
        )
        changed = True
        notes.append("removed_unproven_lock_claim")

    if must_block and _CRED_PHRASES.search(rewritten):
        rewritten = _CRED_PHRASES.sub(
            "we can’t confirm a credential issue based on current information",
            rewritten
        )
        changed = True
        notes.append("removed_unproven_credential_claim")

    # If we changed anything, append a gentle clarification sentence once.
    if changed:
        tail = (
            "\n\n*Note:* Based on the current context, we avoid asserting lock/credential issues without "
            "explicit confirmation. If you can share the exact on-screen error message (no PII), "
            "I can guide you with precise next steps."
        )
        # Avoid duplicating the note if already present
        if tail.strip() not in rewritten:
            rewritten = rewritten.rstrip() + tail

    return rewritten, {"changed": changed, "notes": notes or None}