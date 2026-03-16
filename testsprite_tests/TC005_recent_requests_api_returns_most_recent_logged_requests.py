import requests
from datetime import datetime
import time

BASE_URL = "http://localhost:8000"
API_KEY = "350b6ac402988036f99784fbdb71c040527801dd021f88f04cef0dd03425335e"
HEADERS = {"X-API-Key": API_KEY}
TIMEOUT = 30

def test_recent_requests_api_returns_most_recent_logged_requests():
    # Helper function to create a chat request to ensure at least one recent record exists
    def create_chat_request(prompt: str):
        url = f"{BASE_URL}/v1/chat"
        payload = {"prompt": prompt}
        resp = requests.post(url, json=payload, headers=HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()
        return resp.json()

    # Helper function to delete a request if supported (PRD doesn't show delete endpoint,
    # so this is a no-op, but we follow instructions if needed)

    # 1) Ensure at least one recent request by creating a chat request
    chat_response = None
    try:
        chat_response = create_chat_request("What is the capital of France?")
    except requests.exceptions.HTTPError as e:
        # If 500 internal error due to ANTHROPIC_API_KEY missing, retry with a different prompt to avoid failures
        if e.response.status_code == 500:
            # Try a different prompt that might not cause error or skip
            chat_response = create_chat_request("Hello world")
        else:
            raise

    # 2) Test GET /v1/recent with default limit (20)
    url_recent = f"{BASE_URL}/v1/recent"
    resp_default = requests.get(url_recent, headers=HEADERS, timeout=TIMEOUT)
    assert resp_default.status_code == 200, f"Expected 200 got {resp_default.status_code}"
    results_default = resp_default.json()
    assert isinstance(results_default, list), "Response must be a list"
    # Check limit default max 20
    assert len(results_default) <= 20, f"Expected at most 20 results, got {len(results_default)}"
    # Check fields and order descending by created_at
    previous_created_at = None
    for item in results_default:
        # Validate each field presence and types
        assert "created_at" in item, "Missing created_at field"
        assert "difficulty_tag" in item, "Missing difficulty_tag field"
        assert "model_used" in item, "Missing model_used field"
        assert "cost_usd" in item, "Missing cost_usd field"
        assert "cost_saved_usd" in item, "Missing cost_saved_usd field"
        assert "latency_ms" in item, "Missing latency_ms field"
        assert "escalated" in item, "Missing escalated field"
        # Validate types
        # created_at ISO8601 string parse check
        try:
            curr_created_at = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
        except Exception:
            assert False, f"created_at is not valid ISO8601: {item['created_at']}"
        assert isinstance(item["difficulty_tag"], str), "difficulty_tag must be a string"
        assert isinstance(item["model_used"], str), "model_used must be a string"
        assert isinstance(item["cost_usd"], (float, int)), "cost_usd must be float or int"
        assert isinstance(item["cost_saved_usd"], (float, int)), "cost_saved_usd must be float or int"
        assert isinstance(item["latency_ms"], int), "latency_ms must be int"
        assert isinstance(item["escalated"], bool), "escalated must be bool"
        # Check ordering descending by created_at
        if previous_created_at is not None:
            assert curr_created_at <= previous_created_at, "Results not ordered by created_at descending"
        previous_created_at = curr_created_at

    # 3) Test GET /v1/recent with custom limit parameter (e.g. limit=5)
    params = {"limit": 5}
    resp_limit = requests.get(url_recent, headers=HEADERS, params=params, timeout=TIMEOUT)
    assert resp_limit.status_code == 200, f"Expected 200 got {resp_limit.status_code}"
    results_limit = resp_limit.json()
    assert isinstance(results_limit, list), "Response must be a list"
    assert len(results_limit) <= 5, f"Expected at most 5 results, got {len(results_limit)}"
    previous_created_at = None
    for item in results_limit:
        # Validate each field presence and types same as above
        assert "created_at" in item, "Missing created_at field"
        assert "difficulty_tag" in item, "Missing difficulty_tag field"
        assert "model_used" in item, "Missing model_used field"
        assert "cost_usd" in item, "Missing cost_usd field"
        assert "cost_saved_usd" in item, "Missing cost_saved_usd field"
        assert "latency_ms" in item, "Missing latency_ms field"
        assert "escalated" in item, "Missing escalated field"
        try:
            curr_created_at = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
        except Exception:
            assert False, f"created_at is not valid ISO8601: {item['created_at']}"
        assert isinstance(item["difficulty_tag"], str), "difficulty_tag must be a string"
        assert isinstance(item["model_used"], str), "model_used must be a string"
        assert isinstance(item["cost_usd"], (float, int)), "cost_usd must be float or int"
        assert isinstance(item["cost_saved_usd"], (float, int)), "cost_saved_usd must be float or int"
        assert isinstance(item["latency_ms"], int), "latency_ms must be int"
        assert isinstance(item["escalated"], bool), "escalated must be bool"
        # Check ordering descending by created_at
        if previous_created_at is not None:
            assert curr_created_at <= previous_created_at, "Results not ordered by created_at descending"
        previous_created_at = curr_created_at

    # 4) Test GET /v1/recent without API key returns 403
    resp_unauth = requests.get(url_recent, timeout=TIMEOUT)
    assert resp_unauth.status_code == 403, f"Expected 403 for missing API key, got {resp_unauth.status_code}"

test_recent_requests_api_returns_most_recent_logged_requests()