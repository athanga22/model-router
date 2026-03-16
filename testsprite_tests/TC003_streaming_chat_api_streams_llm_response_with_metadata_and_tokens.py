import requests
import json

BASE_URL = "http://localhost:8000"
API_KEY = "350b6ac402988036f99784fbdb71c040527801dd021f88f04cef0dd03425335e"
HEADERS = {
    "X-API-Key": API_KEY,
    "Content-Type": "application/json",
    "Accept": "text/event-stream"
}
TIMEOUT = 30

def test_streaming_chat_api_streams_llm_response_with_metadata_and_tokens():
    prompt = "Explain quantum entanglement"
    url = f"{BASE_URL}/v1/chat/stream"
    payload = {"prompt": prompt}

    with requests.post(url, headers=HEADERS, json=payload, stream=True, timeout=TIMEOUT) as response:
        # Assert HTTP 200 OK response
        assert response.status_code == 200, f"Expected 200 OK but got {response.status_code}"

        # The content-type should be text/event-stream or similar
        content_type = response.headers.get("Content-Type", "")
        assert "text/event-stream" in content_type.lower(), f"Expected 'text/event-stream' in Content-Type but got {content_type}"

        # We'll parse the stream line by line; each line should be a JSON frame or empty line
        # According to the PRD, expect frames of type: metadata, token, done (or error)
        found_metadata_frames = 0
        found_token_frames = 0
        found_done_frame = False

        for line in response.iter_lines(decode_unicode=True):
            if not line or line.strip() == "":
                continue  # skip empty lines

            # Each frame is newline-delimited JSON (one JSON obj per line)
            try:
                frame = json.loads(line)
            except json.JSONDecodeError as e:
                raise AssertionError(f"Failed to decode JSON frame: {line}") from e

            # Validate frame has a 'type' field
            frame_type = frame.get("type")
            assert frame_type in {"metadata", "token", "done", "error"}, f"Unexpected frame type: {frame_type}"

            # Validate metadata frame structure
            if frame_type == "metadata":
                found_metadata_frames += 1
                # Metadata frame must include keys relevant to routing/classification/escalation
                # Required keys according to user flow: type, model_used, difficulty_tag, possibly escalated
                # Validate minimal required fields
                assert "model_used" in frame, "Metadata frame missing 'model_used'"
                assert "difficulty_tag" in frame, "Metadata frame missing 'difficulty_tag'"
                # escalated is bool, optional if escalation happened
                escalated = frame.get("escalated")
                if escalated is not None:
                    assert isinstance(escalated, bool), "'escalated' in metadata frame must be boolean"

            elif frame_type == "token":
                found_token_frames += 1
                # Token frames must include 'token' and usually 'event' fields (e.g., token text, token type)
                # Minimal: ensure 'token' is present and is a string, or if missing, ensure 'event' is string
                token = frame.get("token", None)
                event = frame.get("event", None)

                if token is not None:
                    assert isinstance(token, str), "Token frame 'token' must be a string if present"
                else:
                    # token not present or None, then event must be string
                    assert event is not None and isinstance(event, str), "Token frame must include 'token' as string or 'event' as string"

            elif frame_type == "done":
                found_done_frame = True
                # done frame should have at minimum 'type': 'done'
                # It may have 'escalated' bool field if escalation occurred
                escalated = frame.get("escalated")
                if escalated is not None:
                    assert isinstance(escalated, bool), "'escalated' in done frame must be boolean"
                # No further frames after done frame should be processed
                break

            elif frame_type == "error":
                # If error frame, fail the test
                message = frame.get("message", "No error message provided")
                raise AssertionError(f"Received error frame in stream: {message}")

        # At least one metadata frame should be sent before tokens
        assert found_metadata_frames >= 1, "No metadata frames found in streamed response"

        # At least one token frame should be present (response tokens streamed)
        assert found_token_frames >= 1, "No token frames found in streamed response"

        # A done frame must be present to close the stream properly
        assert found_done_frame, "No done frame found, stream did not close properly"


test_streaming_chat_api_streams_llm_response_with_metadata_and_tokens()
