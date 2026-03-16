import requests

BASE_URL = "http://localhost:8000"
API_KEY = "350b6ac402988036f99784fbdb71c040527801dd021f88f04cef0dd03425335e"
HEADERS = {"X-API-Key": API_KEY}
TIMEOUT = 30

def test_stats_api_returns_aggregated_telemetry_data():
    try:
        response = requests.get(f"{BASE_URL}/v1/stats", headers=HEADERS, timeout=TIMEOUT)
    except requests.RequestException as e:
        assert False, f"Request failed: {e}"

    assert response.status_code == 200, f"Expected status code 200, got {response.status_code}"
    try:
        data = response.json()
    except ValueError:
        assert False, "Response is not valid JSON"

    # Validate required keys presence and types
    required_fields = {
        "total_requests": int,
        "total_cost_usd": (float, int),
        "total_cost_saved_usd": (float, int),
        "model_usage": dict,
        "escalation_rate": (float, int),
        "savings_ts": list
    }
    for field, expected_type in required_fields.items():
        assert field in data, f"Missing field '{field}' in response"
        assert isinstance(data[field], expected_type), f"Field '{field}' is not of type {expected_type}"

    # Additional semantic checks
    assert data["total_requests"] >= 0, "total_requests should be non-negative"
    assert data["total_cost_usd"] >= 0, "total_cost_usd should be non-negative"
    assert data["total_cost_saved_usd"] >= 0, "total_cost_saved_usd should be non-negative"
    assert 0.0 <= data["escalation_rate"] <= 1.0, "escalation_rate should be between 0 and 1"

    # Validate model_usage dict keys and values types (at least one key-value pair if not empty)
    if data["model_usage"]:
        assert all(isinstance(k, str) for k in data["model_usage"].keys()), "model_usage keys must be strings"
        assert all(isinstance(v, (int, float)) for v in data["model_usage"].values()), "model_usage values must be numbers"

    # Validate savings_ts is a list, optionally check elements if present
    for entry in data["savings_ts"]:
        assert isinstance(entry, dict), "Each savings_ts entry must be a dict"
        # Expected keys could be timestamp and cost_saved_usd or similar (flexible as no exact schema provided)
        # We check existence of at least one numeric value
        numeric_found = any(isinstance(v, (int, float)) for v in entry.values())
        assert numeric_found, "Each savings_ts entry must contain at least one numeric value"

test_stats_api_returns_aggregated_telemetry_data()