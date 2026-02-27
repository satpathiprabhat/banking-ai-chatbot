import pytest
from app.services.auth import create_jwt_token


def test_assist_endpoint_with_mocks(client, mock_cbs_data, mock_llm_response, monkeypatch):
    """Integration test for /assist endpoint with mocked CBS + LLM."""

    # Patch at the usage site (app.routes.assist imports these names directly)
    monkeypatch.setattr("app.routes.assist.fetch_masked_netbanking", lambda customer_id, service_token: mock_cbs_data)
    monkeypatch.setattr("app.routes.assist.call_llm", lambda prompt: mock_llm_response)

    token = create_jwt_token("admin")
    payload = {
        "session_id": "s-abc-123",
        "customer_id": "CUST-0001",
        "query": "I can't login to netbanking",
    }

    response = client.post(
        "/assist/",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    data = response.json()

    assert response.status_code == 200
    assert data["status"] == "ok"
    # "locked" may remain if CBS confirms it; compliance guardrail allows it here
    assert "locked" in data["message"].lower()
    # Ensure no unmasked account number in response
    assert "123456" not in data["message"]
