# app/services/prompt_builder.py
"""
Prompt builder for the Banking GenAI assistant.

Output: list[dict] chat messages (system + user/assistant). llm_stub adapts per provider.
"""

from typing import List, Dict, Optional
import json

# -------------------- Base System Instruction --------------------
SYSTEM_INSTRUCTION = """You are a secure internal banking assistant.
You must ALWAYS:
- Protect customer privacy. NEVER reveal, request, or infer PII (account numbers, card numbers, CVV, OTP, PAN, IFSC, UPI, Aadhaar, phone, email).
- Follow least-privilege: use only the masked context provided; do not assume hidden data.
- Be formal, precise, concise, and action-oriented. Prefer stepwise troubleshooting checklists.
- If the user shares possible PII, warn once and refuse to process it.

Critical anti-hallucination rules:
- Do NOT invent balances, fees, rates, limits, or policy details.
- Do NOT claim the customer account is locked/blocked or credentials are wrong UNLESS:
  (a) the user explicitly said so in this conversation, OR
  (b) the provided masked context explicitly confirms it (e.g., netbanking_status='LOCKED').
- If information is missing from the provided context, say you don’t know and propose the safest next step.

Domain scope:
- Banking troubleshooting (NetBanking/Mobile), generic product/FAQ guidance.
- Compliance with bank security policy at all times.
"""

# -------------------- Helpers --------------------
def _pretty_json(d: Dict, max_chars: int = 1200) -> str:
    try:
        s = json.dumps(d or {}, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    except Exception:
        s = "{}"
    return s[:max_chars]

def _carry_history(history: Optional[List[Dict]], limit: int = 8, max_chars_each: int = 800) -> List[Dict]:
    if not history:
        return []
    trimmed = history[-limit:]
    out: List[Dict] = []
    for m in trimmed:
        role = (m.get("role") or "user").strip().lower()
        content = (m.get("content") or "").strip()
        if not content:
            continue
        if len(content) > max_chars_each:
            content = content[:max_chars_each] + " ..."
        out.append({"role": role, "content": content})
    return out

# -------------------- Main builder --------------------
def build_prompt(
    query: str,
    masked_context: Optional[Dict] = None,
    history: Optional[List[Dict]] = None,
    intent: Optional[str] = None,
) -> List[Dict]:
    messages: List[Dict] = []

    # ---- Dynamic rule block (kept inside ONE system message) ----
    dyn_rules: List[str] = []

    if intent == "knowledge":
        dyn_rules.append(
            "This is a banking knowledge request. Provide concise, general guidance and avoid claiming bank-specific "
            "rates, fees, or policy details unless they are explicitly provided in the conversation."
        )

    if intent == "transactional:feature":
        dyn_rules.append(
            "This is a post-login feature issue. Use the masked CBS context as the only system-provided fact source. "
            "Do NOT assert lock/blocked/credential errors unless explicitly confirmed. "
            "If facts are insufficient, ask for non-PII clarifications and propose safe next steps."
        )

    if intent == "transactional:login":
        dyn_rules.append(
            "This is an authentication/access issue. If the Masked CBS Context indicates LOCKED or FAILED_OTP, "
            "explain unblocking steps safely; otherwise ask for non-PII clarifications."
        )

    sys_content = SYSTEM_INSTRUCTION
    if dyn_rules:
        sys_content += "\n\nContext-specific rules:\n- " + "\n- ".join(dyn_rules)
    messages.append({"role": "system", "content": sys_content})

    # ---- Context blocks (as user messages for transparency) ----
    if masked_context:
        messages.append({
            "role": "user",
            "content": f"Masked CBS Context (non-PII JSON): { _pretty_json(masked_context) }"
        })

    # ---- Carry sanitized history ----
    for h in _carry_history(history):
        messages.append(h)

    # ---- Final user query ----
    messages.append({"role": "user", "content": query.strip() if isinstance(query, str) else ""})

    return messages
