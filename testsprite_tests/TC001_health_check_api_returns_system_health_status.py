import requests

BASE_URL = "http://localhost:8000"
HEADERS = {"X-API-Key": "350b6ac402988036f99784fbdb71c040527801dd021f88f04cef0dd03425335e"}
TIMEOUT = 30

def test_health_check_api_returns_system_health_status():
    url = f"{BASE_URL}/v1/health"
    try:
        response = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        assert response.status_code == 200, f"Expected status code 200, got {response.status_code}"
        json_body = response.json()
        assert isinstance(json_body, dict), "Response body is not a JSON object"
        assert "status" in json_body, "'status' field missing in response"
        assert "db" in json_body, "'db' field missing in response"
        assert "classifier" in json_body, "'classifier' field missing in response"
        assert json_body["status"] in {"ok", "degraded"}, "'status' field has unexpected value"
        assert json_body["db"] in {"ok", "error"}, "'db' field has unexpected value"
        assert json_body["classifier"] in {"ok", "error"}, "'classifier' field has unexpected value"
    except requests.RequestException as e:
        assert False, f"Request failed: {e}"

test_health_check_api_returns_system_health_status()