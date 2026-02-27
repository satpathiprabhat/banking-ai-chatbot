# app/routes/assist.py

from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
from typing import Optional, List, Dict
import logging
import os
import re
import uuid

logger = logging.getLogger(__name__)

from app.services.auth import verify_jwt_token
from app.services.llm_stub import call_llm, mask_sensitive_info
from app.services.prompt_builder import build_prompt
from app.services.cbs_adapter import fetch_masked_netbanking
from app.services.compliance import enforce_output_policies  # post-gen guardrail

# Optional RAG (fail-open if not present)
try:
    from app.services import rag_service  # must expose retrieve(query: str, top_k: int)
    RAG_AVAILABLE = True
except Exception:
    rag_service = None  # type: ignore
    RAG_AVAILABLE = False

router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

# -------------------- Request Model --------------------
class AssistRequest(BaseModel):
    session_id: str
    customer_id: str
    query: str
    history: Optional[List[Dict]] = None  # tolerated; sanitized below

# -------------------- PII Gate --------------------
_PII_HINTS = re.compile(
    r"(account\s*number|card\s*number|cvv|otp|pan|ifsc|upi|aadhaar|aadhar|mobile\s*number)",
    re.IGNORECASE,
)
_LONG_DIGITS = re.compile(r"(?:\d[\s-]?){8,}")  # 8+ digits incl. spaces/dashes

def contains_pii_like(text: str) -> bool:
    if not isinstance(text, str) or not text.strip():
        return False
    return bool(_PII_HINTS.search(text) or _LONG_DIGITS.search(text))

SAFE_PII_RESPONSE = (
    "For your security, please don’t share account/card numbers, CVV, OTP, UPI IDs, PAN, IFSC or phone numbers here. "
    "I can guide you with general troubleshooting or connect you to secure support channels."
)

# -------------------- History Sanitization --------------------
_LOCKY = re.compile(r"\b(locked|blocked|suspended|disabled)\b", re.IGNORECASE)
_CREDY = re.compile(r"\b(wrong|invalid|incorrect)\s+(password|credentials|otp)\b", re.IGNORECASE)

def sanitize_history(history: Optional[List[Dict]], *, intent: str = "") -> List[Dict]:
    """
    - Drop any user turns that look like PII.
    - For 'transactional:feature', drop prior assistant/user lines asserting lock/cred issues.
    - Mask remaining content defensively.
    """
    if not history:
        return []
    cleaned: List[Dict] = []
    for m in history:
        role = (m.get("role") or "user").strip().lower()
        content = (m.get("content") or "").strip()
        if not content:
            continue
        if role == "user" and contains_pii_like(content):
            continue  # never carry PII forward
        if intent.startswith("transactional:feature") and (_LOCKY.search(content) or _CREDY.search(content)):
            continue  # avoid biasing feature flows with lock claims
        cleaned.append({"role": role, "content": mask_sensitive_info(content)})
    return cleaned

# -------------------- Intent + Sub-intent --------------------
_KNOWLEDGE_WORDS = re.compile(
    r"(how to|what is|faq|policy|interest rate|charges|limits|kyc|fd|rd|loan|card pin|reset pin|debit card|credit card|fees|guidelines|rbi)",
    re.IGNORECASE,
)
_TRANSACTIONAL_WORDS = re.compile(
    r"(balance|statement|failed login|netbanking|locked|blocked|otp failed|password reset|transfer|imps|neft|upi limit|account status)",
    re.IGNORECASE,
)
_FEATURE_ISSUE_WORDS = re.compile(
    r"(balance\s*enquir(y|ies)|balance\s*check|view\s*balance|mini\s*statement|txn\s*history|fund\s*transfer|bill\s*pay|card\s*controls)",
    re.IGNORECASE,
)
_LOGIN_ACCESS_WORDS = re.compile(
    r"(login|sign\s*in|otp\s*fail|password\s*reset|locked|blocked|credential|2fa|mfa)",
    re.IGNORECASE,
)

def detect_intent(query: str) -> str:
    """
    Return one of:
      - 'transactional:login'     (authentication/access problems)
      - 'transactional:feature'   (post-login feature issues)
      - 'knowledge'               (FAQ/policy/product info → RAG)
      - 'transactional'           (fallback transactional)
    Default to 'knowledge' if ambiguous (safer; avoids PII/CBS).
    """
    q = (query or "").strip()
    if _LOGIN_ACCESS_WORDS.search(q):
        return "transactional:login"
    if _FEATURE_ISSUE_WORDS.search(q):
        return "transactional:feature"
    if _KNOWLEDGE_WORDS.search(q):
        return "knowledge"
    if _TRANSACTIONAL_WORDS.search(q):
        return "transactional"
    return "knowledge"

# Feature keyword → KB retrieval hint
def _feature_hint(query: str) -> str:
    q = (query or "").lower()
    if "balance" in q:
        return "NetBanking balance enquiry troubleshooting"
    if "transfer" in q or "imps" in q or "neft" in q:
        return "Fund transfer troubleshooting"
    if "statement" in q:
        return "Mini statement / account statement troubleshooting"
    if "pin" in q and ("debit" in q or "credit" in q):
        return "Reset debit/credit card PIN steps"
    return "NetBanking feature troubleshooting steps"

