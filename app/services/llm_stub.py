import logging
import re
import time
from typing import List, Dict, Union

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

# --------------------------
# Masking (unchanged)
# --------------------------
def mask_sensitive_info(text: str) -> str:
    """
    Mask account numbers and similar PII patterns in the text.
    Example: 1234567890 -> XXXXXX7890
    """
    if not isinstance(text, str):
        return text  # safety
    return re.sub(r'\b\d{6}(\d{4,6})\b', r'XXXXXX\1', text)

REQUEST_TIMEOUT_SECONDS = 30.0

def _to_messages(prompt: Union[str, List[Dict]]) -> List[Dict]:
    """
    Normalize input into a list of chat messages: [{role, content}]
    """
    if isinstance(prompt, list):
        msgs: List[Dict] = []
        for m in prompt:
            role = m.get("role", "user")
            content = m.get("content", "")
            msgs.append({"role": role, "content": content})
        return msgs
    else:
        return [{"role": "user", "content": str(prompt)}]

def _mask_messages(messages: List[Dict]) -> List[Dict]:
    """
    Apply masking to each message content before leaving our server.
    """
    masked = []
    for m in messages:
        masked.append({
            "role": m.get("role", "user"),
            "content": mask_sensitive_info(m.get("content", "")),
        })
    return masked


def _merge_system_into_first_user(messages: List[Dict]) -> List[Dict]:
    system_contents: List[str] = []
    other_messages: List[Dict] = []

    for m in messages:
        if m.get("role") == "system":
            system_contents.append(m.get("content", "") or "")
        else:
            other_messages.append({
                "role": m.get("role", "user"),
                "content": m.get("content", "") or "",
            })

    if system_contents:
        joined = "\n\n".join(system_contents).strip()
        if other_messages:
            other_messages[0]["content"] = f"{joined}\n\n{other_messages[0].get('content', '')}".strip()
        else:
            other_messages = [{"role": "user", "content": joined}]

    return other_messages

# --------------------------
# Gemini path
# --------------------------
def _call_gemini(messages: List[Dict]) -> str:
    """
    Call Gemini via the REST API.
    - Merge system messages into the first user message for stable behavior.
    - Uses generateContent with {contents:[{role, parts:[{text}]}]}.
    """
    settings = get_settings()
    api_key = settings.llm_api_key or settings.gemini_api_key or settings.openai_api_key
    if not api_key:
        raise ValueError("Missing GEMINI_API_KEY (or legacy OPENAI_API_KEY) in environment variables.")
    other_messages = _merge_system_into_first_user(messages)

    # Convert roles for Gemini (only "user" and "model" allowed)
    gemini_input: List[Dict] = []
    for m in other_messages:
        role = m.get("role", "user")
        if role == "assistant":
            role = "model"
        elif role not in ("user", "model"):
            role = "user"
        gemini_input.append({
            "role": role,
            "parts": [{"text": m.get("content", "") or ""}]
        })

    logger.debug("Prepared gemini_input (masked): %s", gemini_input)

    model_id = settings.llm_model_id or "gemini-1.5-flash"
    logger.debug("Using Gemini model: %s", model_id)
    base_url = settings.llm_base_url or settings.gemini_base_url
    url = f"{base_url}/models/{model_id}:generateContent"
    payload = {"contents": gemini_input}

    start = time.time()
    response = httpx.post(
        url,
        params={"key": api_key},
        json=payload,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    dur = time.time() - start
    logger.info("Gemini REST call completed in %.2fs | status=%s", dur, response.status_code)
    response.raise_for_status()

    data = response.json()

    candidates = data.get("candidates") or []
    if candidates:
        content = (candidates[0] or {}).get("content") or {}
        parts = content.get("parts") or []
        texts = [part.get("text", "") for part in parts if isinstance(part, dict) and part.get("text")]
        if texts:
            return "\n".join(texts).strip()
    return "[Error] No response text received from Gemini."

# --------------------------
# OpenAI path
# --------------------------
def _call_openai(messages: List[Dict]) -> str:
    """
    Call OpenAI Chat Completions via the REST API.
    """
    oa_messages = [{"role": m.get("role", "user"), "content": m.get("content", "") or ""} for m in messages]
    logger.debug("OpenAI messages (masked): %s", oa_messages)

    settings = get_settings()
    api_key = settings.llm_api_key or settings.openai_api_key
    if not api_key:
        raise ValueError("Missing OPENAI_API_KEY in environment variables.")
    model_id = settings.llm_model_id or "gpt-4o-mini"
    base_url = settings.llm_base_url or settings.openai_base_url
    payload = {
        "model": model_id,
        "messages": oa_messages,
        "temperature": 0.2,
    }

    start = time.time()
    response = httpx.post(
        f"{base_url}/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    dur = time.time() - start
    logger.info("OpenAI REST call completed in %.2fs | status=%s", dur, response.status_code)
    response.raise_for_status()

    data = response.json()

    try:
        return data["choices"][0]["message"]["content"] or "[Error] Empty response from OpenAI."
    except Exception:
        return "[Error] Failed to parse OpenAI response."

# --------------------------
# Unified entrypoint (unchanged signature)
# --------------------------
def call_llm(prompt: Union[str, List[Dict]]) -> str:
    """
    Unified entry point.
    Accepts:
      - string prompt OR
      - list of chat messages: [{"role": "system"|"user"|"assistant", "content": "..."}]
    Applies masking and routes to configured provider.
    """
    logger.debug("call_llm invoked | prompt type: %s", type(prompt).__name__)

    try:
        messages = _to_messages(prompt)
        masked_messages = _mask_messages(messages)

        provider = get_settings().llm_provider
        logger.debug("LLM provider: %s", provider)

        if provider == "openai":
            return _call_openai(masked_messages)
        # default: gemini
        return _call_gemini(masked_messages)

    except Exception as e:
        logger.error("LLM call failed: %s", e, exc_info=True)
        return "I'm sorry, I'm currently facing some technical difficulties. Please try again in a little while."
