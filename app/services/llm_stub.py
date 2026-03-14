import logging
import os
import re
import time
from typing import List, Dict, Union

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

# Keep lazy singletons to avoid re-creating clients every call
_openai_client = None

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

# --------------------------
# Gemini path
# --------------------------
def _call_gemini(messages: List[Dict]) -> str:
    """
    Call Gemini using google-generativeai.
    - Gemini doesn't support 'system' role the same way; we merge system into first user message.
    - Uses generate_content with [{role, parts:[text]}].
    """
    try:
        import google.generativeai as genai  # pip install google-generativeai
    except Exception as e:
        raise RuntimeError("Google Generative AI SDK not installed. `pip install google-generativeai`") from e

    settings = get_settings()
    api_key = settings.gemini_api_key or settings.openai_api_key
    if not api_key:
        raise ValueError("Missing GEMINI_API_KEY (or legacy OPENAI_API_KEY) in environment variables.")
    genai.configure(api_key=api_key)  # type: ignore

    # Merge system messages into the first user message (your existing workaround)
    system_contents: List[str] = []
    other_messages: List[Dict] = []
    for m in messages:
        if m.get("role") == "system":
            system_contents.append(m.get("content", "") or "")
        else:
            other_messages.append(m)

    if system_contents:
        joined = "\n\n".join(system_contents).strip()
        if other_messages:
            other_messages[0]["content"] = f"{joined}\n\n{other_messages[0].get('content','')}"
        else:
            other_messages = [{"role": "user", "content": joined}]

    # Convert roles for Gemini (only "user" and "model" allowed)
    gemini_input = []
    for m in other_messages:
        role = m.get("role", "user")

        # Gemini only accepts "user" and "model"
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
    model = genai.GenerativeModel(model_id)  # type: ignore

    start = time.time()
    resp = model.generate_content(gemini_input)
    dur = time.time() - start
    logger.info("Gemini call completed in %.2fs", dur)

    if hasattr(resp, "text") and resp.text:
        return resp.text
    return "[Error] No response text received from Gemini."

# --------------------------
# OpenAI path
# --------------------------
def _ensure_openai_client():
    global _openai_client
    if _openai_client is None:
        try:
            from openai import OpenAI  # type: ignore # pip install openai>=1.0.0
        except Exception as e:
            raise RuntimeError("OpenAI SDK not installed. `pip install openai`") from e

        # OpenAI SDK reads OPENAI_API_KEY from env
        settings = get_settings()
        if not settings.openai_api_key:
            raise ValueError("Missing OPENAI_API_KEY in environment variables.")
        _openai_client = OpenAI()
    return _openai_client

def _call_openai(messages: List[Dict]) -> str:
    """
    Call OpenAI Chat Completions API (SDK v1+). Supports 'system' role natively.
    """
    client = _ensure_openai_client()

    oa_messages = [{"role": m.get("role", "user"), "content": m.get("content", "") or ""} for m in messages]
    logger.debug("OpenAI messages (masked): %s", oa_messages)

    settings = get_settings()
    model_id = settings.llm_model_id or "gpt-4o-mini"

    start = time.time()
    resp = client.chat.completions.create(
        model=model_id,
        messages=oa_messages, # type: ignore
        temperature=0.2,
    )
    dur = time.time() - start
    logger.info("OpenAI call completed in %.2fs | resp_id=%s", dur, getattr(resp, "id", "n/a"))

    try:
        return resp.choices[0].message.content or "[Error] Empty response from OpenAI."
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