# -------------------- Route --------------------
@router.post("/", response_model=dict)
async def assist(req: AssistRequest, token: str = Depends(oauth2_scheme)):
    """
    Flow:
      1) Verify JWT
      2) PII gate (short-circuit; no CBS/LLM)
      3) Detect intent (+ sub-intent)
      4) Build context:
         - knowledge → RAG retrieved chunks (no PII)
         - transactional:login → minimal lock/failed-login fields
         - transactional:feature → NO lock fields; DO retrieve KB troubleshooting
      5) Build prompt with sanitized history
      6) Call LLM (only if no PII)
      7) Post-gen guardrail to remove speculative lock/cred claims
    """
    request_id = f"req-{uuid.uuid4().hex[:12]}"

    # 1) AuthN
    username = verify_jwt_token(token)
    if not username:
        raise HTTPException(status_code=401, detail="Unauthorized")

    # 2) PII hard stop — DO NOT call CBS or LLM blocking if PII-data
    if contains_pii_like(req.query):
        logger.info("[AUDIT] PII-like input detected; request deflected — LLM/CBS skipped.")
        return {
            "request_id": request_id,
            "status": "ok",  # treated as normal assistant message in UI
            "message": SAFE_PII_RESPONSE,
            "intent": "pii_deflected",
            "rag_used": False,
            "sources": [],
        }

    # 3) Intent + sub-intent
    intent = detect_intent(req.query)

    # 4) Sanitize history (drop PII & lock-claims for feature flow)
    safe_history = sanitize_history(req.history, intent=intent)

    # 5) Prepare context depending on intent
    retrieved: List[Dict] = []  # type-stable list
    masked_ctx: Dict = {}

    logger.debug("intent=%s | RAG available=%s", intent, RAG_AVAILABLE)

    # Enable RAG for knowledge AND feature intents (blended mode)
    if (intent == "knowledge" or intent == "transactional:feature") and RAG_AVAILABLE:
        try:
            rag_query = req.query if intent == "knowledge" else _feature_hint(req.query)
            retrieved = rag_service.retrieve(rag_query, top_k=3)  # type: ignore
        except Exception as e:
            logger.warning("RAG retrieve failed: %s", e)
            retrieved = []
        logger.debug("RAG chunks retrieved: %d", len(retrieved))

    if intent == "transactional:login":
        # Only now call CBS; include lock-related fields (masked summary)
        service_token = os.getenv("SERVICE_TOKEN", "test-token")
        try:
            masked_full = fetch_masked_netbanking(req.customer_id, service_token)
        except Exception:
            raise HTTPException(status_code=500, detail="Failed to fetch CBS data")
        masked_ctx = {
            "netbanking_status": masked_full.get("netbanking_status"),
            "reason_code": masked_full.get("reason_code"),
            "last_failed_login": masked_full.get("last_failed_login"),
        }

    elif intent == "transactional:feature":
        # Post-login feature issue: DO NOT include lock/failed-login fields (prevents false 'blocked')
        masked_ctx = {
            "feature": "balance_enquiry" if "balance" in (req.query or "").lower() else "feature_issue",
            # In future: add benign telemetry (no PII), e.g., feature availability, maintenance.
        }

    elif intent == "transactional":
        # Generic transactional; keep it benign/minimal
        service_token = os.getenv("SERVICE_TOKEN", "test-token")
        try:
            masked_full = fetch_masked_netbanking(req.customer_id, service_token)
        except Exception:
            raise HTTPException(status_code=500, detail="Failed to fetch CBS data")
        masked_ctx = {
            "netbanking_status": masked_full.get("netbanking_status"),
            "reason_code": masked_full.get("reason_code"),
        }

    logger.debug("masked_ctx=%s | history_len=%d", masked_ctx, len(safe_history))

    # 6) Build prompt
    try:
        prompt = build_prompt(
            req.query,
            masked_context=masked_ctx,
            history=safe_history,
            intent=intent,
            retrieved=retrieved,
        )
    except TypeError:
        # Fallback if local build_prompt lacks new params
        prompt = [
            {"role": "system", "content": "You are a secure internal banking assistant. Never reveal PII."},
            {"role": "user", "content": req.query},
        ]

    # 7) Call LLM (only non-PII path reaches here)
    answer = call_llm(prompt)

    # 8) Post-gen guardrail: remove speculative lock/credential claims without evidence
    safe_answer, diag = enforce_output_policies(answer, intent=intent, masked_ctx=masked_ctx)
    if diag.get("changed"):
        logger.warning("[GUARDRAIL] Output rewritten: %s", diag)

    # 9) Prepare sources list for UI (always include)
    sources = [r.get("source") for r in retrieved if isinstance(r, dict) and r.get("source")]

    # 10) Consistent response for UI
    if isinstance(safe_answer, str) and safe_answer.startswith("I'm sorry, I'm currently facing"):
        return {
            "request_id": request_id,
            "status": "error",
            "message": safe_answer,
            "intent": intent,
            "rag_used": bool(retrieved),
            "sources": sources,
        }

    return {
        "request_id": request_id,
        "status": "ok",
        "message": safe_answer if isinstance(safe_answer, str) else "Sorry, something went wrong.",
        "intent": intent,
        "rag_used": bool(retrieved),
        "sources": sources,
    }