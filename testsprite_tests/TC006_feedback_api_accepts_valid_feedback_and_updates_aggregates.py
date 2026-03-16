import requests

BASE_URL = "http://localhost:8000"
API_KEY = "350b6ac402988036f99784fbdb71c040527801dd021f88f04cef0dd03425335e"
HEADERS = {"X-API-Key": API_KEY}
TIMEOUT = 30


def test_feedback_api_accepts_valid_feedback_and_updates_aggregates():
    # First, create a new chat request to generate a valid request_id for feedback
    chat_payload = {"prompt": "What is the capital of France?"}
    request_id = None

    try:
        # Create chat request
        chat_response = requests.post(
            f"{BASE_URL}/v1/chat",
            json=chat_payload,
            headers=HEADERS,
            timeout=TIMEOUT,
        )
        assert chat_response.status_code == 200, f"Unexpected chat POST status {chat_response.status_code}"
        chat_json = chat_response.json()

        # Check required fields in chat response
        keys = ["response", "model_used", "difficulty_tag", "cost_usd", "latency_ms", "escalated"]
        for key in keys:
            assert key in chat_json, f"Missing key '{key}' in chat response"

        # We expect that the request_id is logged implicitly in the system, but we need to fetch it.
        # Since the PRD and endpoints don't provide request_id directly on chat response,
        # we fetch the most recent request to get the request_id.
        recent_response = requests.get(f"{BASE_URL}/v1/recent?limit=1", headers=HEADERS, timeout=TIMEOUT)
        assert recent_response.status_code == 200, f"Unexpected recent GET status {recent_response.status_code}"
        recent_json = recent_response.json()
        assert isinstance(recent_json, list) and len(recent_json) == 1, "Recent endpoint did not return 1 item"

        # PRD does not specify request_id or id field in recent request objects, so cannot retrieve request_id
        assert False, "Cannot find 'id' or 'request_id' field in recent request item as per PRD specification"

    finally:
        # Cleanup: no explicit delete endpoint indicated in the PRD for requests or feedback,
        # so no resource deletion is possible here.
        pass


test_feedback_api_accepts_valid_feedback_and_updates_aggregates()
