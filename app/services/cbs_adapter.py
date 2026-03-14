from datetime import datetime

from app.config import get_settings

def fetch_masked_netbanking(customer_id: str, service_token: str) -> dict:
    """
    Mock CBS adapter that returns masked, non-PII summary of a customer's NetBanking state.

    - Neutral by default (ACTIVE, not locked)
    - To simulate a lock: set env var MOCK_LOCKED_STATUS=true

    Production notes:
      - Query CBS via secure middleware
      - Mask PII before returning
      - Never return full account numbers, PAN, etc.
    """
    locked = get_settings().mock_locked_status

    if locked:
        return {
            "masked_account": "XXXXXX1234",
            "netbanking_status": "LOCKED",
            "reason_code": "FAILED_OTP_3",
            "last_failed_login": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

    # Neutral/default branch (no lock)
    return {
        "masked_account": "XXXXXX1234",
        "netbanking_status": "ACTIVE",
        "reason_code": None,
        "last_failed_login": None,
    }
