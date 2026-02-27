# app/services/prompt_builder.py
"""
Prompt builder for the Banking GenAI assistant.

Blended Context:
- For knowledge intent → STRICT grounding to retrieved KB.
- For transactional:feature → Blend masked CBS context (facts) + KB troubleshooting (procedures).
- For transactional:login → Include minimal lock/2FA context if present.

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

def _format_rag_context(retrieved: Optional[List[Dict]], max_chunks: int = 3, max_chars: int = 1800) -> str:
    if not retrieved:
        return ""
    lines: List[str] = []
    for i, r in enumerate(retrieved[:max_chunks], start=1):
        src = r.get("source") or f"doc#{i}"
        txt = (r.get("doc") or "").strip().replace("\r\n", "\n")
        if not txt:
            continue
        if len(txt) > 800:
            txt = txt[:800] + " ..."
        lines.append(f"- [{src}] {txt}")
    block = "\n".join(lines)
    return block[:max_chars]

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
    retrieved: Optional[List[Dict]] = None,
) -> List[Dict]:
    messages: List[Dict] = []

    # ---- Dynamic rule block (kept inside ONE system message) ----
    dyn_rules: List[str] = []

    if intent == "knowledge":
        dyn_rules.append(
            "For this request, you MUST answer ONLY using the 'Knowledge Context' provided below. "
            "If the Knowledge Context does not contain the answer, reply exactly once: "
            "\"I don’t have enough information from the bank’s knowledge base to answer that.\" "
            "Then suggest a safe next step. Do NOT use outside knowledge; do NOT guess."
        )

    if intent == "transactional:feature":
        dyn_rules.append(
            "This is a post-login feature issue. Blend the following sources in order:\n"
            "1) Masked CBS Context → treat as ground truth facts.\n"
            "2) Knowledge Context (if present) → use for troubleshooting steps and safe procedures.\n"
            "Rules: Do NOT assert lock/blocked/credential errors unless explicitly confirmed. "
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

    rag_block = _format_rag_context(retrieved)
    if intent == "knowledge":
        if rag_block:
            messages.append({
                "role": "user",
                "content": "Knowledge Context (use ONLY this context to answer):\n" + rag_block
            })
        else:
            messages.append({
                "role": "user",
                "content": (
                    "Knowledge Context: [NONE]\n"
                    "You must state that you don’t have enough information from the bank’s knowledge base to answer."
                )
            })
    elif intent == "transactional:feature":
        # In blended mode, include KB if present, but clearly labelled
        if rag_block:
            messages.append({
                "role": "user",
                "content": "Knowledge Context (troubleshooting procedures):\n" + rag_block
            })

    else:
        # transactional (generic) — optional KB reference if present
        if rag_block:
            messages.append({
                "role": "user",
                "content": "Knowledge Context (reference if relevant):\n" + rag_block
            })

    # ---- Carry sanitized history ----
    for h in _carry_history(history):
        messages.append(h)

    # ---- Final user query ----
    messages.append({"role": "user", "content": query.strip() if isinstance(query, str) else ""})

    return messages