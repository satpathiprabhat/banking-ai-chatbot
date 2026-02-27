import pytest
from fastapi.testclient import TestClient
from app.main import app

@pytest.fixture
def client():
    """FastAPI test client."""
    return TestClient(app)

@pytest.fixture
def mock_cbs_data():
    """Mocked CBS adapter response with masked account number."""
    return {
        "customer_id": "CUST-0001",
        "masked_account": "XXXXXX1234",
        "netbanking_status": "LOCKED",
        "last_failed_login": "2025-08-10T09:12:00Z",
        "reason_code": "FAILED_OTP_3"
    }

@pytest.fixture
def mock_llm_response():
    """Mock LLM response."""
    return "Your netbanking access is currently locked due to 3 failed OTP attempts. Please reset your password or contact branch."