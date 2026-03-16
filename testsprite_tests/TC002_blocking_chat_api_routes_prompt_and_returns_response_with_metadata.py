import requests

BASE_URL = "http://localhost:8000"
API_KEY = "350b6ac402988036f99784fbdb71c040527801dd021f88f04cef0dd03425335e"
HEADERS = {"X-API-Key": API_KEY, "Content-Type": "application/json"}
TIMEOUT = 30


def test_blocking_chat_api_routes_prompt_and_returns_response_with_metadata():
    url = f"{BASE_URL}/v1/chat"
    prompt = "What is the capital of France?"
    payload = {"prompt": prompt}

    # 1) Test valid request - expect 200 and proper metadata fields
    resp = requests.post(url, headers=HEADERS, json=payload, timeout=TIMEOUT)
    assert resp.status_code == 200, f"Unexpected status code {resp.status_code}, body: {resp.text}"
    data = resp.json()
    # Check required fields present
    assert "response" in data and isinstance(data["response"], str) and len(data["response"]) > 0
    assert "model_used" in data and isinstance(data["model_used"], str) and len(data["model_used"]) > 0
    assert "difficulty_tag" in data and data["difficulty_tag"] in ["simple", "medium", "complex"]
    assert "cost_usd" in data and isinstance(data["cost_usd"], (float, int))
    assert "latency_ms" in data and isinstance(data["latency_ms"], int)
    assert "escalated" in data and isinstance(data["escalated"], bool)

    # 2) Test missing API key - expect 403
    resp_no_key = requests.post(url, headers={"Content-Type": "application/json"}, json=payload, timeout=TIMEOUT)
    assert resp_no_key.status_code == 403
    assert resp_no_key.text.lower().find("invalid_api_key") != -1

    # 3) Test invalid API key - expect 403
    headers_invalid_key = {"X-API-Key": "invalidkey123", "Content-Type": "application/json"}
    resp_bad_key = requests.post(url, headers=headers_invalid_key, json=payload, timeout=TIMEOUT)
    assert resp_bad_key.status_code == 403
    assert resp_bad_key.text.lower().find("invalid_api_key") != -1

    # 4) Test empty prompt - expect 422 Unprocessable Entity
    empty_prompt_payload = {"prompt": ""}
    resp_empty_prompt = requests.post(url, headers=HEADERS, json=empty_prompt_payload, timeout=TIMEOUT)
    assert resp_empty_prompt.status_code == 422


test_blocking_chat_api_routes_prompt_and_returns_response_with_metadata()